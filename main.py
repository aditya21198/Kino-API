import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, BackgroundTasks
from models import ManualPostInvoiceKino,KinoPostStock,ManualSendData,PostInvoiceData
from services import end_of_month_job,end_of_the_day_invoice_job
from kino.kino_api import ids_post_invoice,post_stock,manual_send_data,create_post_invoice_payload

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

@app.post("/manual_send_data")
async def mannual_send_data(payload:ManualSendData,background_task:BackgroundTasks):
    data_dict = payload.dict()
    background_task.add_task(manual_send_data,data_dict)
    return{
        "status": "processing",
        "message": "Request accepted and is being processed in background."
    }

@app.post("/post-invoice-data")
async def post_invoice_data(payload:PostInvoiceData, background_tasks: BackgroundTasks):
    data_dict = payload.dict()
    background_tasks.add_task(create_post_invoice_payload,data_dict)
    return {
        "status": "processing",
        "message": "Request accepted and is being processed in background."
    }

