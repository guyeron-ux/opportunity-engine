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

    # --- Rerate existing opportunities ---

    def rerate_all(self):
        if self._cycle_running:
            return False
        self._cycle_running = True
        update_db_settings({"cycle_running": True})
        asyncio.run(self._async_rerate())
        return True

    async def _async_rerate(self):
        from backend.models.database import load_db, save_db
        try:
            db = load_db()
            opps = db.opportunities[:]
            await self._broadcast("rerate_start", {"total": len(opps)})
            log.info("Re-rating %d opportunities", len(opps))

            loop = asyncio.get_event_loop()
            for i, opp in enumerate(opps):
                report = self._opp_to_report(opp)
                new_rating = await loop.run_in_executor(None, self._rater.rate, report)
                if new_rating:
                    opp.ratings = new_rating.ratings
                    opp.composite_score = new_rating.composite_score
                    opp.classification = new_rating.classification
                    from datetime import datetime
                    opp.updated_at = datetime.utcnow()
                await self._broadcast("rerate_progress", {
                    "done": i + 1,
                    "total": len(opps),
                    "title": opp.title,
                    "type": opp.classification.type,
                    "score": opp.composite_score,
                })

            db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
            update_db_settings({"cycle_running": False})
            save_db(db)
            await self._broadcast("rerate_done", {"total": len(opps)})
            log.info("Re-rating complete")
        except Exception as e:
            log.error("Rerate error: %s", e, exc_info=True)
            update_db_settings({"cycle_running": False})
            await self._broadcast("rerate_error", {"error": str(e)})
        finally:
            self._cycle_running = False

    def _opp_to_report(self, opp) -> dict:
        return {
            "title": opp.title,
            "pain_point_summary": opp.research.pain_point_summary,
            "affected_segments": opp.research.affected_segments,
            "market_size_estimate": opp.research.market_size_estimate,
            "market_growth_rate": opp.research.market_growth_rate,
            "competitors": opp.research.competitors,
            "monetization_models": opp.research.monetization_models,
            "solution_hypothesis": opp.research.solution_hypothesis,
            "sources": opp.research.sources,
            "signal_sources": opp.research.signal_sources,
            "raw_signals": opp.research.raw_signals,
        }

    # --- Upload processing ---

    def process_upload(self, text: str, filename: str):
        if self._cycle_running:
            return False
        self._cycle_running = True
        update_db_settings({"cycle_running": True})
        asyncio.run(self._async_process_upload(text, filename))
        return True

    async def _async_process_upload(self, text: str, filename: str):
        try:
            await self._broadcast("cycle_start", {
                "timestamp": datetime.utcnow().isoformat(),
                "source": filename,
            })
            log.info("Processing upload: %s", filename)

            loop = asyncio.get_event_loop()
            signals = await loop.run_in_executor(None, self._extract_signals_from_text, text)
            log.info("Extracted %d signals from upload", len(signals))
            await self._broadcast("scouts_done", {"signal_count": len(signals)})

            new_opps = []
            for i, signal in enumerate(signals):
                try:
                    report = await loop.run_in_executor(None, self._analyst.analyze, signal)
                    opp = await loop.run_in_executor(None, self._rater.rate, report)
                    if opp:
                        saved = add_opportunity(opp)
                        new_opps.append(saved)
                        await self._broadcast("opportunity_added", {
                            "id": opp.id,
                            "title": opp.title,
                            "score": opp.composite_score,
                            "type": opp.classification.type,
                        })
                except Exception as e:
                    log.error("Error processing uploaded signal '%s': %s", signal.get("title"), e)
                await self._broadcast("batch_done", {
                    "processed": i + 1,
                    "total": len(signals),
                    "new_opportunities": len(new_opps),
                })

            summary = self._generate_summary(new_opps)
            update_db_settings({"cycle_running": False, "last_cycle_summary": summary})
            self._save_import_record(filename, len(signals), len(new_opps))
            await self._broadcast("cycle_done", {
                "new_opportunities": len(new_opps),
                "summary": summary,
            })
            log.info("Upload processing complete: %d new opportunities", len(new_opps))
        except Exception as e:
            log.error("Upload processing error: %s", e, exc_info=True)
            update_db_settings({"cycle_running": False})
            await self._broadcast("cycle_error", {"error": str(e)})
        finally:
            self._cycle_running = False

    def _save_import_record(self, filename: str, signals: int, added: int):
        from backend.models.database import load_db, save_db
        from backend.models.opportunity import ImportRecord
        db = load_db()
        record = ImportRecord(
            id=f"IMP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            filename=filename,
            signals_extracted=signals,
            opportunities_added=added,
        )
        db.imports.append(record)
        save_db(db)

    def _extract_signals_from_text(self, text: str) -> list[dict]:
        prompt = f"""Extract startup opportunity signals from the following text.

For each distinct opportunity, pain point, or market gap mentioned, return a structured signal.

Return a JSON array (no markdown):
[
  {{
    "title": "concise opportunity name",
    "pain_point_summary": "description of the problem or gap",
    "signal_strength": 3,
    "source": "uploaded document"
  }}
]

If the document contains a single opportunity, return an array with one item.
Only extract concrete, actionable opportunities — skip vague mentions.

TEXT:
{text[:12000]}"""

        try:
            result = self._rater._call_json(
                [{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            if isinstance(result, list):
                return result
        except Exception as e:
            log.error("Signal extraction failed: %s", e)
        return []

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
