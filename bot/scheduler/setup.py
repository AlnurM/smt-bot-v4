"""APScheduler factory — creates AsyncIOScheduler with MemoryJobStore."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore


def create_scheduler() -> AsyncIOScheduler:
    """
    Creates an AsyncIOScheduler with an in-memory job store.

    Call scheduler.start() inside async main() — NOT at module import time.
    Jobs are registered in Phase 2 (Market Scanner).

    Job defaults:
      - coalesce=True      : merge missed runs into one execution
      - max_instances=1    : no concurrent execution of the same job
      - misfire_grace_time=60 : allow 60-second late execution window
    """
    jobstores = {"default": MemoryJobStore()}
    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        },
        timezone="UTC",
    )
    return scheduler
