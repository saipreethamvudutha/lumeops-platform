"""
Background Task Scheduler for periodic maintenance.

LEARNING NOTE — Why APScheduler Instead of Celery?

    Celery requires a separate worker process, message broker configuration,
    and adds deployment complexity. For periodic tasks that run within the
    same process, APScheduler is simpler:

    1. NO EXTRA PROCESS: Runs inside the FastAPI event loop
    2. NO EXTRA INFRA: No Celery broker config needed (Redis is already
       used for pub/sub, but Celery would need a dedicated Redis DB)
    3. SIMPLER DEBUGGING: Tasks run in the same process, same logs
    4. ASYNC NATIVE: APScheduler's AsyncIOScheduler integrates with
       FastAPI's async event loop seamlessly

    When to switch to Celery:
    - Tasks that take > 30 seconds (could block the event loop)
    - Tasks that need horizontal scaling (multiple workers)
    - Tasks that need retry/failure tracking infrastructure
    - CPU-intensive tasks (data processing, ML training)

    For our retention cleanup (DELETE queries) and snapshot computation,
    APScheduler is the right choice — these are I/O-bound database
    operations that complete in seconds.

Current scheduled tasks:
    1. retention_cleanup: Daily at 2 AM UTC — deletes expired data
    2. (Future) snapshot_computation: Hourly — pre-computes model metrics
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import async_session_factory
from app.core.logging import get_logger

logger = get_logger("scheduler")

scheduler = AsyncIOScheduler()


async def run_retention_cleanup():
    """
    Periodic task: clean up expired data for all tenants.

    Runs daily at 2 AM UTC. Each tenant's retention policy is respected:
    - Inferences older than inference_retention_days → deleted
    - Resolved alerts older than alert_retention_days → deleted
    - Webhook deliveries older than webhook_delivery_retention_days → deleted

    Only tenants with at least one policy configured are processed.
    """
    from app.services.data_retention import DataRetentionService

    logger.info("scheduled_retention_cleanup_starting")

    try:
        async with async_session_factory() as session:
            service = DataRetentionService(session)
            summaries = await service.cleanup_all_tenants(dry_run=False)
            await session.commit()

            total_deleted = sum(s.get("total_deleted", 0) for s in summaries)
            logger.info(
                "scheduled_retention_cleanup_completed",
                tenants_processed=len(summaries),
                total_records_deleted=total_deleted,
            )
    except Exception as e:
        logger.error(
            "scheduled_retention_cleanup_failed",
            error=str(e),
        )


def setup_scheduler():
    """
    Configure and start the background scheduler.

    Called during application startup (lifespan).
    """
    # Retention cleanup: daily at 2:00 AM UTC
    scheduler.add_job(
        run_retention_cleanup,
        trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="retention_cleanup",
        name="Daily data retention cleanup",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )

    scheduler.start()
    logger.info(
        "scheduler_started",
        jobs=len(scheduler.get_jobs()),
    )


def shutdown_scheduler():
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
