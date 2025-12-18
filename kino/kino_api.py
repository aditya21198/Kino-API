import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from models import KinoPostStock
from dotenv import load_dotenv
import os
from datetime import datetime,timedelta
from database import execute_query_fetch,get_price_list,update_table
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from log_handler.logs import KinoLogger
from kino.kino_api_test import mock_data,mock_post_stock_maxlife,mock_post_stock_non_maxlife
from fastapi.encoders import jsonable_encoder
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = KinoLogger("kino_api_logs")

load_dotenv()

_KINO_CONFIG_CACHE = {}

def get_kino_config(maxlife=False, force_reload=False):
    cache_key = "maxlife" if maxlife else "normal"

    if not force_reload and cache_key in _KINO_CONFIG_CACHE:
        return _KINO_CONFIG_CACHE[cache_key]

    kino_config = {
        'kino_host': None,
        'kino_client_id': None,
        'kino_client_secret': None,
        'kino_access_token': None,
        'kino_access_token_creation': None
    }

    query = """
        SELECT field, value
        FROM tabSingles
        WHERE doctype = 'Kino API Settings'
        AND field IN (
            'kino_client_id','kino_client_secret','kino_host',
            'kino_access_token','access_token_creation',
            'kino_host_maxlife','kino_client_id_maxlife',
            'kino_client_secret_maxlife','kino_access_token_maxlife',
            'access_token_creation_maxlife'
        )
    """
    result = execute_query_fetch(query=query)

    if result:
        for row in result:
            f = row["field"]
            v = row["value"]

            if not maxlife:
                if f == "kino_host":
                    kino_config["kino_host"] = v
                elif f == "kino_client_id":
                    kino_config["kino_client_id"] = v
                elif f == "kino_client_secret":
                    kino_config["kino_client_secret"] = v
                elif f == "kino_access_token":
                    kino_config["kino_access_token"] = v
                elif f == "access_token_creation":
                    kino_config["kino_access_token_creation"] = v
            else:
                if f == "kino_host_maxlife":
                    kino_config["kino_host"] = v
                elif f == "kino_client_id_maxlife":
                    kino_config["kino_client_id"] = v
                elif f == "kino_client_secret_maxlife":
                    kino_config["kino_client_secret"] = v
                elif f == "kino_access_token_maxlife":
                    kino_config["kino_access_token"] = v
                elif f == "access_token_creation_maxlife":
                    kino_config["kino_access_token_creation"] = v

    _KINO_CONFIG_CACHE[cache_key] = kino_config
    return kino_config

def update_single(value,field):
    query = f"""
        UPDATE `tabSingles`
        SET value = '{value}'
        WHERE doctype = 'Kino API Settings'
        AND field = '{field}';
    """
    result_update = update_table(query=query)
    return result_update
    

def login(maxlife=False):
    # if using env
    # url = os.getenv("KINO_GET_LOGIN_URL")
    # client_id = os.getenv("KINO_CLIENT_ID")
    # client_secret = os.getenv("KINO_CLIENT_SECRET")
    def token_expired(token_creation):
        if not token_creation:
            return True

        # kalau disimpan string
        if isinstance(token_creation, str):
            token_creation_dt = datetime.strptime(
                token_creation, "%Y-%m-%d %H:%M:%S"
            )
        else:
            token_creation_dt = token_creation
        now = datetime.now(pytz.timezone("Asia/Jakarta")).replace(tzinfo=None)
        return now - token_creation_dt > timedelta(hours=24)

    print(f"login function called maxlife={maxlife}\n")

    url = get_kino_config(maxlife=maxlife).get("kino_host")+'oauth/token'
    client_id = get_kino_config(maxlife=maxlife).get("kino_client_id")
    client_secret = get_kino_config(maxlife=maxlife).get("kino_client_secret")
    client_token = get_kino_config(maxlife=maxlife).get("kino_access_token")
    client_token_ceration = get_kino_config(maxlife=maxlife).get("kino_access_token_creation")
    if not client_token or token_expired(client_token_ceration):
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "*"
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        print(f"payload {payload}")

        try:
            response = requests.post(url, data=payload, headers=headers,timeout=60)
            response.raise_for_status()
            print(response.json())
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if maxlife:
                update_single(response.json()['access_token'],'kino_access_token_maxlife')
                update_single(date_now,'access_token_creation_maxlife')
            else:
                update_single(response.json()['access_token'],'kino_access_token')
                update_single(date_now,'access_token_creation')
            return response.json()
        except requests.exceptions.RequestException as e:
            print("Login API Error:", str(e),flush=True)
            print("Response text:", getattr(e.response, "text", ""),flush=True)
            return None
        except Exception as e:
            print("Unexpected Error during login:", str(e),flush=True)
            return None
    else:
        return {
            "access_token": client_token
        }
        
    

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

