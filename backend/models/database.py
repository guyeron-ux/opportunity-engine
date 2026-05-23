from __future__ import annotations
import json
import logging
import re
from datetime import datetime, date
from filelock import FileLock

from backend.config import settings
from backend.models.opportunity import DatabaseModel, OpportunityEntry

log = logging.getLogger("database")

_LOCK_PATH = str(settings.opportunities_file) + ".lock"
_REDIS_KEY = "opportunity_engine_db"

# ---------------------------------------------------------------------------
# Fuzzy duplicate detection
# ---------------------------------------------------------------------------

# Words stripped before similarity comparison — AI buzzword prefixes and
# generic product-type nouns that don't differentiate one opportunity from another
_STOP: frozenset[str] = frozenset({
    # Articles / prepositions
    'a', 'an', 'the', 'for', 'and', 'of', 'in', 'with', 'by', 'on', 'to',
    'at', 'from', 'via', 'into',
    # AI prefix words universally prepended in this space
    'ai', 'powered', 'native', 'driven', 'augmented', 'intelligent', 'smart',
    'automated', 'autonomous',
    # Generic product-type nouns that don't differentiate
    'platform', 'system', 'solution', 'tool', 'suite', 'software', 'app',
})

# Two opportunities are considered duplicates when their normalized title
# token sets share this fraction of words (Jaccard similarity)
DUPLICATE_THRESHOLD = 0.65


def _normalize_title(title: str) -> frozenset[str]:
    title = title.lower()
    title = re.sub(r'[^a-z0-9\s]', ' ', title)
    return frozenset(t for t in title.split() if t not in _STOP and len(t) > 2)


def _title_similarity(a: str, b: str) -> float:
    ta, tb = _normalize_title(a), _normalize_title(b)
    if not ta or not tb:
        return 0.0
    union = len(ta | tb)
    return len(ta & tb) / union if union else 0.0


# ---------------------------------------------------------------------------
# Storage backend: Upstash Redis (production) or local JSON file (dev)
# ---------------------------------------------------------------------------

def _redis_load() -> DatabaseModel | None:
    """Load DB from Upstash Redis REST API. Returns None on any error."""
    try:
        import httpx
        resp = httpx.get(
            f"{settings.upstash_redis_url}/get/{_REDIS_KEY}",
            headers={"Authorization": f"Bearer {settings.upstash_redis_token}"},
            timeout=10,
        )
        result = resp.json().get("result")
        if result is None:
            return DatabaseModel()
        return DatabaseModel.model_validate_json(result)
    except Exception as e:
        log.error("Redis load failed: %s", e)
        return None


def _redis_save(db: DatabaseModel) -> bool:
    """Save DB to Upstash Redis. Returns False on error."""
    try:
        import httpx
        payload = db.model_dump_json()
        # Upstash REST: POST / with ["SET", key, value] command array
        resp = httpx.post(
            f"{settings.upstash_redis_url}",
            headers={"Authorization": f"Bearer {settings.upstash_redis_token}"},
            json=["SET", _REDIS_KEY, payload],
            timeout=10,
        )
        return resp.json().get("result") == "OK"
    except Exception as e:
        log.error("Redis save failed: %s", e)
        return False


def _use_redis() -> bool:
    return bool(settings.upstash_redis_url and settings.upstash_redis_token)


# ---------------------------------------------------------------------------
# Public API — identical interface regardless of backend
# ---------------------------------------------------------------------------

def load_db() -> DatabaseModel:
    if _use_redis():
        result = _redis_load()
        if result is not None:
            return result
        log.warning("Redis unavailable, falling back to local file")

    path = settings.opportunities_file
    if not path.exists():
        return DatabaseModel()
    with FileLock(_LOCK_PATH):
        raw = json.loads(path.read_text())
    return DatabaseModel.model_validate(raw)


def save_db(db: DatabaseModel) -> None:
    if _use_redis():
        if _redis_save(db):
            return
        log.warning("Redis save failed, falling back to local file")

    path = settings.opportunities_file
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = db.model_dump(mode="json")
    with FileLock(_LOCK_PATH):
        path.write_text(json.dumps(serialized, indent=2, default=str))

    # Local backup
    backup_dir = settings.backups_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"opportunities_{date.today().isoformat()}.json"
    backup_path.write_text(json.dumps(serialized, indent=2, default=str))


def add_opportunity(opp: OpportunityEntry) -> OpportunityEntry:
    db = load_db()
    for existing in db.opportunities:
        sim = _title_similarity(opp.title, existing.title)
        if sim >= DUPLICATE_THRESHOLD:
            if opp.composite_score > existing.composite_score:
                # Incoming scores higher — replace existing
                db.opportunities.remove(existing)
                db.opportunities.append(opp)
                db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
                save_db(db)
                log.info(
                    "Replaced duplicate '%s' (%.1f) with higher-scoring '%s' (%.1f) [sim=%.2f]",
                    existing.title, existing.composite_score,
                    opp.title, opp.composite_score, sim,
                )
            else:
                log.info(
                    "Skipping duplicate '%s' (%.1f) — existing '%s' (%.1f) scores higher [sim=%.2f]",
                    opp.title, opp.composite_score,
                    existing.title, existing.composite_score, sim,
                )
            return opp
    db.opportunities.append(opp)
    db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
    save_db(db)
    return opp


def delete_opportunity(opp_id: str) -> bool:
    db = load_db()
    for lst in [db.opportunities, db.archived_opportunities]:
        for opp in lst:
            if opp.id == opp_id:
                lst.remove(opp)
                save_db(db)
                return True
    return False


