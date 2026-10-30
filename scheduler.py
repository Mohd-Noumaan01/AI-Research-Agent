import os
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from processing import run_research
from database import get_last_run_time

# Load environment settings
load_dotenv()

# Read schedule time from .env, default to 09:00
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

# Scheduler instance
scheduler = BackgroundScheduler()


def scheduled_job():
    """Runs research and handles exceptions so future runs continue."""
    print("\n[Scheduler] Starting scheduled research run...")
    try:
        counts = run_research(max_topics=10)
        print(f"[Scheduler] Finished successfully: {counts}")
    except Exception as e:
        print(f"[Scheduler] Error during scheduled run: {e}")


def catch_up_if_missed():
    """Runs research in a background thread if last run was > 24 hours ago or never."""
    last_time_str = get_last_run_time()

    if not last_time_str:
        print("[Scheduler] Catch-up run started: No previous run found.")
        threading.Thread(target=scheduled_job, daemon=True).start()
        return

    try:
        # SQLite CURRENT_TIMESTAMP is UTC format 'YYYY-MM-DD HH:MM:SS'
        last_dt = datetime.fromisoformat(last_time_str.replace("Z", ""))
        now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        hours_diff = (now_dt - last_dt).total_seconds() / 3600.0

        if hours_diff >= 24.0:
            print(f"[Scheduler] Catch-up run started: Last run was {hours_diff:.1f} hours ago (> 24h).")
            threading.Thread(target=scheduled_job, daemon=True).start()
        else:
            print(f"[Scheduler] Last run was {hours_diff:.1f} hours ago, no catch-up needed.")
    except Exception as e:
        print(f"[Scheduler] Catch-up run started (timestamp check fallback): {e}")
        threading.Thread(target=scheduled_job, daemon=True).start()


def start_scheduler():
    """Starts the background scheduler if not already running."""
    if not scheduler.running:
        trigger = CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE)
        scheduler.add_job(
            scheduled_job,
            trigger=trigger,
            id="daily_research",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        scheduler.start()
        print(f"[Scheduler] Running daily at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}")


def stop_scheduler():
    """Shuts down the background scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