def get_salesman_code(region_id:str):
    query = """
    SELECT gms_region,gms_entity,gms_branch,gms_salesman_id,gms_salesman_name 
    FROM `tabSalesman Mapping Detail`
    WHERE parent = 'Kino API Settings'
    """
    salesman_mapping = execute_query_fetch(query=query)
    if salesman_mapping:
        for salesman in salesman_mapping:
            if salesman['gms_region'] == region_id:
                return salesman
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
                    if sub_brand.lower() in ["maxlife","perro"]:
                        region_code = "1002"
                    else:
                        region_code = "1000"
                else:
                    region_code = "1000"
                
                # Formated Customer Name
                store = row.get('store',None)
                channel = row.get('channel',None)

                print(row.get('name',None))
                print('so name')

                cust_code1 = get_customer_code(store=store,channel=channel,region_id=region_code)[0]
                cust_code2 = get_customer_code(store=store,channel=channel,region_id=region_code)[1]
                entity_code = get_customer_code(store=store,channel=channel,region_id=region_code)[2]
                branch_code = get_customer_code(store=store,channel=channel,region_id=region_code)[3]
                salesman_code = get_salesman_code(region_id=region_code)['gms_salesman_id']

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
                'DISC_DIST_PCT1': 0.0,
                'DISC_DIST_VAL1': 0.0,

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
                "CLIENTID": None,
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
    condittion_start_date_end_date = []
    if order_ref:
        conditions.append(f"AND calc.name = '{order_ref}'")
    
    if start_date and end_date:
        condittion_start_date_end_date.append(f"AND so.transaction_date >= '{start_date}'")
        condittion_start_date_end_date.append(f"AND so.transaction_date <= '{end_date}'")

    condition_sql = " ".join(conditions) if conditions else ""
    condition_transaction_date_sql = " ".join(condittion_start_date_end_date) if condittion_start_date_end_date else ""
    query = f"""
        SELECT
            calc.name,
            calc.po_no,
            calc.transaction_date,
            calc.grand_total AS grand_total_with_vat,
            calc.master_bundle_item,
            calc.item_code,
            calc.sub_brand,
            calc.quantity,
            calc.harga_jual,
            calc.total_amount,
            CAST(calc.total_amount * 0.11 AS DECIMAL(20,4)) AS tax_amount,
            CAST(calc.total_amount * 1.11 AS DECIMAL(20,4)) AS amount,
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
                COALESCE(pi.parent_item, "") AS master_bundle_item,
                COALESCE(pi.item_code, soi.item_code) AS item_code,

                COALESCE(pi.qty, soi.qty) - COALESCE(soi.returned_qty, 0) AS quantity,

                CAST(
                    COALESCE(
                        soi.rate * pi.qty / pi_totals.total_qty,
                        soi.rate
                    ) AS DECIMAL(20,4)
                ) AS harga_jual,

                CAST(
                    COALESCE(
                        (soi.rate / pi_totals.total_qty) * pi.qty,
                        soi.rate * soi.qty
                    ) AS DECIMAL(20,4)
                )
                * (
                    (COALESCE(pi.qty, soi.qty) - COALESCE(soi.returned_qty, 0))
                    / COALESCE(pi.qty, soi.qty)
                ) AS total_amount,

                (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    WHERE ip.item_code = COALESCE(pi.item_code, soi.item_code)
                    AND ip.price_list = 'DBP'
                    AND ip.valid_from <= so.transaction_date
                    ORDER BY ip.valid_from DESC
                    LIMIT 1
                ) AS price_list_rate_dbp,

                CASE
                    WHEN pi.item_code IS NOT NULL THEN 1
                    ELSE 0
                END AS is_bundle_item,

                JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].store')) AS store,
                JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].channel')) AS channel,

                soi.idx,
                it.sub_brand,
                COALESCE(pi.idx, 0) AS pi_idx

            FROM aladdin.`tabSales Order Item` soi
            INNER JOIN aladdin.`tabSales Order` so
                ON soi.parent = so.name

            LEFT JOIN aladdin.`tabPacked Item` pi
                ON pi.parent = so.name
                AND pi.parent_item = soi.item_code

            -- 🔥 FIX UTAMA DI SINI
            LEFT JOIN aladdin.`tabItem` it
                ON it.item_code = COALESCE(pi.item_code, soi.item_code)

            LEFT JOIN (
                SELECT
                    parent,
                    parent_item,
                    SUM(qty) AS total_qty
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
            {condition_transaction_date_sql}
        ) calc
        WHERE calc.quantity != 0
        {condition_sql}
        ORDER BY calc.po_no, calc.name, calc.idx, calc.pi_idx;
    """
    try:
        result = execute_query_fetch(query=query)
        # payloads = build_payload(result=result)
        # for test
        # payloads = mock_data()

        return result
    except Exception as error:
        raise Exception(traceback.format_exc())

