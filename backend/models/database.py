from __future__ import annotations
import json
import shutil
from datetime import datetime, date
from pathlib import Path
from filelock import FileLock

from backend.config import settings
from backend.models.opportunity import DatabaseModel, OpportunityEntry


_LOCK_PATH = str(settings.opportunities_file) + ".lock"


def load_db() -> DatabaseModel:
    path = settings.opportunities_file
    if not path.exists():
        return DatabaseModel()
    with FileLock(_LOCK_PATH):
        raw = json.loads(path.read_text())
    return DatabaseModel.model_validate(raw)


def save_db(db: DatabaseModel) -> None:
    path = settings.opportunities_file
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = db.model_dump(mode="json")
    with FileLock(_LOCK_PATH):
        path.write_text(json.dumps(serialized, indent=2, default=str))
    _backup(serialized)


def _backup(data: dict) -> None:
    backup_dir = settings.backups_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"opportunities_{date.today().isoformat()}.json"
    backup_path.write_text(json.dumps(data, indent=2, default=str))


def add_opportunity(opp: OpportunityEntry) -> OpportunityEntry:
    db = load_db()
    # Deduplicate by title similarity (simple check)
    existing_titles = {o.title.lower() for o in db.opportunities}
    if opp.title.lower() in existing_titles:
        return opp
    db.opportunities.append(opp)
    db.opportunities.sort(key=lambda o: o.composite_score, reverse=True)
    save_db(db)
    return opp


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


def get_opportunities(
    filters: dict | None = None,
    threshold: int | None = None,
) -> list[OpportunityEntry]:
    db = load_db()
    opps = [o for o in db.opportunities if not o.user.archived]

    effective_threshold = threshold if threshold is not None else settings.score_threshold
    opps = [o for o in opps if o.composite_score >= effective_threshold]

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
    db = load_db()
    return db.settings


def update_db_settings(patch: dict) -> dict:
    db = load_db()
    db.settings.update(patch)
    save_db(db)
    return db.settings


def generate_opportunity_id(db: DatabaseModel | None = None) -> str:
    if db is None:
        db = load_db()
    today = datetime.utcnow()
    date_str = today.strftime("%Y-%m%d")
    count = len(db.opportunities) + len(db.archived_opportunities) + 1
    return f"OPP-{date_str}-{count:03d}"
