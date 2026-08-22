from apscheduler.schedulers.asyncio import AsyncIOScheduler


def create_scheduler(callback_service: object, poll_seconds: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        callback_service.process_due,
        "interval",
        seconds=poll_seconds,
        id="process-due-callbacks",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
