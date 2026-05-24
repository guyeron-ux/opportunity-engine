from __future__ import annotations
import asyncio
import io
import json
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.models.database import (
    get_opportunities, archive_opportunity, update_opportunity,
    get_db_settings, update_db_settings, load_db,
    get_opportunity_by_id, append_chat_messages, clear_chat,
    delete_opportunity,
)
from backend.models.opportunity import OpportunityEntry
from backend.api.websocket import ws_manager

router = APIRouter()

# Lazy import of orchestrator to avoid circular deps at module load
_orchestrator = None


def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from backend.agents.orchestrator import Orchestrator
        _orchestrator = Orchestrator(ws_manager=ws_manager)
    return _orchestrator


# --- Request / Response models ---

class AnnotateRequest(BaseModel):
    notes: str


class ThresholdRequest(BaseModel):
    score_threshold: int


class FiltersRequest(BaseModel):
    types: list[str] = []
    categories: list[str] = []
    industries: list[str] = []
    tech_stacks: list[str] = []
    min_score: Optional[float] = None
    max_score: Optional[float] = None


# --- REST Endpoints ---

@router.get("/opportunities", response_model=list[OpportunityEntry])
def list_opportunities(
    threshold: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
):
    filters = {}
    if type:
        filters["types"] = [type]
    if category:
        filters["categories"] = [category]
    if industry:
        filters["industries"] = [industry]
    if min_score is not None:
        filters["min_score"] = min_score
    if max_score is not None:
        filters["max_score"] = max_score
    return get_opportunities(filters=filters or None, threshold=threshold)


@router.get("/opportunities/{opp_id}", response_model=OpportunityEntry)
def get_opportunity(opp_id: str):
    opps = get_opportunities(threshold=0)
    for opp in opps:
        if opp.id == opp_id:
            update_opportunity(opp_id, {"last_viewed": None})  # trigger updated_at
            return opp
    raise HTTPException(404, f"Opportunity {opp_id} not found")


@router.post("/opportunities/{opp_id}/annotate")
def annotate_opportunity(opp_id: str, body: AnnotateRequest):
    result = update_opportunity(opp_id, {"notes": body.notes})
    if not result:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    return {"ok": True}


class PatchRequest(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/opportunities/{opp_id}")
def patch_opportunity(opp_id: str, body: PatchRequest):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    result = update_opportunity(opp_id, patch)
    if not result:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    return result


@router.delete("/opportunities/{opp_id}")
def delete_opp(opp_id: str):
    success = delete_opportunity(opp_id)
    if not success:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    return {"ok": True}


@router.post("/opportunities/{opp_id}/calibrate")
def calibrate_one_opportunity(opp_id: str):
    opp = get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    orch = get_orchestrator()
    thread = threading.Thread(target=orch.calibrate_one, args=(opp_id,), daemon=True)
    thread.start()
    return {"ok": True}


@router.post("/opportunities/{opp_id}/archive")
def archive_opp(opp_id: str):
    success = archive_opportunity(opp_id)
    if not success:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    return {"ok": True}


@router.post("/opportunities/{opp_id}/request-info")
def request_info(opp_id: str):
    result = update_opportunity(opp_id, {"deeper_research_requested": True})
    if not result:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    return {"ok": True, "queued": True}


class ChatRequest(BaseModel):
    message: str


@router.post("/opportunities/{opp_id}/chat")
def chat_opportunity(opp_id: str, body: ChatRequest):
    from backend.agents.chat import ChatAgent
    opp = get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(404, f"Opportunity {opp_id} not found")

    agent = ChatAgent()

    # Build message list from persisted chat history + new message
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in opp.user.chat
    ]
    messages.append({"role": "user", "content": body.message})

    def event_stream():
        full_response = ""
        try:
            for chunk in agent.stream_chat(opp, messages):
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            clean_text, actions = agent.parse_actions(full_response)
            # Persist messages (clean version without action tags)
            append_chat_messages(opp_id, body.message, clean_text)
            yield f"data: {json.dumps({'done': True, 'actions': actions})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


@router.delete("/opportunities/{opp_id}/chat")
def clear_chat_history(opp_id: str):
    success = clear_chat(opp_id)
    if not success:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    return {"ok": True}


@router.post("/opportunities/{opp_id}/rerate")
def rerate_one_opportunity(opp_id: str):
    opp = get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    orch = get_orchestrator()
    thread = threading.Thread(target=orch.rerate_one, args=(opp_id,), daemon=True)
    thread.start()
    return {"ok": True}


class RerateWithContextRequest(BaseModel):
    chat_context: list[dict] = []


@router.post("/opportunities/{opp_id}/rerate-with-context")
def rerate_one_with_context(opp_id: str, body: RerateWithContextRequest):
    opp = get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    orch = get_orchestrator()
    thread = threading.Thread(
        target=orch.rerate_one_with_context, args=(opp_id, body.chat_context), daemon=True
    )
    thread.start()
    return {"ok": True}


