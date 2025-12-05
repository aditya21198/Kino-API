import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, BackgroundTasks
from models import ManualPostInvoiceKino
from services import end_of_month_job
from kino.kino_api import ids_post_invoice
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

app = FastAPI()

scheduler = AsyncIOScheduler()
scheduler.start()


# CRON JOB: Jalan tiap akhir bulan jam 23:59
scheduler.add_job(
    end_of_month_job,
    CronTrigger(day="last", hour=23, minute=59),
    id="monthly_job",
    replace_existing=True
)


@app.post("/submit-order")
async def submit_order(payload: ManualPostInvoiceKino, background_tasks: BackgroundTasks):
    # Convert Pydantic object to dict
    data_dict = payload.dict()

    # Add to background job
    background_tasks.add_task(ids_post_invoice, data_dict)

    return {
        "status": "processing",
        "message": "Request accepted and is being processed in background."
    }
