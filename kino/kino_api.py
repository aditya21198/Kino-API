import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from models import KinoPostStock
from dotenv import load_dotenv
import os
from datetime import datetime
from database import execute_query_fetch,get_price_list
import pprint
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import difflib
from log_handler.logs import KinoLogger
import re
from kino.kino_api_test import mock_data
from fastapi.encoders import jsonable_encoder

logger = KinoLogger("kino_api_logs")

load_dotenv()

def get_kino_config():
    kino_config = {
        'kino_host':None,
        'kino_client_id':None,
        'kino_client_secret':None
    }
    query = """
        SELECT *
        FROM tabSingles 
        WHERE doctype = 'Kino API Settings'
        AND field IN ('kino_client_id','kino_client_secret','kino_host')
    """
    result = execute_query_fetch(query=query)
    if result:
        for row in result:
            if row.get('field') == "kino_host":
                kino_config['kino_host'] = row.get('value')
            if row.get('field') == 'kino_client_id':
                kino_config['kino_client_id'] = row.get('value')
            if row.get('field') == 'kino_client_secret':
                kino_config['kino_client_secret'] = row.get('value')
    return kino_config


def login():
    # if using env
    # url = os.getenv("KINO_GET_LOGIN_URL")
    # client_id = os.getenv("KINO_CLIENT_ID")
    # client_secret = os.getenv("KINO_CLIENT_SECRET")

    url = get_kino_config().get("kino_host")+'oauth/token'
    client_id = get_kino_config().get("kino_client_id")
    client_secret = get_kino_config().get("kino_client_secret")
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "*"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
        print(response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Login API Error:", str(e))
        print("Response text:", getattr(e.response, "text", ""))
        return None
    

def get_customer_code(store:str,channel:str,region_id:str):
    query = """
    SELECT
        store,
        channel,
        cm_region,
        cm_entity,
        cm_branch,
        cm_cust_code1,
        cm_cust_code2,
        cm_cust_name 
    FROM `tabCustomer Mapping Detail`
    WHERE parent = 'Kino API Settings'
    """
    try:
        customers_mapping = execute_query_fetch(query=query)
        lower_store = store.lower()
        lower_channel = channel.lower()
        found = False
        for customer in customers_mapping:
            if customer.get('store') == lower_store and customer.get('channel') == lower_channel and region_id == customer.get('cm_region'):
                found = True
                return customer.get('cm_cust_code1'),customer.get('cm_cust_code2'),customer.get('cm_entity'),customer.get('cm_branch')
        if not found:
            raise Exception (f"Customer Code with store {store} and channel {channel} not found")
    except Exception as e:
        raise Exception (f"Customer Code with store {store} and channel {channel} not found")

def remove_kn(item_code: str):
    if item_code.startswith("KN"):
        return item_code[2:]
    return item_code

def get_salesman_code():
    query = """
    SELECT gms_region,gms_entity,gms_branch,gms_salesman_id,gms_salesman_name 
    FROM `tabSalesman Mapping Detail`
    WHERE parent = 'Kino API Settings'
    """
    salesman_mapping = execute_query_fetch(query=query)
    if salesman_mapping:
        return salesman_mapping[0]
    raise Exception ("Salesman Not Found in Salesman mapping")

def get_price_list_item(item:str,price_list:str):
    result = get_price_list(item_code=item,price_list=price_list)
    return result

def grouped_data_by_order_id(query_result:list):
    grouped_data ={}
    try:
        for row in query_result:
            order_id = row.get('name')
            if not order_id:
                continue

            if order_id not in grouped_data:
                grouped_data[order_id] = []
            
                # get Region Code
                sub_brand = row.get("sub_brand")
                if sub_brand:
                    if sub_brand.lower() == "maxlife":
                        region_code = "1002"
                    else:
                        region_code = "1000"
                else:
                    region_code = "1000"
                
                # Formated Customer Name
                store = row.get('store',None)
                channel = row.get('channel',None)

                cust_code1 = get_customer_code(store=store,channel=channel,region_id=region_code)[0]
                cust_code2 = get_customer_code(store=store,channel=channel,region_id=region_code)[1]
                entity_code = get_customer_code(store=store,channel=channel,region_id=region_code)[2]
                branch_code = get_customer_code(store=store,channel=channel,region_id=region_code)[3]
                print(get_customer_code(store=store,channel=channel,region_id=region_code))
                print("customer\n")
                salesman_code = get_salesman_code()['gms_salesman_id']

                transaction_date = row.get("transaction_date").isoformat() if row.get("transaction_date",None) else None

                grouped_data[order_id].append({
                    'REGION_CODE':region_code,
                    'BRANCH_CODE':branch_code,
                    'ENTITY_CODE':str(entity_code),
                    'CUST_CODE1':cust_code1,
                    'CUST_CODE2':cust_code2,
                    'SALESMAN_CODE':salesman_code,
                    'INV_TYPE':"INV02",
                    'ORDER_REF':row.get("name",None),
                    'ORDER_DATE':transaction_date,
                    'SFA_TGLORDER':transaction_date,
                    'SFA_ORDERNO':row.get("name",None),
                    'SFA_SLSNO':salesman_code
                })
        return grouped_data
    except Exception as error:
        raise Exception(traceback.format_exc())
        


def group_details_by_order_id(query_result: list):
    grouped_detail = {}
    try:

        for row in query_result:
            order_id = row.get('name')
            if not order_id:
                continue

            if order_id not in grouped_detail:
                grouped_detail[order_id] = []

            price_list_rate = row.get('price_list_rate_dbp',None)

            grouped_detail[order_id].append({
                'PCODE': remove_kn(row.get('item_code')),
                'PRICE': price_list_rate,
                'LINETYPE': 'N',
                'QTY': row.get('quantity'),
                'GROSS': row.get('total_amount'),

                'DISC_ID1': "",
                'DISC_PRINCIPAL_PCT1': 0.0,
                'DISC_PRINCIPAL_VAL1': 0.0,
                'DISC_DIST_PCT1': "1",
                'DISC_DIST_VAL1': "",

                'DISC_ID2': "",
                'DISC_PRINCIPAL_PCT2': 0.0,
                'DISC_PRINCIPAL_VAL2': 0.0,
                'DISC_DIST_PCT2': 0.0,
                'DISC_DIST_VAL2': 0.0,

                'DISC_ID3': "",
                'DISC_PRINCIPAL_PCT3': 0.0,
                'DISC_PRINCIPAL_VAL3': 0.0,
                'DISC_DIST_PCT3': 0.0,
                'DISC_DIST_VAL3': 0.0,

                'DISC_ID4': "",
                'DISC_PRINCIPAL_PCT4': 0.0,
                'DISC_PRINCIPAL_VAL4': 0.0,
                'DISC_DIST_PCT4': 0.0,
                'DISC_DIST_VAL4': 0.0,

                'DISC_ID5': "",
                'DISC_PRINCIPAL_PCT5': 0.0,
                'DISC_PRINCIPAL_VAL5': 0.0,
                'DISC_DIST_PCT5': 0.0,
                'DISC_DIST_VAL5': 0.0,

                'DISC_ID6': "",
                'DISC_PRINCIPAL_PCT6': 0.0,
                'DISC_PRINCIPAL_VAL6': 0.0,
                'DISC_DIST_PCT6': 0.0,
                'DISC_DIST_VAL6': 0.0,

                'TAX_AMT': row.get('tax_amount', 0.0),
                'NET': row.get('total_amount', 0.0),
                'DISC_TOTAL': 0.0
            })
        return grouped_detail
    except Exception as error:
        raise Exception (traceback.format_exc())

def build_payload(result: list):
    try:
        grouped_data = grouped_data_by_order_id(query_result=result)
        grouped_detail = group_details_by_order_id(query_result=result)

        payloads = []

        for key in grouped_data:
            # buat header baru untuk setiap order
            header = {
                "INTERFACEID": "T007",
                "CLIENTID": "12",
                "DATA": []
            }
            order_header = grouped_data[key][0]
            details = grouped_detail.get(key, [])
            order_header["DETAIL"] = details
            header["DATA"].append(order_header)
            payloads.append(header)

        return payloads
    except Exception as error:
        raise Exception (traceback.format_exc())
    


def create_post_invoice_payload(order_ref:str = None,start_date:str = None,end_date:str = None):
    conditions = []
    if order_ref:
        conditions.append(f"AND calc.name = '{order_ref}'")

    condition_sql = " ".join(conditions) if conditions else ""
    query = f"""
        SELECT
            calc.name,
            calc.po_no,
            calc.transaction_date,
            calc.grand_total as grand_total_with_vat,
            calc.master_bundle_item,
            calc.item_code,
            calc.sub_brand,
            calc.quantity,
            calc.harga_jual,
            calc.total_amount,
            CAST(calc.total_amount * 0.11 AS DECIMAL(20,4)) as tax_amount,
            CAST(calc.total_amount * 1.11 AS DECIMAL(20,4)) as amount,
            calc.is_bundle_item,
            calc.store,
            calc.channel,
            calc.price_list_rate_dbp
        FROM (
                SELECT
                    so.name,
                    so.po_no,
                    so.transaction_date,
                    so.grand_total,
                    COALESCE(pi.parent_item, "") as master_bundle_item,
                    COALESCE(pi.item_code, soi.item_code) as item_code,

                    COALESCE(pi.qty, soi.qty) - COALESCE(soi.returned_qty, 0) as quantity,

                    CAST(COALESCE(soi.rate * pi.qty / pi_totals.total_qty, soi.rate) AS DECIMAL(20,4)) as harga_jual,

                    CAST(
                            COALESCE((soi.rate / pi_totals.total_qty) * pi.qty, soi.rate * soi.qty)
                            AS DECIMAL(20,4)
                        )
                        * (
                            (COALESCE(pi.qty, soi.qty) - COALESCE(soi.returned_qty, 0))
                            / COALESCE(pi.qty, soi.qty)
                        ) as total_amount,
                    (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    WHERE ip.item_code = COALESCE(pi.item_code, soi.item_code)
                    AND ip.price_list = 'DBP'
                    AND ip.valid_from <= so.transaction_date
                    ORDER BY ip.valid_from DESC
                    LIMIT 1
                    ) AS price_list_rate_dbp,

                    CASE WHEN pi.item_code IS NOT NULL THEN 1 ELSE 0 END as is_bundle_item,

                    JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].store')) AS store,
                    JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].channel')) AS channel,

                    soi.idx,
                    it.sub_brand,
                    COALESCE(pi.idx, 0) as pi_idx

                FROM aladdin.`tabSales Order Item` soi
                    INNER JOIN aladdin.`tabSales Order` so
                        ON soi.parent = so.name

                    LEFT JOIN aladdin.`tabPacked Item` pi
                        ON pi.parent = so.name AND pi.parent_item = soi.item_code

                    LEFT JOIN aladdin.`tabItem` it
                        ON pi.item_code = it.item_code

                    LEFT JOIN (
                        SELECT parent, parent_item, SUM(qty) as total_qty
                        FROM aladdin.`tabPacked Item`
                        GROUP BY parent, parent_item
                    ) pi_totals
                        ON pi_totals.parent = so.name
                        AND pi_totals.parent_item = soi.item_code

                    LEFT JOIN logs.erpnext_arbi_titipaja_api_log api_log
                        ON api_log.po_no = so.po_no
                        AND api_log.title = 'Price Detail'
                        AND api_log.created_at = (
                            SELECT MAX(created_at)
                            FROM logs.erpnext_arbi_titipaja_api_log l2
                            WHERE l2.po_no = so.po_no
                            AND l2.title = 'Price Detail'
                        )

                WHERE soi.brand = 'Kino'
                AND so.docstatus = 1
                AND so.transaction_date >= %s
                AND so.transaction_date <= %s
            ) calc

        WHERE calc.quantity != 0
        {condition_sql}
        ORDER BY calc.po_no, calc.name, calc.idx, calc.pi_idx;
    """
    try:
        # result = execute_query_fetch(query=query,params=(start_date,end_date))
        # payloads = build_payload(result=result)
        # for test
        payloads = mock_data()

        return payloads
    except Exception as error:
        raise Exception(traceback.format_exc())

def send_single_invoice(url: str, headers: dict, payload: json):
    try:
        response = requests.post(url, json=payload, headers=headers)

        log_data = {
            "url": url,
            "title": "SEND_SINGLE_INVOICE",
            "order_ref":payload['DATA'][0]['ORDER_REF'],
            "method": "POST",
            "status_code": response.status_code if response else None,
            "request": payload,
            "kino_status":response.json().get("STATUSDESC", None),
            "response": response.text if response else None
        }

        if response.status_code == 200:
            logger.log(log_data)
            print(f"Success Send {response.text}")
            return {"status": "success", "payload": payload, "response": response.text}

        # kalau status bukan 200 → tetap log
        logger.log(log_data)
        return {"status": "failed", "payload": payload, "response": response.text}

    except Exception as e:
        err_text = e
        logger.log({
            "url": url,
            "title": "SEND_SINGLE_INVOICE_ERROR",
            "order_ref":payload['DATA'][0]['ORDER_REF'],
            "method": "POST",
            "status_code": 500,
            "kino_status":response.json().get("STATUSDESC",None),
            "request": payload,
            "response": e
        })
        print("Error sending payload:", err_text)
        return {"status": "error", "payload": payload, "response": str(e)}


def ids_post_invoice(data_dict:dict):
    token = login()['access_token']
    # if using env
    # url = os.getenv("KINO_IDS_POST_INVOICE_URL")
    url = get_kino_config().get('kino_host')+'api/ids/extclient/masterpayload'
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    order_ref = None
    start_date = None
    end_date = None
    if data_dict:
        order_ref = data_dict.get('ORDER_REF',None)
        start_date = data_dict.get('START_DATE',None)
        end_date = data_dict.get('END_DATE',None)
    try:
        payloads = create_post_invoice_payload(order_ref=order_ref,start_date=start_date,end_date=end_date)
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            # max_workers=10 → 10 thread paralel
            future_to_payload = {
                executor.submit(send_single_invoice, url, headers, payload): json.dumps(payload)
                for payload in payloads
            }

            for future in as_completed(future_to_payload):
                results.append(future.result())
        # debug
        # print(results)
        # print('result\n')
        return results


    except Exception as error:
        print(traceback.format_exc(),error)
        err_text = traceback.format_exc()
        logger.log({
            "url": url,
            "title": "INVOICE_ERROR",
            "order_ref":None,
            "method": "POST",
            "status_code": 500,
            "kino_status":None,
            "request": None,
            "response": err_text
        })
        
        return None

def get_all_balance_kino_item(item_code: str = None, warehouse: str = None):
    conditions = """
        WHERE it.brand = 'KINO'
        AND sle.docstatus = 1
    """

    params = []

    if item_code:
        conditions += " AND sle.item_code = %s"
        params.append(item_code)

    if warehouse:
        conditions += " AND sle.warehouse = %s"
        params.append(warehouse)

    query = f"""
        SELECT
            sle.item_code,
            sle.warehouse,
            SUM(sle.actual_qty) AS balance
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` it ON it.name = sle.item_code
        {conditions}
        GROUP BY sle.item_code, sle.warehouse
        HAVING balance <> 0
    """
    return execute_query_fetch(query=query, params=tuple(params))


def create_stock_payload(item_code:str=None,warehouse:str=None):
    whloc1 = "4001",
    whloc2 = "01",
    header = {
    "INTERFACEID": "T006",
    "CLIENTID": "12",
    "DATA":[]
    }
    detail = []
    kino_stock_balance = get_all_balance_kino_item(item_code=item_code,warehouse=warehouse)
    for kino_stock in kino_stock_balance:
        item_code = remove_kn(kino_stock.get('item_code'))
        detail.append({
            "PRDCODE": item_code,
            "WHLOC1": whloc1,
            "WHLOC2": whloc2,
            "QTY": kino_stock.get('balance')
        })
    header['DATA'].append({
        'DETAIL':detail
    })
    return header
    

def post_stock(data: KinoPostStock):
    try:
        item_code = None
        warehouse = None
        if data:
            item_code = data.get('item_code',None)
            warehouse = data.get('warehouse',None)
        payloads = create_stock_payload(item_code = item_code,warehouse=warehouse)

        token = login()['access_token']
        print(token)
        base_url = get_kino_config().get('kino_host')
        url = f"{base_url}api/ids/extclient/masterpayload"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        # Convert Pydantic model → JSON
        payload = json.dumps(payloads)
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        print(response.json())

        # Handle HTTP errors
        response.raise_for_status()
        logger.log({
            "url": url,
            "title": "POST_IDS_STOCK",
            "method": "POST",
            "status_code": response.status_code,
            "kino_status":response.json().get("STATUSDESC",None),
            "request": payload,
            "response": response.json()
        })

        return {
            "status": "success",
            "code": response.status_code,
            "response": response.json()
        }

    except requests.exceptions.HTTPError as http_err:
        logger.log({
            "url": url,
            "title": "POST_IDS_STOCK",
            "method": "POST",
            "status_code": response.status_code,
            "kino_status":response.json().get("STATUSDESC",None),
            "request": payload,
            "response": response.json()
        })
        return {
            "status": "http_error",
            "error": str(http_err),
            "response": response.text if 'response' in locals() else None
        }

    except Exception as e:
        logger.log({
            "url": url,
            "title": "POST_IDS_STOCK",
            "method": "POST",
            "status_code": response.status_code,
            "kino_status":response.json().get("STATUSDESC",None),
            "request": payload,
            "response": response.json()
        })
        return {
            "status": "error",
            "error": str(e)
        }

    

# test only
if __name__ == '__main__':
    try:
        print(create_stock_payload())
    except Exception as e:
        print(f"{datetime.now()} : Error in main function", flush=True)
        print(traceback.format_exc())
