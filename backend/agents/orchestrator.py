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
from backend.agents.chat import ChatAgent
from backend.models.database import (
    add_opportunity, get_opportunities, archive_opportunity,
    update_opportunity, get_db_settings, update_db_settings, _is_pure_b2g,
)

log = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self, ws_manager=None):
        self.ws_manager = ws_manager  # WebSocket broadcast callable
        self._cycle_running = False
        self._cycle_abort = False
        self._analyst = AnalystAgent()
        self._rater = RatingAgent()
        self._chat = ChatAgent()

    def abort_cycle(self):
        """Signal the running cycle to stop after its current query."""
        if self._cycle_running:
            self._cycle_abort = True
            log.info("Cycle abort requested.")
            return True
        return False

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
        self._cycle_running = True\n        self._cycle_abort = False
        self._current_cycle_id = datetime.utcnow().strftime("%Y%m%d-%H%M")
        update_db_settings({"cycle_running": True, "last_cycle_run": datetime.utcnow().isoformat()})

        asyncio.run(self._async_cycle())

    async def _async_cycle(self):
        try:
            await self._broadcast("cycle_start", {"timestamp": datetime.utcnow().isoformat()})
            log.info("=== Daily cycle started ===")

            # Step 1: Run scouts in parallel
            all_signals, quota_exceeded = await asyncio.get_event_loop().run_in_executor(
                None, self._run_scouts
            )
            log.info("Scouts returned %d total signals (quota_exceeded=%s)", len(all_signals), quota_exceeded)

            if quota_exceeded:
                msg = "Tavily monthly search quota exhausted — no signals collected. Renew API key at app.tavily.com."
                await self._broadcast("quota_exceeded", {"service": "tavily", "message": msg})
                if not all_signals:
                    log.error("Aborting cycle: quota exhausted and no signals available")
                    update_db_settings({"cycle_running": False})
                    return

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

    def _run_scouts(self) -> tuple[list[dict], bool]:
        from backend.agents.base import TavilyQuotaExceededError
        scouts = [
            ScoutBusinessAgent(),
            ScoutCommunityAgent(),
            ScoutLongformAgent(),
        ]
        all_signals: list[dict] = []
        quota_exceeded = False
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(s.run): s.name for s in scouts}
            for future in as_completed(futures):
                try:
                    signals = future.result()
                    all_signals.extend(signals)
                except TavilyQuotaExceededError:
                    quota_exceeded = True
                    log.error("Tavily quota exhausted — scout searches failing. Renew key at app.tavily.com")
                except Exception as e:
                    log.error("Scout error: %s", e)
        return all_signals, quota_exceeded

    def _deduplicate(self, signals: list[dict]) -> list[dict]:
        from backend.models.database import _title_similarity, DUPLICATE_THRESHOLD
        kept: list[dict] = []
        for signal in signals:
            title = signal.get("title", "").strip()
            if not title:
                continue
            if not any(
                _title_similarity(title, k.get("title", "")) >= DUPLICATE_THRESHOLD
                for k in kept
            ):
                kept.append(signal)
        return kept

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
                    opp.cycle_id = getattr(self, '_current_cycle_id', opp.cycle_id)
                    if _is_pure_b2g(opp):
                        log.info("Skipping pure B2G opportunity: '%s'", opp.title)
                    else:
                        saved = add_opportunity(opp)
                        results.append(saved)
                        await self._broadcast("opportunity_added", {
                            "id": opp.id,
                            "title": opp.title,
                            "score": opp.composite_score,
                            "type": opp.classification.type,
                            "go_to_market": opp.classification.go_to_market,
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
        self._cycle_running = True\n        self._cycle_abort = False
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
            b2g_archived = 0
            for i, opp in enumerate(opps):
                try:
                    report = self._opp_to_report(opp)
                    new_rating = await loop.run_in_executor(None, self._rater.rate, report)
                    if new_rating:
                        # Scores only change when new research is introduced (full cycle / deep research).
                        # Rerate refreshes classification metadata only — ratings stay frozen.
                        opp.classification = new_rating.classification
                        opp.updated_at = datetime.utcnow()
                        # Archive pure B2G opportunities
                        if _is_pure_b2g(opp):
                            log.info("Archiving pure B2G: '%s'", opp.title)
                            opp.user.archived = True
                            opp.user.archived_at = datetime.utcnow()
                            db.archived_opportunities.append(opp)
                            db.opportunities.remove(opp)
                            b2g_archived += 1
                        # Save incrementally so progress survives interruptions
                        db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
                        save_db(db)
                except Exception as e:
                    log.error("Rerate failed for '%s': %s", opp.title, e)
                await self._broadcast("rerate_progress", {
                    "done": i + 1,
                    "total": len(opps),
                    "title": opp.title,
                    "type": opp.classification.type,
                    "score": opp.composite_score,
                    "go_to_market": opp.classification.go_to_market,
                })

            update_db_settings({"cycle_running": False})
            await self._broadcast("rerate_done", {"total": len(opps), "b2g_archived": b2g_archived})
            log.info("Re-rating complete — %d B2G archived", b2g_archived)
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

    # --- Single-opportunity rerate ---

    def rerate_one(self, opp_id: str):
        asyncio.run(self._async_rerate_one(opp_id))

    async def _async_rerate_one(self, opp_id: str):
        from backend.models.database import load_db, save_db
        try:
            db = load_db()
            opp = next((o for o in db.opportunities if o.id == opp_id), None)
            if not opp:
                log.warning("rerate_one: opportunity %s not found", opp_id)
                return

            report = self._opp_to_report(opp)
            loop = asyncio.get_event_loop()
            new_rating = await loop.run_in_executor(None, self._rater.rate, report)
            if new_rating:
                # Classification only — scores require new research to change
                opp.classification = new_rating.classification
                opp.updated_at = datetime.utcnow()

                if _is_pure_b2g(opp):
                    log.info("rerate_one: archiving pure B2G '%s'", opp.title)
                    opp.user.archived = True
                    opp.user.archived_at = datetime.utcnow()
                    db.archived_opportunities.append(opp)
                    db.opportunities.remove(opp)

                db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
                save_db(db)
                await self._broadcast("opportunity_updated", {
                    "id": opp_id,
                    "score": opp.composite_score,
                    "type": opp.classification.type,
                    "go_to_market": opp.classification.go_to_market,
                })
                log.info("rerate_one: completed for '%s' → %.1f", opp.title, opp.composite_score)
        except Exception as e:
            log.error("rerate_one error for %s: %s", opp_id, e, exc_info=True)

    # --- Threshold-based full rescore (rubric calibration + devil's advocate) ---

    def rerate_above_threshold(self, threshold: float):
        if self._cycle_running:
            return False
        self._cycle_running = True\n        self._cycle_abort = False
        update_db_settings({"cycle_running": True})
        asyncio.run(self._async_rerate_above_threshold(threshold))
        return True

    async def _async_rerate_above_threshold(self, threshold: float):
        from backend.models.database import load_db, save_db
        try:
            db = load_db()
            opps = [o for o in db.opportunities if o.composite_score >= threshold]
            await self._broadcast("rerate_start", {"total": len(opps)})
            log.info("Calibrated rerate: %d opportunities at score >= %.0f", len(opps), threshold)

            loop = asyncio.get_event_loop()
            for i, opp in enumerate(opps):
                try:
                    report = self._opp_to_report(opp)
                    new_rating = await loop.run_in_executor(None, self._rater.rate, report)
                    if new_rating:
                        # Full rescore — intentional rubric recalibration
                        opp.ratings = new_rating.ratings
                        opp.composite_score = new_rating.composite_score
                        opp.classification = new_rating.classification
                        if new_rating.devils_advocate:
                            opp.devils_advocate = new_rating.devils_advocate
                        opp.updated_at = datetime.utcnow()

                        if _is_pure_b2g(opp):
                            log.info("Calibrated rerate: archiving pure B2G '%s'", opp.title)
                            opp.user.archived = True
                            opp.user.archived_at = datetime.utcnow()
                            db.archived_opportunities.append(opp)
                            db.opportunities.remove(opp)

                        db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
                        save_db(db)
                except Exception as e:
                    log.error("Calibrated rerate failed for '%s': %s", opp.title, e)

                await self._broadcast("rerate_progress", {
                    "done": i + 1,
                    "total": len(opps),
                    "title": opp.title,
                    "type": opp.classification.type,
                    "score": opp.composite_score,
                    "go_to_market": opp.classification.go_to_market,
                })

            update_db_settings({"cycle_running": False})
            await self._broadcast("rerate_done", {"total": len(opps), "b2g_archived": 0})
            log.info("Calibrated rerate complete: %d opportunities processed", len(opps))
        except Exception as e:
            log.error("Calibrated rerate error: %s", e, exc_info=True)
            update_db_settings({"cycle_running": False})
            await self._broadcast("rerate_error", {"error": str(e)})
        finally:
            self._cycle_running = False

    # --- Single-opportunity full rescore (calibrate: scores + DA, no chat context) ---

    def calibrate_one(self, opp_id: str):
        asyncio.run(self._async_calibrate_one(opp_id))

    async def _async_calibrate_one(self, opp_id: str):
        from backend.models.database import load_db, save_db
        try:
            db = load_db()
            opp = next((o for o in db.opportunities if o.id == opp_id), None)
            if not opp:
                log.warning("calibrate_one: opportunity %s not found", opp_id)
                return
            report = self._opp_to_report(opp)
            loop = asyncio.get_event_loop()
            new_rating = await loop.run_in_executor(None, self._rater.rate, report)
            if new_rating:
                opp.ratings = new_rating.ratings
                opp.composite_score = new_rating.composite_score
                opp.classification = new_rating.classification
                if new_rating.devils_advocate:
                    opp.devils_advocate = new_rating.devils_advocate
                opp.updated_at = datetime.utcnow()
                db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
                save_db(db)
                await self._broadcast("opportunity_updated", {
                    "id": opp_id,
                    "score": opp.composite_score,
                    "type": opp.classification.type,
                    "go_to_market": opp.classification.go_to_market,
                })
                log.info("calibrate_one: completed for '%s' → %.1f", opp.title, opp.composite_score)
        except Exception as e:
            log.error("calibrate_one error for %s: %s", opp_id, e, exc_info=True)

    # --- Single-opportunity rerate WITH chat context (scores can update) ---

    def rerate_one_with_context(self, opp_id: str, chat_context: list[dict]):
        asyncio.run(self._async_rerate_one_with_context(opp_id, chat_context))

    async def _async_rerate_one_with_context(self, opp_id: str, chat_context: list[dict]):
        from backend.models.database import load_db, save_db
        try:
            db = load_db()
            opp = next((o for o in db.opportunities if o.id == opp_id), None)
            if not opp:
                log.warning("rerate_one_with_context: opportunity %s not found", opp_id)
                return

            # Build context string from the last 20 chat messages
            chat_lines = []
            for msg in chat_context[-20:]:
                role = "User" if msg.get("role") == "user" else "Analyst"
                chat_lines.append(f"{role}: {msg.get('content', '')}")
            extra_context = (
                "New insights from analyst conversation — incorporate into scoring:\n\n"
                + "\n\n".join(chat_lines)
            )

            report = self._opp_to_report(opp)
            report["extra_context"] = extra_context

            loop = asyncio.get_event_loop()
            new_rating = await loop.run_in_executor(None, self._rater.rate, report)
            if new_rating:
                # Chat insights = new information → full rescore (ratings + classification)
                opp.ratings = new_rating.ratings
                opp.composite_score = new_rating.composite_score
                opp.classification = new_rating.classification
                opp.updated_at = datetime.utcnow()

                if _is_pure_b2g(opp):
                    log.info("rerate_one_with_context: archiving pure B2G '%s'", opp.title)
                    opp.user.archived = True
                    opp.user.archived_at = datetime.utcnow()
                    db.archived_opportunities.append(opp)
                    db.opportunities.remove(opp)

                db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
                save_db(db)
                await self._broadcast("opportunity_updated", {
                    "id": opp_id,
                    "score": opp.composite_score,
                    "type": opp.classification.type,
                    "go_to_market": opp.classification.go_to_market,
                })
                log.info(
                    "rerate_one_with_context: completed for '%s' → %.1f",
                    opp.title, opp.composite_score,
                )
        except Exception as e:
            log.error("rerate_one_with_context error for %s: %s", opp_id, e, exc_info=True)

    # --- Reframe a single opportunity using chat insights ---

    def reframe_one(self, opp_id: str):
        asyncio.run(self._async_reframe_one(opp_id))

    async def _async_reframe_one(self, opp_id: str):
        from backend.models.database import load_db, save_db
        from backend.models.opportunity import (
            Ratings, RatingFactor, Classification, DevilsAdvocate
        )
        try:
            db = load_db()
            opp = next((o for o in db.opportunities if o.id == opp_id), None)
            if not opp:
                log.warning("reframe_one: opportunity %s not found", opp_id)
                return

            log.info("reframe_one: starting for '%s'", opp.title)
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._chat.reframe, opp)
            if not data:
                log.warning("reframe_one: no output for '%s'", opp.title)
                return

            # Update title
            if data.get("title"):
                opp.title = data["title"]

            # Update research fields
            for field in ("pain_point_summary", "affected_segments", "solution_hypothesis",
                          "market_size_estimate", "solution_tam_estimate", "tam_derivation",
                          "market_growth_rate", "monetization_models",
                          "incumbent_ai_threat", "build_vs_buy_risk"):
                val = data.get(field)
                if val is not None:
                    setattr(opp.research, field, val)

            # Update ratings
            raw_ratings = data.get("ratings", {})
            factor_names = ["market_size", "pain_severity", "solution_clarity",
                            "competitive_insight", "monetization_potential",
                            "startup_viability", "signal_authority"]
            for name in factor_names:
                rf_data = raw_ratings.get(name)
                if not rf_data:
                    continue
                existing: RatingFactor = getattr(opp.ratings, name)
                existing.score = rf_data.get("score", existing.score)
                existing.rationale = rf_data.get("rationale", existing.rationale)
                existing.evidence = rf_data.get("evidence", existing.evidence)
                if name == "startup_viability":
                    if rf_data.get("capital_efficiency") is not None:
                        existing.capital_efficiency = rf_data["capital_efficiency"]
                    if rf_data.get("time_to_revenue") is not None:
                        existing.time_to_revenue = rf_data["time_to_revenue"]
                    if rf_data.get("execution_accessibility") is not None:
                        existing.execution_accessibility = rf_data["execution_accessibility"]

            # Recalculate composite from ratings (authoritative weights)
            opp.composite_score = opp.ratings.composite()

            # Update classification
            cls = data.get("classification", {})
            if cls:
                for field in ("type", "moonshot_justification", "category", "industry",
                              "go_to_market", "tech_stack", "tags"):
                    val = cls.get(field)
                    if val is not None:
                        setattr(opp.classification, field, val)

            # Update devil's advocate
            da = data.get("devils_advocate", {})
            if da:
                if not opp.devils_advocate:
                    opp.devils_advocate = DevilsAdvocate(
                        bear_case="", key_risks=[], biggest_threat=""
                    )
                for field in ("bear_case", "key_risks", "biggest_threat"):
                    val = da.get(field)
                    if val is not None:
                        setattr(opp.devils_advocate, field, val)

            opp.updated_at = datetime.utcnow()
            if _is_pure_b2g(opp):
                log.info("reframe_one: archiving pure B2G '%s'", opp.title)
                opp.user.archived = True
                opp.user.archived_at = datetime.utcnow()
                db.archived_opportunities.append(opp)
                db.opportunities.remove(opp)

            db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
            save_db(db)
            await self._broadcast("opportunity_updated", {
                "id": opp_id,
                "score": opp.composite_score,
                "type": opp.classification.type,
                "go_to_market": opp.classification.go_to_market,
            })
            log.info("reframe_one: completed for '%s' → %.1f", opp.title, opp.composite_score)
        except Exception as e:
            log.error("reframe_one error for %s: %s", opp_id, e, exc_info=True)

    # --- Deep research on a single opportunity ---

    def deep_research_one(self, opp_id: str, task: str):
        asyncio.run(self._async_deep_research_one(opp_id, task))

    async def _async_deep_research_one(self, opp_id: str, task: str):
        from backend.models.database import load_db, save_db
        try:
            db = load_db()
            opp = next((o for o in db.opportunities if o.id == opp_id), None)
            if not opp:
                log.warning("deep_research_one: opportunity %s not found", opp_id)
                return

            log.info("deep_research_one: starting for '%s', task='%s'", opp.title, task)
            signal = self._opp_to_report(opp)

            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                None, self._analyst.analyze, signal, task
            )

            # Merge new research into existing opportunity
            opp.research.pain_point_summary = report.get("pain_point_summary", opp.research.pain_point_summary)
            opp.research.affected_segments = report.get("affected_segments", opp.research.affected_segments)
            if report.get("market_size_estimate"):
                opp.research.market_size_estimate = report["market_size_estimate"]
            if report.get("solution_tam_estimate"):
                opp.research.solution_tam_estimate = report["solution_tam_estimate"]
            if report.get("tam_derivation"):
                opp.research.tam_derivation = report["tam_derivation"]
            if report.get("market_growth_rate"):
                opp.research.market_growth_rate = report["market_growth_rate"]
            # Append new competitors not already present
            existing_names = {c.get("name", "").lower() for c in opp.research.competitors}
            for comp in report.get("competitors", []):
                if comp.get("name", "").lower() not in existing_names:
                    opp.research.competitors.append(comp)
            # Append new monetization models
            existing_models = set(opp.research.monetization_models)
            for model in report.get("monetization_models", []):
                if model not in existing_models:
                    opp.research.monetization_models.append(model)
                    existing_models.add(model)
            if report.get("solution_hypothesis"):
                opp.research.solution_hypothesis = report["solution_hypothesis"]
            # Append new sources
            existing_sources = set(opp.research.sources)
            for src in report.get("sources", []):
                if src not in existing_sources:
                    opp.research.sources.append(src)
                    existing_sources.add(src)

            # Re-rate
            new_rating = await loop.run_in_executor(None, self._rater.rate, report)
            if new_rating:
                opp.ratings = new_rating.ratings
                opp.composite_score = new_rating.composite_score
                opp.classification = new_rating.classification

            opp.updated_at = datetime.utcnow()
            db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
            save_db(db)

            await self._broadcast("opportunity_updated", {
                "id": opp_id,
                "score": opp.composite_score,
                "type": opp.classification.type,
                "go_to_market": opp.classification.go_to_market,
            })
            log.info("deep_research_one: completed for '%s'", opp.title)
        except Exception as e:
            log.error("deep_research_one error for %s: %s", opp_id, e, exc_info=True)

    # --- Guided cycle (plain-language prompt → LLM generates queries → pipeline) ---

    def guided_cycle(self, prompt: str, target_count: int = 5, target_score: float = 75.0):
        if self._cycle_running:
            return False
        self._cycle_running = True\n        self._cycle_abort = False
        self._current_cycle_id = datetime.utcnow().strftime("%Y%m%d-%H%M")
        update_db_settings({"cycle_running": True, "last_cycle_run": datetime.utcnow().isoformat()})
        asyncio.run(self._async_guided_cycle(prompt, target_count, target_score))
        return True

    async def _async_guided_cycle(self, prompt: str, target_count: int, target_score: float):
        from backend.agents.scout_guided import GuidedScoutAgent
        from backend.models.database import _title_similarity, load_db
        try:
            await self._broadcast("cycle_start", {
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "guided",
                "prompt": prompt,
            })
            log.info("=== Guided cycle: '%s' target=%d score>=%.0f ===", prompt[:60], target_count, target_score)

            loop = asyncio.get_event_loop()
            scout = GuidedScoutAgent()

            db = load_db()
            existing_titles = [o.title for o in db.opportunities]
            seen_titles: list[str] = []

            def _is_dup(title: str) -> bool:
                return any(_title_similarity(title, t) >= 0.60 for t in seen_titles + existing_titles)

            # Generate queries then run them one at a time
            queries = await loop.run_in_executor(None, scout.generate_queries, prompt, 7)
            log.info("Guided cycle: generated %d queries", len(queries))
            await self._broadcast("scouts_done", {"signal_count": len(queries), "queries": queries})

            qualifying: list = []
            for q_idx, query in enumerate(queries):
                if len(qualifying) >= target_count or self._cycle_abort:
                    break
                log.info("Guided query %d/%d: %s", q_idx + 1, len(queries), query)
                signals = await loop.run_in_executor(None, scout.query_signals_raw, query, prompt)

                for signal in signals:
                    if len(qualifying) >= target_count or self._cycle_abort:
                        break
                    title = signal.get("title", "").strip()
                    if not title or _is_dup(title):
                        continue
                    seen_titles.append(title)
                    try:
                        report = await loop.run_in_executor(None, self._analyst.analyze, signal)
                        opp = await loop.run_in_executor(None, self._rater.rate, report)
                        if opp and opp.composite_score >= target_score and not _is_pure_b2g(opp):
                            opp.cycle_id = self._current_cycle_id
                            saved = add_opportunity(opp)
                            qualifying.append(saved)
                            await self._broadcast("opportunity_added", {
                                "id": opp.id, "title": opp.title,
                                "score": opp.composite_score,
                                "type": opp.classification.type,
                                "go_to_market": opp.classification.go_to_market,
                            })
                            log.info("Guided: ✓ #%d [%.1f] %s", len(qualifying), opp.composite_score, opp.title[:60])
                        elif opp:
                            log.info("Guided: ✗ [%.1f] %s", opp.composite_score, title[:50])
                    except Exception as e:
                        log.error("Guided: error on '%s': %s", title[:50], e)

            summary = self._generate_summary(qualifying)
            update_db_settings({"cycle_running": False, "last_cycle_summary": summary})
            await self._broadcast("cycle_done", {"new_opportunities": len(qualifying), "summary": summary})
            log.info("=== Guided cycle complete: %d opportunities ===", len(qualifying))
        except Exception as e:
            log.error("Guided cycle error: %s", e, exc_info=True)
            update_db_settings({"cycle_running": False})
            await self._broadcast("cycle_error", {"error": str(e)})
        finally:
            self._cycle_running = False

    # --- Targeted domain cycle ---

    def targeted_cycle(self, domains: list[str], target_per_domain: int = 5, target_score: float = 75.0):
        """Run a targeted discovery cycle for specific domains until target_per_domain qualifying opps found."""
        if self._cycle_running:
            return False
        self._cycle_running = True\n        self._cycle_abort = False
        self._current_cycle_id = datetime.utcnow().strftime("%Y%m%d-%H%M")
        update_db_settings({"cycle_running": True, "last_cycle_run": datetime.utcnow().isoformat()})
        asyncio.run(self._async_targeted_cycle(domains, target_per_domain, target_score))
        return True

    async def _async_targeted_cycle(self, domains: list[str], target_per_domain: int, target_score: float):
        from backend.agents.scout_targeted import TargetedScoutAgent
        from backend.models.database import _title_similarity, load_db
        try:
            await self._broadcast("cycle_start", {
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "targeted",
                "domains": domains,
            })
            log.info("=== Targeted cycle: domains=%s target=%d score>=%.0f ===", domains, target_per_domain, target_score)

            loop = asyncio.get_event_loop()
            scout = TargetedScoutAgent()
            all_new: list = []

            for domain in domains:
                qualifying: list = []
                seen_titles: list[str] = []

                # Snapshot existing titles for dedup (refresh per domain)
                db = load_db()
                existing_titles = [o.title for o in db.opportunities]

                def _is_dup(title: str) -> bool:
                    return any(
                        _title_similarity(title, t) >= 0.60
                        for t in seen_titles + existing_titles
                    )

                queries = scout.get_queries(domain)
                log.info("Targeted[%s]: %d queries, stopping at %d qualifying", domain, len(queries), target_per_domain)

                for q_idx, query in enumerate(queries):
                    if len(qualifying) >= target_per_domain:
                        log.info("Targeted[%s]: target reached after %d queries", domain, q_idx)
                        break
                    if self._cycle_abort:
                        log.info("Targeted[%s]: abort requested, stopping", domain)
                        break

                    log.info("Targeted[%s] query %d/%d: %s", domain, q_idx + 1, len(queries), query[:60])
                    # Scout one query (web search + LLM extraction)
                    signals = await loop.run_in_executor(None, scout.query_signals, query, domain)
                    log.info("Targeted[%s]: query returned %d signals", domain, len(signals))

                    # Immediately process each signal — stop as soon as we have enough
                    for signal in signals:
                        if len(qualifying) >= target_per_domain or self._cycle_abort:
                            break

                        title = signal.get("title", "").strip()
                        if not title or _is_dup(title):
                            log.info("Targeted[%s]: skipping dup/blank '%s'", domain, title[:50])
                            continue
                        seen_titles.append(title)

                        try:
                            report = await loop.run_in_executor(None, self._analyst.analyze, signal)
                            opp = await loop.run_in_executor(None, self._rater.rate, report)
                            if opp is None:
                                log.info("Targeted[%s]: rater returned None for '%s'", domain, title[:50])
                                continue
                            opp.cycle_id = self._current_cycle_id
                            score = opp.composite_score
                            if score >= target_score and not _is_pure_b2g(opp):
                                saved = add_opportunity(opp)
                                qualifying.append(saved)
                                all_new.append(saved)
                                await self._broadcast("opportunity_added", {
                                    "id": opp.id,
                                    "title": opp.title,
                                    "score": score,
                                    "type": opp.classification.type,
                                    "go_to_market": opp.classification.go_to_market,
                                    "domain": domain,
                                })
                                log.info("Targeted[%s]: ✓ #%d [%.1f] %s", domain, len(qualifying), score, opp.title[:60])
                            else:
                                log.info("Targeted[%s]: ✗ [%.1f] %s", domain, score, title[:50])
                        except Exception as e:
                            log.error("Targeted[%s]: error on '%s': %s", domain, title[:50], e)

                    # Checkpoint after each query
                    await self._broadcast("batch_done", {
                        "domain": domain,
                        "qualifying": len(qualifying),
                        "target": target_per_domain,
                        "queries_run": q_idx + 1,
                    })

                log.info("Targeted[%s]: finished — %d/%d qualifying", domain, len(qualifying), target_per_domain)

            summary = self._generate_summary(all_new)
            update_db_settings({"cycle_running": False, "last_cycle_summary": summary})
            await self._broadcast("cycle_done", {
                "new_opportunities": len(all_new),
                "summary": summary,
                "domains": domains,
            })
            log.info("=== Targeted cycle complete: %d total new opportunities ===", len(all_new))
        except Exception as e:
            log.error("Targeted cycle error: %s", e, exc_info=True)
            update_db_settings({"cycle_running": False})
            await self._broadcast("cycle_error", {"error": str(e)})
        finally:
            self._cycle_running = False

    # --- Upload processing ---

    def process_upload(self, text: str, filename: str):
        if self._cycle_running:
            return False
        self._cycle_running = True\n        self._cycle_abort = False
        self._current_cycle_id = datetime.utcnow().strftime("%Y%m%d-%H%M")
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
                        opp.cycle_id = getattr(self, '_current_cycle_id', opp.cycle_id)
                        if _is_pure_b2g(opp):
                            log.info("Skipping pure B2G (upload): '%s'", opp.title)
                        else:
                            saved = add_opportunity(opp)
                            new_opps.append(saved)
                            await self._broadcast("opportunity_added", {
                                "id": opp.id,
                                "title": opp.title,
                                "score": opp.composite_score,
                                "type": opp.classification.type,
                                "go_to_market": opp.classification.go_to_market,
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
