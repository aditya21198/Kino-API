import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, BackgroundTasks
from models import ManualPostInvoiceKino,KinoPostStock,ManualSendData,LoadDBPCache
from services import end_of_month_job,end_of_the_day_invoice_job,post_load_dbp_asi
from kino.new_kino_api import ids_post_invoice,post_stock

app = FastAPI()

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

@app.post("/post-stock")
async def ids_post_stock(payload: KinoPostStock,background_tasks:BackgroundTasks):
    data_dict = payload.dict()
    background_tasks.add_task(post_stock, data_dict)
    return {
        "status": "processing",
        "message": "Request accepted and is being processed in background."
    }

@app.post("/load_dbp_cache")
async def load_dbp_cache(payload:LoadDBPCache, background_tasks: BackgroundTasks):
    data_dict = payload.dict()
    background_tasks.add_task(post_load_dbp_asi,data_dict)
    return {
        "status": "processing",
        "message": "Request accepted and is being processed in background."
    }