def send_single_invoice(payload: json):
    data = payload
    token = login(maxlife=False)['access_token']
    if data[0]['DATA'][0].get('REGION_CODE') == '1002':
        token = login(maxlife=True)['access_token']
        data[0]['CLIENTID'] = get_kino_config(maxlife=True).get('kino_client_id')
        url = get_kino_config(maxlife=True).get('kino_host')+'api/ids/extclient/masterpayload'
    else:
        data[0]['CLIENTID'] = get_kino_config(maxlife=False).get('kino_client_id')
        url = get_kino_config(maxlife=False).get('kino_host')+'api/ids/extclient/masterpayload'

    # if using env
    # url = os.getenv("KINO_IDS_POST_INVOICE_URL")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    try:
        response = requests.post(url, json=data[0], headers=headers)

        log_data = {
            "url": url,
            "title": "SEND_SINGLE_INVOICE",
            "order_ref":data[0]['DATA'][0]['ORDER_REF'],
            "method": "POST",
            "status_code": response.status_code if response else None,
            "request": data[0],
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
            "order_ref":data[0]['DATA'][0]['ORDER_REF'],
            "method": "POST",
            "status_code": 500,
            "kino_status":response.json().get("STATUSDESC",None),
            "request": data[0],
            "response": e
        })
        print("Error sending payload:", err_text)
        return {"status": "error", "payload": payload, "response": str(e)}

def get_unique_so_ref(payloads:list):
    so_refs = set()
    for payload in payloads:
        so_ref = payload.get('name')
        if so_ref:
            so_refs.add(so_ref)
    return list(so_refs)

def ids_post_invoice(data_dict: dict):
    order_ref = None
    start_date = None
    end_date = None

    try:
        if data_dict:
            order_ref = data_dict.get('ORDER_REF')
            start_date = data_dict.get('START_DATE')
            end_date = data_dict.get('END_DATE')

        raw_payloads = create_post_invoice_payload(
            order_ref=order_ref,
            start_date=start_date,
            end_date=end_date
        )

        grouped = {}
        for row in raw_payloads:
            so_ref = row.get('name')
            if not so_ref:
                continue
            grouped.setdefault(so_ref, []).append(row)

        def worker(so_ref, rows):
            try:
                payload = build_payload(rows)
                send_single_invoice(payload)
                return {"so_ref": so_ref, "status": "success"}
            except Exception:
                err_text = traceback.format_exc()
                logger.log({
                    "url": None,
                    "title": "INVOICE_ERROR",
                    "order_ref": so_ref,
                    "method": "POST",
                    "status_code": 500,
                    "kino_status": None,
                    "request": None,
                    "response": err_text
                })
                return {"so_ref": so_ref, "status": "failed"}

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(worker, so_ref, rows)
                for so_ref, rows in grouped.items()
            ]

            for future in as_completed(futures):
                try:
                    result = future.result()
                    print(f"SO {result['so_ref']} → {result['status']}")
                except Exception:
                    print(traceback.format_exc())

    except Exception:
        err_text = traceback.format_exc()
        print(err_text)
        logger.log({
            "url": None,
            "title": "INVOICE_ERROR",
            "order_ref": None,
            "method": "POST",
            "status_code": 500,
            "kino_status": None,
            "request": None,
            "response": err_text
        })

