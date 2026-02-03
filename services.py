import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from datetime import datetime,timedelta
import calendar
from kino.kino_api import ids_post_invoice,post_stock
from fastapi import FastAPI, BackgroundTasks

def get_start_and_last_day_of_the_month():
    today = datetime.today()
    year = today.year
    month = today.month

    start_day = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_day = datetime(year, month, last_day)
    return start_day,end_day

def end_of_month_job():
    start_day, end_day = get_start_and_last_day_of_the_month()

    start_str = start_day.strftime("%Y-%m-%d")
    end_str = end_day.strftime("%Y-%m-%d")

    payload = {
        "ORDER_REF": "",
        "START_DATE": start_str,
        "END_DATE": end_str
    }
    ids_post_invoice(data_dict=payload)

def end_of_the_day_invoice_job():
    yesterday = datetime.now() - timedelta(days=1)
    transaction_date = yesterday.date().strftime("%Y-%m-%d")
    payload = {
        "START_DATE":transaction_date,
        "END_DATE":transaction_date
    }
    ids_post_invoice(data_dict=payload)

def end_of_the_day_stock_job():
    yesterday = datetime.now() - timedelta(days=1)
    transaction_date = yesterday.date().strftime("%Y-%m-%d")
    post_stock_param ={
        "date":transaction_date,
        "item_code":None,
        "warehouse":None
    }
    post_stock(data=post_stock_param)