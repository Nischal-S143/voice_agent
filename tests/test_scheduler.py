from app.scheduler.scheduler import create_scheduler


class CallbackService:
    async def process_due(self) -> bool:
        return False


def test_scheduler_registers_one_coalesced_nonoverlapping_job() -> None:
    scheduler = create_scheduler(CallbackService(), 15)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "process-due-callbacks"
    assert job.max_instances == 1
    assert job.coalesce is True
