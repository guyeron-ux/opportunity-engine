import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("scheduler")


def create_scheduler(orchestrator) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    # Daily cycle at 06:00 UTC
    scheduler.add_job(
        orchestrator.run_daily_cycle,
        CronTrigger(hour=6, minute=0),
        id="daily_cycle",
        name="Daily Opportunity Discovery",
        replace_existing=True,
    )

    # Weekly deep dive Sunday 14:00 UTC
    scheduler.add_job(
        orchestrator.run_daily_cycle,  # same cycle, could be extended later
        CronTrigger(day_of_week="sun", hour=14, minute=0),
        id="weekly_deep_dive",
        name="Weekly Deep Dive",
        replace_existing=True,
    )

    return scheduler
