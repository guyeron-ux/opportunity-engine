from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from backend.agents.scout_business import ScoutBusinessAgent
from backend.agents.scout_community import ScoutCommunityAgent
from backend.agents.scout_longform import ScoutLongformAgent
from backend.agents.analyst import AnalystAgent
from backend.agents.rating import RatingAgent
from backend.models.database import (
    add_opportunity, get_opportunities, archive_opportunity,
    update_opportunity, get_db_settings, update_db_settings,
)

log = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self, ws_manager=None):
        self.ws_manager = ws_manager  # WebSocket broadcast callable
        self._cycle_running = False
        self._analyst = AnalystAgent()
        self._rater = RatingAgent()

    async def _broadcast(self, event: str, data: dict):
        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({"event": event, "data": data})
            except Exception as e:
                log.warning("WS broadcast failed: %s", e)

    def run_daily_cycle(self):
        if self._cycle_running:
            log.warning("Cycle already running, skipping.")
            return
        self._cycle_running = True
        update_db_settings({"cycle_running": True, "last_cycle_run": datetime.utcnow().isoformat()})

        asyncio.run(self._async_cycle())

    async def _async_cycle(self):
        try:
            await self._broadcast("cycle_start", {"timestamp": datetime.utcnow().isoformat()})
            log.info("=== Daily cycle started ===")

            # Step 1: Run scouts in parallel
            all_signals = await asyncio.get_event_loop().run_in_executor(
                None, self._run_scouts
            )
            log.info("Scouts returned %d total signals", len(all_signals))
            await self._broadcast("scouts_done", {"signal_count": len(all_signals)})

            # Step 2: Deduplicate
            signals = self._deduplicate(all_signals)
            log.info("%d signals after deduplication", len(signals))

            # Step 3: Process in batches
            new_opps = []
            batch_size = 4
            for i in range(0, len(signals), batch_size):
                batch = signals[i:i + batch_size]
                batch_results = await self._process_batch(batch)
                new_opps.extend(batch_results)
                await self._broadcast("batch_done", {
                    "processed": i + len(batch),
                    "total": len(signals),
                    "new_opportunities": len(new_opps),
                })

            # Step 4: Summary
            summary = self._generate_summary(new_opps)
            update_db_settings({
                "cycle_running": False,
                "last_cycle_summary": summary,
            })
            await self._broadcast("cycle_done", {
                "new_opportunities": len(new_opps),
                "summary": summary,
            })
            log.info("=== Daily cycle complete: %d new opportunities ===", len(new_opps))

        except Exception as e:
            log.error("Cycle error: %s", e, exc_info=True)
            update_db_settings({"cycle_running": False})
            await self._broadcast("cycle_error", {"error": str(e)})
        finally:
            self._cycle_running = False

    def _run_scouts(self) -> list[dict]:
        scouts = [
            ScoutBusinessAgent(),
            ScoutCommunityAgent(),
            ScoutLongformAgent(),
        ]
        all_signals: list[dict] = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(s.run): s.name for s in scouts}
            for future in as_completed(futures):
                try:
                    signals = future.result()
                    all_signals.extend(signals)
                except Exception as e:
                    log.error("Scout error: %s", e)
        return all_signals

    def _deduplicate(self, signals: list[dict]) -> list[dict]:
        seen_titles: set[str] = set()
        unique = []
        for signal in signals:
            title_key = signal.get("title", "").lower().strip()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(signal)
        return unique

    async def _process_batch(self, signals: list[dict]) -> list:
        loop = asyncio.get_event_loop()
        results = []
        for signal in signals:
            try:
                # Analyst (blocking I/O — run in executor)
                report = await loop.run_in_executor(None, self._analyst.analyze, signal)
                # Rating
                opp = await loop.run_in_executor(None, self._rater.rate, report)
                if opp:
                    saved = add_opportunity(opp)
                    results.append(saved)
                    await self._broadcast("opportunity_added", {
                        "id": opp.id,
                        "title": opp.title,
                        "score": opp.composite_score,
                        "type": opp.classification.type,
                    })
            except Exception as e:
                log.error("Error processing signal '%s': %s", signal.get("title"), e)
        return results

    def _generate_summary(self, new_opps: list) -> dict:
        if not new_opps:
            return {"total": 0, "moonshots": 0, "pragmatic": 0, "avg_score": 0}
        scores = [o.composite_score for o in new_opps]
        return {
            "total": len(new_opps),
            "moonshots": sum(1 for o in new_opps if o.classification.type == "Moonshot"),
            "pragmatic": sum(1 for o in new_opps if o.classification.type == "Pragmatic"),
            "avg_score": round(sum(scores) / len(scores), 1),
            "top_opportunity": max(new_opps, key=lambda o: o.composite_score).title if new_opps else None,
        }

    # --- User command handlers ---

    def annotate(self, opp_id: str, notes: str) -> bool:
        result = update_opportunity(opp_id, {"notes": notes})
        return result is not None

    def archive(self, opp_id: str) -> bool:
        return archive_opportunity(opp_id)

    def request_info(self, opp_id: str) -> bool:
        result = update_opportunity(opp_id, {"deeper_research_requested": True})
        return result is not None

    def set_threshold(self, threshold: int) -> None:
        update_db_settings({"score_threshold": threshold})

    def get_status(self) -> dict:
        db_settings = get_db_settings()
        return {
            "cycle_running": self._cycle_running,
            "last_run": db_settings.get("last_cycle_run"),
            "last_summary": db_settings.get("last_cycle_summary"),
        }