def get_all_balance_kino_item(item_code: str = None, warehouse: str = None):
    conditions = """
        WHERE it.brand = 'KINO'
        AND sle.docstatus = 1
        AND sle.item_code != 'DUMMY-OVALEMIC'
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
            SUM(sle.actual_qty) AS balance,
            it.sub_brand
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` it ON it.name = sle.item_code
        {conditions}
        GROUP BY sle.item_code, sle.warehouse
        HAVING balance <> 0
    """
    return execute_query_fetch(query=query, params=tuple(params))

def get_warehouse_mapping():
    query = """
    select warehouse,whloc1,whloc2 from `tabKino Warehouse Mapping`
    where parent = 'Kino API Settings'
    """
    result = execute_query_fetch(query=query)
    if result:
        return result
    else:
        raise Exception("Please Set Kino Warehouse Mapping")


def create_stock_payload(item_code: str = None, warehouse: str = None):
    header_maxlife = {
        "INTERFACEID": "T006",
        "CLIENTID": get_kino_config(maxlife=True).get("kino_client_id"),
        "DATA": []
    }
    print(get_kino_config(maxlife=True).get("kino_client_id"))
    print("maxlife")

    header_without_maxlife = {
        "INTERFACEID": "T006",
        "CLIENTID": get_kino_config(maxlife=False).get("kino_client_id"),
        "DATA": []
    }
    print(get_kino_config(maxlife=False).get("kino_client_id"))
    print("non maxlife")

    try:
        kino_stock_balance = get_all_balance_kino_item(
            item_code=item_code,
            warehouse=warehouse
        )
        print(kino_stock_balance)
        print("kino stock balance\n")

        warehouse_mapping = get_warehouse_mapping()

        maxlife_detail = []
        non_maxlife_detail = []

        for kino_stock in kino_stock_balance:
            whloc1 = None
            whloc2 = None

            for wh in warehouse_mapping:
                if wh.get("warehouse") == kino_stock.get("warehouse"):
                    whloc1 = wh.get("whloc1")
                    whloc2 = wh.get("whloc2")
                    break

            if not whloc1 or not whloc2:
                raise Exception(
                    f"Warehouse Mapping Not Found for warehouse {kino_stock.get('warehouse')}"
                )

            detail_row = {
                "PRDCODE": remove_kn(kino_stock.get("item_code")),
                "WHLOC1": whloc1,
                "WHLOC2": whloc2,
                "QTY": int(kino_stock.get("balance"))
            }
            if kino_stock.get("sub_brand").lower() not in ['maxlife','perro']:
                print(kino_stock.get("sub_brand"))
                print("non maxlife detail\n")
                non_maxlife_detail.append(detail_row)
            if kino_stock.get("sub_brand").lower() in ['maxlife','perro']:
                maxlife_detail.append(detail_row)

        if maxlife_detail:
            header_maxlife["DATA"].append({
                "DETAIL": maxlife_detail
            })

        if non_maxlife_detail:
            header_without_maxlife["DATA"].append({
                "DETAIL": non_maxlife_detail
            })
        
        return header_maxlife, header_without_maxlife

    except Exception:
        raise Exception(traceback.format_exc())
    

def safe_response_json(response):
    try:
        return response.json()
    except ValueError:
        return None