class DeepResearchRequest(BaseModel):
    task: str


@router.post("/opportunities/{opp_id}/deep-research")
def deep_research_opportunity(opp_id: str, body: DeepResearchRequest):
    opp = get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(404, f"Opportunity {opp_id} not found")
    orch = get_orchestrator()
    thread = threading.Thread(target=orch.deep_research_one, args=(opp_id, body.task), daemon=True)
    thread.start()
    return {"ok": True}


@router.get("/settings")
def get_settings():
    return get_db_settings()


@router.patch("/settings")
def update_settings(body: dict):
    return update_db_settings(body)


@router.post("/cycle/run")
def trigger_cycle():
    orch = get_orchestrator()
    if orch._cycle_running:
        return {"ok": False, "message": "Cycle already running"}
    thread = threading.Thread(target=orch.run_daily_cycle, daemon=True)
    thread.start()
    return {"ok": True, "message": "Cycle started"}


@router.get("/cycle/status")
def cycle_status():
    return get_orchestrator().get_status()


@router.post("/cycle/abort")
def abort_cycle():
    """Force-reset a stuck cycle. Clears both in-memory and DB flags."""
    orch = get_orchestrator()
    orch._cycle_running = False
    update_db_settings({"cycle_running": False})
    return {"ok": True}


@router.post("/opportunities/rerate")
def rerate_opportunities():
    orch = get_orchestrator()
    if orch._cycle_running:
        return {"ok": False, "message": "Cycle already running"}
    thread = threading.Thread(target=orch.rerate_all, daemon=True)
    thread.start()
    return {"ok": True, "message": "Re-rating started"}


@router.post("/opportunities/deduplicate")
def deduplicate():
    from backend.models.database import deduplicate_opportunities
    removed = deduplicate_opportunities()
    return {"ok": True, "removed_count": len(removed), "removed": removed}


class RerateThresholdRequest(BaseModel):
    threshold: float = 75.0


@router.post("/opportunities/rerate-calibrate")
def rerate_calibrate(body: RerateThresholdRequest):
    orch = get_orchestrator()
    if orch._cycle_running:
        return {"ok": False, "message": "Cycle already running"}
    thread = threading.Thread(target=orch.rerate_above_threshold, args=(body.threshold,), daemon=True)
    thread.start()
    return {"ok": True, "message": f"Calibrated rerate started for score >= {body.threshold}"}


@router.get("/imports")
def list_imports():
    return load_db().imports


@router.get("/debug/ping")
def debug_ping():
    """Test Tavily search and LLM connectivity from the server's environment."""
    from backend.agents.base import BaseAgent
    from backend.config import settings

    results: dict = {
        "tavily_key_set": bool(settings.tavily_api_key),
        "llm_key_set": bool(settings.llm_api_key),
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
    }

    # Test Tavily — call raw to inspect full response
    try:
        from tavily import TavilyClient
        tc = TavilyClient(api_key=settings.tavily_api_key)
        raw = tc.search(query="startup software 2025", max_results=2, search_depth="basic")
        hits = raw.get("results", [])
        results["tavily_ok"] = True
        results["tavily_results"] = len(hits)
        results["tavily_sample"] = hits[0].get("title", "") if hits else ""
        results["tavily_raw_keys"] = list(raw.keys())
    except Exception as e:
        results["tavily_ok"] = False
        results["tavily_error"] = str(e)

    # Test LLM — inspect raw message fields
    try:
        from openai import OpenAI
        llm = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, timeout=30.0)
        response = llm.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "Reply with exactly the word: OK"}],
            max_tokens=20,
        )
        msg = response.choices[0].message
        results["llm_ok"] = True
        results["llm_content"] = msg.content or ""
        results["llm_reasoning_content"] = getattr(msg, "reasoning_content", None) or ""
        results["llm_msg_fields"] = [k for k in dir(msg) if not k.startswith("_")]
        # what _call() would return after fix
        content = msg.content or ""
        if not content.strip():
            content = getattr(msg, "reasoning_content", "") or ""
        results["llm_effective_response"] = content[:200]
    except Exception as e:
        results["llm_ok"] = False
        results["llm_error"] = str(e)

    return results


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    orch = get_orchestrator()
    if orch._cycle_running:
        raise HTTPException(409, "A cycle or upload is already running")

    content = await file.read()
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "pdf":
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except Exception as e:
            raise HTTPException(400, f"Could not parse PDF: {e}")
    else:
        # .md / .txt — plain text
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            raise HTTPException(400, f"Could not read file: {e}")

    if not text.strip():
        raise HTTPException(400, "File appears to be empty or unreadable")

    thread = threading.Thread(
        target=orch.process_upload, args=(text, filename), daemon=True
    )
    thread.start()
    return {"ok": True, "message": f"Processing '{filename}' — pipeline running"}


