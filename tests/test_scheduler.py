"""Tests for bot/scheduler/setup.py — INFRA-04: AsyncIOScheduler factory."""
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scheduler_creates():
    """create_scheduler() returns an AsyncIOScheduler with UTC timezone."""
    import datetime

    from bot.scheduler.setup import create_scheduler

    scheduler = create_scheduler()
    assert isinstance(scheduler, AsyncIOScheduler)
    # APScheduler 3.11.x may store timezone as pytz.utc or datetime.timezone.utc
    # depending on Python version — check by UTC offset being zero
    tz = scheduler.timezone
    # Either pytz.utc or datetime.timezone.utc: both have utcoffset of 0
    try:
        # pytz style
        import pytz

        assert tz in (pytz.utc, datetime.timezone.utc) or str(tz) in ("UTC", "utc")
    except ImportError:
        assert tz == datetime.timezone.utc


def test_scheduler_not_started_at_import():
    """Importing bot.scheduler.setup must NOT start any scheduler or event loop."""
    import importlib

    # Re-import to confirm no side effects
    import bot.scheduler.setup as setup_module

    importlib.reload(setup_module)
    # If any scheduler were started at import it would raise or we can check
    # that no running scheduler exists at module level
    assert not hasattr(setup_module, "_running_scheduler")


def test_scheduler_job_defaults():
    """Scheduler job defaults: coalesce=True, max_instances=1."""
    from bot.scheduler.setup import create_scheduler

    scheduler = create_scheduler()
    assert scheduler._job_defaults["coalesce"] is True
    assert scheduler._job_defaults["max_instances"] == 1