def post_stock(data: KinoPostStock = None):
    print("run post stock\n")
    try:
        item_code = None
        warehouse = None
        if data:
            item_code = data.get('item_code',None)
            warehouse = data.get('warehouse',None)
        header_maxlife, header_without_maxlife = create_stock_payload(item_code = item_code,warehouse=warehouse)
        # for test only
        # header_maxlife= mock_post_stock_maxlife()
        # header_without_maxlife = mock_post_stock_non_maxlife()
        if header_maxlife.get('DATA'):
            print("post maxlife\n")
            print(len(header_maxlife))
            try:
                payloads = header_maxlife
                token = login(maxlife=True)['access_token']
                print("token maxlife ok\n")
                base_url = get_kino_config().get('kino_host')
                url = f"{base_url}api/ids/extclient/masterpayload"

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
                print("jalanin request\n")
                response = requests.post(
                    url,
                    json=header_maxlife,
                    headers=headers
                )
                full_response_text = json.dumps(response.text) or ""
                resp_json = safe_response_json(response)
                # Handle HTTP errors
                response.raise_for_status()
                logger.log({
                    "url": url,
                    "title": "POST_IDS_STOCK",
                    "method": "POST",
                    "status_code": response.status_code,
                    "kino_status":resp_json.get("STATUSDESC") if resp_json else full_response_text[-10000:],
                    "request": header_maxlife,
                    "response": full_response_text[-10000:]
                })
            except requests.exceptions.HTTPError as http_err:
                base_url = get_kino_config().get('kino_host')
                url = f"{base_url}api/ids/extclient/masterpayload"
                logger.log({
                    "url": url,
                    "title": "POST_IDS_STOCK",
                    "method": "POST",
                    "status_code": response.status_code,
                    "kino_status":resp_json.get("STATUSDESC") if resp_json else full_response_text[-10000:],
                    "request": header_maxlife,
                    "response": full_response_text[-10000:]
                })
        if header_without_maxlife.get('DATA'):
            print("post non maxlife\n")
            print(len(header_without_maxlife))
            try:
                payloads = header_without_maxlife
                token = login(maxlife=False)['access_token']
                print("token non maxlife ok\n")
                base_url = get_kino_config().get('kino_host')
                url = f"{base_url}api/ids/extclient/masterpayload"

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
                print("jalanin request\n")
                response = requests.post(
                    url,
                    json=header_without_maxlife,
                    headers=headers
                )
                full_response_text = json.dumps(response.text) or ""

                resp_json = safe_response_json(response)
                print(response.text)
                # Handle HTTP errors
                response.raise_for_status()
                logger.log({
                    "url": url,
                    "title": "POST_IDS_STOCK",
                    "method": "POST",
                    "status_code": response.status_code,
                    "kino_status":resp_json.get("STATUSDESC") if resp_json else full_response_text[-10000:],
                    "request": header_without_maxlife,
                    "response": full_response_text[-10000:]
                })
            except requests.exceptions.HTTPError as http_err:
                base_url = get_kino_config().get('kino_host')
                url = f"{base_url}api/ids/extclient/masterpayload"
                logger.log({
                    "url": url,
                    "title": "POST_IDS_STOCK",
                    "method": "POST",
                    "status_code": response.status_code,
                    "kino_status":resp_json.get("STATUSDESC") if resp_json else full_response_text[-10000:],
                    "request": header_without_maxlife,
                    "response": full_response_text[-10000:]
                })
    except Exception as e:
        logger.log({
            "title": "STOCK_ERROR",
            "method": "POST",
            "status_code": None,
            "kino_status":None,
            "request": None,
            "response": traceback.format_exc()
        })
    

# test only
if __name__ == '__main__':
    try:
        header_maxlife, header_without_maxlife = create_stock_payload()
        print("Maxlife Payload:")
        print(header_maxlife)
        print("\nNon-Maxlife Payload:")
        print(header_without_maxlife)
    except Exception as e:
        print(f"{datetime.now()} : Error in main function", flush=True)
        print(traceback.format_exc())
