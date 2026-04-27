import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from datetime import datetime,timedelta
import calendar
from kino.new_kino_api import ids_post_invoice,post_stock,load_dbp_cache,repost_failed_invoice
from fastapi import FastAPI, BackgroundTasks
from database import execute_query_fetch
import json

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

def post_load_dbp_asi(data_dict:dict):
    load_dbp_cache(end_date=data_dict.get("end_date"))

def check_retur_so(so_no):
    new_so_no = ""
    splited_so = so_no.split("-")
    count_so_len = len(splited_so)
    if count_so_len > 4:
        new_so_no = "-".join(splited_so[:-1])
    else:
        new_so_no = so_no
    return new_so_no

def resend_kino_invoice():
    yesterday = datetime.now() - timedelta(days=1)
    transaction_date = yesterday.date().strftime("%Y-%m-%d")
    query = f"""
        select distinct(order_ref)
        from logs.kino_api_logs
        where date(created_at) = '{transaction_date}'
        and order_ref is not null
        and response not like '%%SFA_ORDERNO ALREADY EXISTS%%'
        and (kino_status is null or kino_status = 'error')
    """
    result = execute_query_fetch(query=query)
    sos = []
    if result:
        for res in result:
            if res.get('order_ref',None):
                so_no = res.get('order_ref')
                sos.append(so_no)
    # check if so number already sucess from previous transaction in log
    so_success = []
    if sos:
        sku_placeholders = ",".join(["%s"] * len(sos))
        param = tuple(sos)
        query = f"""
            SELECT order_ref
            FROM logs.kino_api_logs
            WHERE order_ref in ({sku_placeholders})
            and kino_status = 'success'
        """
        result = execute_query_fetch(query=query,params=param)
        if result:
            for r in result:
                so_success.append(r.get('order_ref'))
    failed_so = []
    for so in sos:
        if so not in so_success:
            main_so = check_retur_so(so)
            failed_so.append(main_so)
    payload = {
        "ORDER_REF":[],
        "END_DATE":transaction_date,
        "ORDER_REF_LIST":failed_so
    }
    repost_failed_invoice(data_dict=payload)

def kino_get_replacement_item():
    query = f"""
    select tis.parent as item_code,tis.supplier_part_no
    from aladdin.tabItem as ti
    left join aladdin.`tabItem Supplier` as tis on tis.parent = ti.item_code
    where tis.supplier_part_no is not null
    and ti.brand = 'Kino'
    order by tis.idx asc limit 1
    """
    result = execute_query_fetch(query=query)
    if result:
        return

if __name__ == "__main__":
    resend_kino_invoice()