def deduplicate_opportunities() -> list[dict]:
    """Scan all active opportunities for fuzzy title duplicates.
    Within each duplicate pair, keep the higher-scored one and remove the other.
    Returns a summary list of removed opportunities."""
    db = load_db()
    # Process highest-scored first so the keeper is always encountered first
    sorted_opps = sorted(db.opportunities, key=lambda o: o.composite_score, reverse=True)
    to_remove: set[str] = set()
    removed_log: list[dict] = []

    for i, a in enumerate(sorted_opps):
        if a.id in to_remove:
            continue
        for b in sorted_opps[i + 1:]:
            if b.id in to_remove:
                continue
            sim = _title_similarity(a.title, b.title)
            if sim >= DUPLICATE_THRESHOLD:
                to_remove.add(b.id)
                removed_log.append({
                    "removed_title": b.title,
                    "removed_score": round(b.composite_score, 1),
                    "kept_title": a.title,
                    "kept_score": round(a.composite_score, 1),
                    "similarity": round(sim, 2),
                })
                log.info(
                    "Dedup: removing '%s' (%.1f) in favour of '%s' (%.1f) [sim=%.2f]",
                    b.title, b.composite_score, a.title, a.composite_score, sim,
                )

    if to_remove:
        db.opportunities = [o for o in db.opportunities if o.id not in to_remove]
        save_db(db)

    return removed_log


def archive_opportunity(opp_id: str) -> bool:
    db = load_db()
    for i, opp in enumerate(db.opportunities):
        if opp.id == opp_id:
            opp.user.archived = True
            opp.user.archived_at = datetime.utcnow()
            db.archived_opportunities.append(opp)
            db.opportunities.pop(i)
            save_db(db)
            return True
    return False


def update_opportunity(opp_id: str, patch: dict) -> OpportunityEntry | None:
    db = load_db()
    for opp in db.opportunities:
        if opp.id == opp_id:
            for key, value in patch.items():
                if hasattr(opp, key):
                    setattr(opp, key, value)
                elif hasattr(opp.user, key):
                    setattr(opp.user, key, value)
            opp.updated_at = datetime.utcnow()
            save_db(db)
            return opp
    return None


def _is_pure_b2g(opp: OpportunityEntry) -> bool:
    """Returns True only for pure B2G (primary customer is government).
    Mixed (B2B/B2G, B2C/B2G) are kept — 'marginal' B2G is not filtered."""
    gtm = opp.classification.go_to_market.strip().upper()
    return gtm == "B2G"


def get_opportunities(
    filters: dict | None = None,
    threshold: int | None = None,
) -> list[OpportunityEntry]:
    db = load_db()
    opps = [o for o in db.opportunities if not o.user.archived]

    # Exclude pure B2G — marginal (mixed B2B/B2G, B2C/B2G) are kept
    opps = [o for o in opps if not _is_pure_b2g(o)]

    # Threshold is an optional caller-supplied filter only — never hide by default
    if threshold is not None:
        opps = [o for o in opps if o.composite_score >= threshold]

    if filters:
        if filters.get("types"):
            opps = [o for o in opps if o.classification.type in filters["types"]]
        if filters.get("categories"):
            opps = [o for o in opps if o.classification.category in filters["categories"]]
        if filters.get("industries"):
            opps = [o for o in opps if o.classification.industry in filters["industries"]]
        if filters.get("tech_stacks"):
            opps = [o for o in opps if any(
                t in o.classification.tech_stack for t in filters["tech_stacks"]
            )]
        if filters.get("min_score") is not None:
            opps = [o for o in opps if o.composite_score >= filters["min_score"]]
        if filters.get("max_score") is not None:
            opps = [o for o in opps if o.composite_score <= filters["max_score"]]

    return sorted(opps, key=lambda o: o.composite_score, reverse=True)


def get_db_settings() -> dict:
    return load_db().settings


def update_db_settings(patch: dict) -> dict:
    db = load_db()
    db.settings.update(patch)
    save_db(db)
    return db.settings


def get_opportunity_by_id(opp_id: str) -> "OpportunityEntry | None":
    """Direct lookup by ID — searches active, archived, and B2G opportunities."""
    db = load_db()
    for opp in db.opportunities:
        if opp.id == opp_id:
            return opp
    for opp in db.archived_opportunities:
        if opp.id == opp_id:
            return opp
    return None


def append_chat_messages(opp_id: str, user_msg: str, assistant_msg: str) -> bool:
    """Atomically append a user + assistant ChatMessage pair to an opportunity."""
    from backend.models.opportunity import ChatMessage
    db = load_db()
    for opp in db.opportunities:
        if opp.id == opp_id:
            opp.user.chat.append(ChatMessage(role="user", content=user_msg))
            opp.user.chat.append(ChatMessage(role="assistant", content=assistant_msg))
            opp.updated_at = datetime.utcnow()
            save_db(db)
            return True
    for opp in db.archived_opportunities:
        if opp.id == opp_id:
            opp.user.chat.append(ChatMessage(role="user", content=user_msg))
            opp.user.chat.append(ChatMessage(role="assistant", content=assistant_msg))
            opp.updated_at = datetime.utcnow()
            save_db(db)
            return True
    return False


def clear_chat(opp_id: str) -> bool:
    """Clear all chat messages for an opportunity."""
    db = load_db()
    for opp in db.opportunities + db.archived_opportunities:
        if opp.id == opp_id:
            opp.user.chat = []
            opp.updated_at = datetime.utcnow()
            save_db(db)
            return True
    return False


def generate_opportunity_id(db: DatabaseModel | None = None) -> str:
    if db is None:
        db = load_db()
    today = datetime.utcnow()
    date_str = today.strftime("%Y-%m%d")
    count = len(db.opportunities) + len(db.archived_opportunities) + 1
    return f"OPP-{date_str}-{count:03d}"
