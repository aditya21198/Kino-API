import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from models import KinoPostStock
from dotenv import load_dotenv
import os
from datetime import datetime,timedelta,date
from database import execute_query_fetch, make_db_connection,update_table
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from log_handler.logs import KinoLogger
from kino.kino_api_test import mock_data,mock_post_stock_maxlife,mock_post_stock_non_maxlife,mock_data_so,mock_data_rdo,mock_data_cancel_so
from fastapi.encoders import jsonable_encoder
import pytz

from threading import Lock

LOGIN_LOCK = Lock()

logger = KinoLogger("kino_api_logs")
providers_table = KinoLogger('kino_item_price_result')

load_dotenv()

_KINO_CONFIG_CACHE = {}

def get_kino_config(maxlife=False, force_reload=False):
    cache_key = "maxlife" if maxlife else "normal"

    if not force_reload and cache_key in _KINO_CONFIG_CACHE:
        return _KINO_CONFIG_CACHE[cache_key]

    kino_config = {
        "kino_host": None,
        "kino_client_id": None,
        "kino_client_secret": None,
        "kino_access_token": None,
        "kino_access_token_creation": None
    }

    result = execute_query_fetch("""
        SELECT field, value
        FROM tabSingles
        WHERE doctype = 'Kino API Settings'
    """)

    if result:
        for row in result:
            f = row["field"]
            v = row["value"]

            if not maxlife:
                mapping = {
                    "kino_host": "kino_host",
                    "kino_client_id": "kino_client_id",
                    "kino_client_secret": "kino_client_secret",
                    "kino_access_token": "kino_access_token",
                    "access_token_creation": "kino_access_token_creation",
                }
            else:
                mapping = {
                    "kino_host_maxlife": "kino_host",
                    "kino_client_id_maxlife": "kino_client_id",
                    "kino_client_secret_maxlife": "kino_client_secret",
                    "kino_access_token_maxlife": "kino_access_token",
                    "access_token_creation_maxlife": "kino_access_token_creation",
                }

            if f in mapping:
                kino_config[mapping[f]] = v

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
    def token_expired(token_creation):
        if not token_creation:
            return True

        if isinstance(token_creation, str):
            token_creation = datetime.strptime(
                token_creation, "%Y-%m-%d %H:%M:%S"
            )

        return datetime.now() - token_creation > timedelta(hours=24)

    config = get_kino_config(maxlife=maxlife)

    if config["kino_access_token"] and not token_expired(
        config["kino_access_token_creation"]
    ):
        return {"access_token": config["kino_access_token"]}

    with LOGIN_LOCK:
        config = get_kino_config(maxlife=maxlife, force_reload=True)

        if config["kino_access_token"] and not token_expired(
            config["kino_access_token_creation"]
        ):
            return {"access_token": config["kino_access_token"]}

        response = requests.post(
            config["kino_host"] + "oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config["kino_client_id"],
                "client_secret": config["kino_client_secret"],
                "scope": "*"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=(5,10)
        )
        response.raise_for_status()

        token = response.json()["access_token"]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_single(
            token,
            "kino_access_token_maxlife" if maxlife else "kino_access_token"
        )
        update_single(
            now,
            "access_token_creation_maxlife" if maxlife else "access_token_creation"
        )
        get_kino_config(maxlife=maxlife, force_reload=True)

        return {"access_token": token}

        
    

# def get_customer_code(store:str,channel:str,region_id:str):
#     query = """
#     SELECT
#         store,
#         channel,
#         cm_region,
#         cm_entity,
#         cm_branch,
#         cm_cust_code1,
#         cm_cust_code2,
#         cm_cust_name 
#     FROM `tabCustomer Mapping Detail`
#     WHERE parent = 'Kino API Settings'
#     """
#     try:
#         customers_mapping = execute_query_fetch(query=query)
#         lower_store = store.lower()
#         lower_channel = channel.lower()
#         found = False
#         for customer in customers_mapping:
#             if customer.get('store') == lower_store and customer.get('channel') == lower_channel and region_id == customer.get('cm_region'):
#                 found = True
#                 return customer.get('cm_cust_code1'),customer.get('cm_cust_code2'),customer.get('cm_entity'),customer.get('cm_branch')
#         if not found:
#             raise Exception (f"Customer Code with store {store} and channel {channel} not found")
#     except Exception as e:
#         raise Exception (f"Customer Code with store {store} and channel {channel} not found")
# cache global
CUSTOMER_MAPPING_CACHE = None

def load_customer_mapping():
    global CUSTOMER_MAPPING_CACHE
    if CUSTOMER_MAPPING_CACHE is not None:
        return CUSTOMER_MAPPING_CACHE

    query = """
    SELECT
        store,
        channel,
        cm_region,
        cm_entity,
        cm_branch,
        cm_cust_code1,
        cm_cust_code2
    FROM `tabCustomer Mapping Detail`
    WHERE parent = 'Kino API Settings'
    """
    result = execute_query_fetch(query=query)
    mapping = {}
    for row in result:
        key = (row['store'].lower(), row['channel'].lower(), row['cm_region'])
        mapping[key] = (
            row['cm_cust_code1'],
            row['cm_cust_code2'],
            row['cm_entity'],
            row['cm_branch']
        )
    CUSTOMER_MAPPING_CACHE = mapping
    return mapping

def get_customer_code(store:str, channel:str, region_id:str):
    mapping = load_customer_mapping()
    key = (store.lower(), channel.lower(), region_id)
    if key in mapping:
        return mapping[key]
    raise Exception(f"Customer Code with store {store} and channel {channel} not found")

def remove_kn(item_code: str):
    if item_code.startswith("KN"):
        return item_code[2:]
    return item_code

# def get_salesman_code(region_id:str):
#     query = """
#     SELECT gms_region,gms_entity,gms_branch,gms_salesman_id,gms_salesman_name 
#     FROM `tabSalesman Mapping Detail`
#     WHERE parent = 'Kino API Settings'
#     """
#     salesman_mapping = execute_query_fetch(query=query)
#     if salesman_mapping:
#         for salesman in salesman_mapping:
#             if salesman['gms_region'] == region_id:
#                 return salesman
#     raise Exception ("Salesman Not Found in Salesman mapping")

# cache global
SALESMAN_MAPPING_CACHE = None

def load_salesman_mapping():
    global SALESMAN_MAPPING_CACHE
    if SALESMAN_MAPPING_CACHE is not None:
        return SALESMAN_MAPPING_CACHE

    query = """
    SELECT gms_region, gms_entity, gms_branch, gms_salesman_id, gms_salesman_name 
    FROM `tabSalesman Mapping Detail`
    WHERE parent = 'Kino API Settings'
    """
    result = execute_query_fetch(query=query)
    mapping = {}
    for row in result:
        # key berdasarkan region_id
        mapping[row['gms_region']] = row
    SALESMAN_MAPPING_CACHE = mapping
    return mapping

def get_salesman_code(region_id: str):
    mapping = load_salesman_mapping()
    if region_id in mapping:
        return mapping[region_id]
    raise Exception("Salesman Not Found in Salesman mapping")

def grouped_data_by_order_id(query_result: list, is_cancel: bool = False):
    inv_type = "INV02"
    if is_cancel:
        inv_type = "RET01"

    grouped_data = {}

    for row in query_result:
        order_id = row.get('name')
        if not order_id:
            continue

        if order_id not in grouped_data:
            grouped_data[order_id] = []

            try:
                # === REGION CODE ===
                sub_brand = row.get("sub_brand")
                if sub_brand and sub_brand.lower() in ["maxlife", "perro", "jojo", "kucingku"]:
                    region_code = "1002"
                else:
                    region_code = "1000"

                # === CUSTOMER CODE ===
                store = row.get('store')
                channel = row.get('channel')

                cust_code1, cust_code2, entity_code, branch_code = \
                    get_customer_code(
                        store=store,
                        channel=channel,
                        region_id=region_code
                    )

                salesman_code = get_salesman_code(
                    region_id=region_code
                )['gms_salesman_id']

                transaction_date = (
                    row.get("transaction_date").isoformat()
                    if row.get("transaction_date")
                    else None
                )

                grouped_data[order_id].append({
                    'REGION_CODE': region_code,
                    'BRANCH_CODE': branch_code,
                    'ENTITY_CODE': str(entity_code),
                    'CUST_CODE1': cust_code1,
                    'CUST_CODE2': cust_code2,
                    'SALESMAN_CODE': salesman_code,
                    'INV_TYPE': inv_type,
                    'ORDER_REF': order_id,
                    'ORDER_DATE': transaction_date,
                    'SFA_TGLORDER': transaction_date,
                    'SFA_ORDERNO': order_id,
                    'SFA_SLSNO': salesman_code
                })

            except Exception as e:
                # ⛔ skip order ini aja
                print(f"[SKIP ORDER {order_id}] {e}")
                grouped_data.pop(order_id, None)
                continue

    return grouped_data

        


# def group_details_by_order_id(query_result: list):
#     grouped_detail = {}
#     try:

#         for row in query_result:
#             order_id = row.get('name')
#             if not order_id:
#                 continue

#             if order_id not in grouped_detail:
#                 grouped_detail[order_id] = []

#             price_list_rate = row.get('price_list_rate_dbp',None)

#             grouped_detail[order_id].append({
#                 'PCODE': remove_kn(row.get('item_code')),
#                 'PRICE': price_list_rate,
#                 'LINETYPE': 'N',
#                 'QTY': row.get('quantity'),
#                 'GROSS': row.get('total_amount'),

#                 'DISC_ID1': "",
#                 'DISC_PRINCIPAL_PCT1': 0.0,
#                 'DISC_PRINCIPAL_VAL1': 0.0,
#                 'DISC_DIST_PCT1': 0.0,
#                 'DISC_DIST_VAL1': 0.0,

#                 'DISC_ID2': "",
#                 'DISC_PRINCIPAL_PCT2': 0.0,
#                 'DISC_PRINCIPAL_VAL2': 0.0,
#                 'DISC_DIST_PCT2': 0.0,
#                 'DISC_DIST_VAL2': 0.0,

#                 'DISC_ID3': "",
#                 'DISC_PRINCIPAL_PCT3': 0.0,
#                 'DISC_PRINCIPAL_VAL3': 0.0,
#                 'DISC_DIST_PCT3': 0.0,
#                 'DISC_DIST_VAL3': 0.0,

#                 'DISC_ID4': "",
#                 'DISC_PRINCIPAL_PCT4': 0.0,
#                 'DISC_PRINCIPAL_VAL4': 0.0,
#                 'DISC_DIST_PCT4': 0.0,
#                 'DISC_DIST_VAL4': 0.0,

#                 'DISC_ID5': "",
#                 'DISC_PRINCIPAL_PCT5': 0.0,
#                 'DISC_PRINCIPAL_VAL5': 0.0,
#                 'DISC_DIST_PCT5': 0.0,
#                 'DISC_DIST_VAL5': 0.0,

#                 'DISC_ID6': "",
#                 'DISC_PRINCIPAL_PCT6': 0.0,
#                 'DISC_PRINCIPAL_VAL6': 0.0,
#                 'DISC_DIST_PCT6': 0.0,
#                 'DISC_DIST_VAL6': 0.0,

#                 'TAX_AMT': row.get('tax_amount', 0.0),
#                 'NET': row.get('amount', 0.0),
#                 'DISC_TOTAL': 0.0
#             })
#         return grouped_detail
#     except Exception as error:
#         raise Exception (traceback.format_exc())

def group_details_by_order_id(query_result: list):
    grouped_detail = {}
    try:
        for row in query_result:
            order_id = row.get('name')
            if not order_id:
                continue

            # init per order
            if order_id not in grouped_detail:
                grouped_detail[order_id] = {}

            item_code = remove_kn(row.get('item_code'))
            price_list_rate = row.get('price_list_rate_dbp', None)

            # kalau item_code belum ada → create
            if item_code not in grouped_detail[order_id]:
                grouped_detail[order_id][item_code] = {
                    'PCODE': item_code,
                    'PRICE': price_list_rate,
                    'LINETYPE': 'N',
                    'QTY': abs(row.get('quantity', 0.0)),
                    'GROSS': abs(row.get('total_amount', 0.0)),

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

                    'TAX_AMT': abs(row.get('tax_amount', 0.0)),
                    'NET': abs(row.get('amount', 0.0)),
                    'DISC_TOTAL': 0.0
                }

            # kalau item_code sudah ada → SUM
            else:
                item = grouped_detail[order_id][item_code]
                item['QTY'] += abs(row.get('quantity', 0.0))
                item['GROSS'] += abs(row.get('total_amount', 0.0))
                item['TAX_AMT'] += abs(row.get('tax_amount', 0.0))
                item['NET'] += abs(row.get('amount', 0.0))

        # convert dict → list (biar sama kayak sebelumnya)
        for order_id in grouped_detail:
            grouped_detail[order_id] = list(grouped_detail[order_id].values())

        return grouped_detail

    except Exception:
        raise Exception(traceback.format_exc())


def build_payload(result: list,is_cancel:bool=False):
    try:
        grouped_data = grouped_data_by_order_id(query_result=result,is_cancel=is_cancel)
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
    


def create_post_invoice_payload(order_ref:str = None,start_date:str = None,end_date:str = None,is_cancel:bool=False):
    conditions = []
    condittion_start_date_end_date = []
    docstatus = 1
    if is_cancel:
        docstatus = 2
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
        calc.grand_total_with_vat,
        calc.master_bundle_item,
        calc.item_code,
        calc.sub_brand,
        calc.quantity,
        calc.selling_price_list,
        calc.price_list_rate,
        
        CAST(calc.harga_jual_satuan AS DECIMAL(20,4)) AS harga_jual,
        
        CAST(calc.harga_jual_satuan * calc.quantity AS DECIMAL(20,4)) AS total_amount,
        CAST((calc.harga_jual_satuan * calc.quantity) * 0.11 AS DECIMAL(20,4)) AS tax_amount,
        CAST((calc.harga_jual_satuan * calc.quantity) * 1.11 AS DECIMAL(20,4)) AS amount,
        
        calc.is_bundle_item,
        calc.store,
        calc.channel,
        calc.price_list_rate_dbp,
        calc.soi_name,
        calc.pi_name
    FROM (
        SELECT
            so.name,
            so.po_no,
            so.transaction_date,
            so.grand_total AS grand_total_with_vat,
            so.selling_price_list,
            COALESCE(pi.parent_item, soi.item_code) AS master_bundle_item,
            COALESCE(pi.item_code, soi.item_code) AS item_code,
            COALESCE(pi.qty, soi.qty)-soi.returned_qty AS quantity,

            CASE 
                WHEN pi.item_code IS NOT NULL THEN 
                    ((soi.price_list_rate * soi.qty) / NULLIF(bundle_sum.total_pcs_in_this_row, 0))
                ELSE 
                    soi.price_list_rate 
            END AS harga_jual_satuan,
            soi.price_list_rate,

            CASE WHEN pi.item_code IS NOT NULL THEN 1 ELSE 0 END AS is_bundle_item,
            JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].store')) AS store,
            JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].channel')) AS channel,
            it.sub_brand,
            
            soi.name AS soi_name,
            COALESCE(pi.name, 'SINGLE') AS pi_name,

            (
                SELECT ip.price_list_rate
                FROM aladdin.`tabItem Price` ip
                WHERE ip.item_code = COALESCE(pi.item_code, soi.item_code)
                AND ip.price_list = 'DBP'
                AND ip.valid_from <= so.transaction_date
                ORDER BY ip.valid_from DESC
                LIMIT 1
            ) AS price_list_rate_dbp

        FROM aladdin.`tabSales Order Item` soi
        INNER JOIN aladdin.`tabSales Order` so ON soi.parent = so.name
        
        LEFT JOIN aladdin.`tabPacked Item` pi 
            ON pi.parent = so.name 
            AND pi.parent_detail_docname = soi.name


        LEFT JOIN (
            SELECT 
                parent_detail_docname, 
                SUM(qty) as total_pcs_in_this_row
            FROM aladdin.`tabPacked Item`
            GROUP BY parent_detail_docname
        ) bundle_sum ON bundle_sum.parent_detail_docname = soi.name

        LEFT JOIN aladdin.tabItem it ON it.item_code = COALESCE(pi.item_code, soi.item_code)
        LEFT JOIN logs.erpnext_arbi_titipaja_api_log api_log ON api_log.id = (
                SELECT l2.id
                FROM logs.erpnext_arbi_titipaja_api_log l2
                WHERE l2.po_no = so.po_no AND l2.title = 'Price Detail'
                ORDER BY l2.created_at DESC, l2.id DESC LIMIT 1
            )

        WHERE soi.brand = 'Kino'
        AND so.docstatus = {docstatus}
        {condition_transaction_date_sql}
    ) calc
    WHERE calc.quantity != 0
    {condition_sql}
    GROUP BY calc.soi_name, calc.pi_name
    ORDER BY calc.transaction_date, calc.name, calc.soi_name, calc.pi_name
    """
    try:
        result = execute_query_fetch(query=query) or []
        for row in result:
            item_code = row.get("item_code")
            if item_code:
                dbp_price = select_dbp_price(item_code,end_date)
                if dbp_price is not None:
                    row["price_list_rate_dbp"] = dbp_price
        # payloads = build_payload(result=result)
        # for test
        # payloads = mock_data()

        return result
    except Exception as error:
        raise Exception(traceback.format_exc())

def send_single_invoice(payload: json,is_cancel:bool=False):
    inv_type = "INV02"
    if is_cancel:
        inv_type = "RET01"
    data = payload
    if data[0]['DATA'][0].get('REGION_CODE') == '1002':
        token = login(maxlife=True)['access_token']
        print(token)
        data[0]['CLIENTID'] = get_kino_config(maxlife=True).get('kino_client_id')
        url = get_kino_config(maxlife=True).get('kino_host')+'api/ids/extclient/masterpayload'
    else:
        token = login(maxlife=False)['access_token']
        print(token)
        data[0]['CLIENTID'] = get_kino_config(maxlife=False).get('kino_client_id')
        url = get_kino_config(maxlife=False).get('kino_host')+'api/ids/extclient/masterpayload'

    # if using env
    # url = os.getenv("KINO_IDS_POST_INVOICE_URL")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    try:
        response = requests.post(url, json=data[0], headers=headers,timeout=(5,20))

        log_data = {
            "url": url,
            "title": "SEND_SINGLE_INVOICE",
            "inv_type":inv_type,
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
            "inv_type":inv_type,
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

DBP_PRICE_CACHE = {}
DBP_CACHE_LOADED = [False,""]
DBP_LOCK = Lock()


def select_dbp_price(item_code: str, end_date: str):

    global DBP_CACHE_LOADED

    if not DBP_CACHE_LOADED[0] or DBP_CACHE_LOADED[1] != end_date:
        with DBP_LOCK:
            if not DBP_CACHE_LOADED[0] or DBP_CACHE_LOADED[1] != end_date:
                load_dbp_cache(end_date=end_date)

    return DBP_PRICE_CACHE.get(item_code)


def load_dbp_cache(end_date: str):
    global DBP_PRICE_CACHE, DBP_CACHE_LOADED
    try:
        query = """
            SELECT ip.item_code, ip.price_list_rate
            FROM `tabItem Price` ip
            INNER JOIN (
                SELECT item_code, MAX(valid_from) as max_valid_from
                FROM `tabItem Price`
                WHERE price_list = 'DBP'
                AND brand = 'Kino'
                AND valid_from <= %s
                GROUP BY item_code
            ) latest
            ON ip.item_code = latest.item_code
            AND ip.valid_from = latest.max_valid_from
            WHERE ip.price_list = 'DBP'
            AND ip.brand = 'Kino'
        """
        rows = execute_query_fetch(query=query, params=(end_date,),is_asi=True) or []

        # get all data to db
        get_all_data = f"""
        select 
            item_code,
            price_list_rate,
            valid_from,
            price_list,
            valid_upto
        from `tabItem Price`
        WHERE price_list = 'DBP'
        AND brand = 'Kino'
        AND valid_from <= '{end_date}'
        """
        result_all_data = execute_query_fetch(query=get_all_data,is_asi=True) or []
        # turncate table before insert new cache
        providers_table.truncate_if_exists()
        # insert
        providers_table.log_bulk(result_all_data)

        DBP_PRICE_CACHE = {
            item_code: price
            for item_code, price in rows
        }

        DBP_CACHE_LOADED = [True, end_date]
    except Exception as e:
        raise Exception(f"Error loading DBP cache: {e}")

def create_update_invoice_payload_dn(order_ref:str,start_date:str,end_date:str,cancel:bool=False):
    sql_condition = f"AND dni.against_sales_order = '{order_ref}'" if order_ref else ""
    is_return = 0
    if cancel:
        is_return = 1
    query = f"""
    SELECT
        calc.name,
        calc.po_no,
        calc.transaction_date,
        calc.grand_total_with_vat,
        calc.master_bundle_item,
        calc.item_code,
        calc.sub_brand,
        calc.quantity,
        calc.selling_price_list,
        calc.price_list_rate,
        
        CAST(calc.harga_jual_satuan AS DECIMAL(20,4)) AS harga_jual,
        
        CAST(calc.harga_jual_satuan * calc.quantity AS DECIMAL(20,4)) AS total_amount,
        CAST((calc.harga_jual_satuan * calc.quantity) * 0.11 AS DECIMAL(20,4)) AS tax_amount,
        CAST((calc.harga_jual_satuan * calc.quantity) * 1.11 AS DECIMAL(20,4)) AS amount,
        
        calc.is_bundle_item,
        calc.store,
        calc.channel,
        calc.price_list_rate_dbp,
        calc.dni_name,
        calc.pi_name
    FROM (
        SELECT
            so.name,
            so.po_no,
            so.transaction_date,
            so.grand_total AS grand_total_with_vat,
            so.selling_price_list,
            COALESCE(pi.parent_item, dni.item_code) AS master_bundle_item,
            COALESCE(pi.item_code, dni.item_code) AS item_code,
            COALESCE(pi.qty, dni.qty) AS quantity,

            CASE 
                WHEN pi.item_code IS NOT NULL THEN 
                    ((dni.price_list_rate * dni.qty) / NULLIF(bundle_sum.total_pcs_in_this_row, 0))
                ELSE 
                    dni.price_list_rate 
            END AS harga_jual_satuan,
            dni.price_list_rate,

            CASE WHEN pi.item_code IS NOT NULL THEN 1 ELSE 0 END AS is_bundle_item,
            JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].store')) AS store,
            JSON_UNQUOTE(JSON_EXTRACT(api_log.response, '$.data.price[0].channel')) AS channel,
            it.sub_brand,
            
            dni.name AS dni_name,
            COALESCE(pi.name, 'SINGLE') AS pi_name,

            (
                SELECT ip.price_list_rate
                FROM aladdin.`tabItem Price` ip
                WHERE ip.item_code = COALESCE(pi.item_code, dni.item_code)
                AND ip.price_list = 'DBP'
                AND ip.valid_from <= so.transaction_date
                ORDER BY ip.valid_from DESC
                LIMIT 1
            ) AS price_list_rate_dbp

        FROM aladdin.`tabDelivery Note Item` dni
        INNER JOIN aladdin.`tabSales Order` so ON dni.against_sales_order = so.name
        
        LEFT JOIN `tabDelivery Note` dn
            ON dn.name = dni.parent
        
        LEFT JOIN aladdin.`tabPacked Item` pi 
            ON pi.parent = dni.parent 
            AND pi.parent_detail_docname = dni.name


        LEFT JOIN (
            SELECT 
                parent_detail_docname, 
                SUM(qty) as total_pcs_in_this_row
            FROM aladdin.`tabPacked Item`
            GROUP BY parent_detail_docname
        ) bundle_sum ON bundle_sum.parent_detail_docname = dni.name

        LEFT JOIN aladdin.tabItem it ON it.item_code = COALESCE(pi.item_code, dni.item_code)
        LEFT JOIN logs.erpnext_arbi_titipaja_api_log api_log ON api_log.id = (
                SELECT l2.id
                FROM logs.erpnext_arbi_titipaja_api_log l2
                WHERE l2.po_no = so.po_no AND l2.title = 'Price Detail'
                ORDER BY l2.created_at DESC, l2.id DESC LIMIT 1
            )

        WHERE dni.brand = 'Kino'
        AND DATE(dni.modified) BETWEEN '{start_date}' AND '{end_date}'
        AND dn.docstatus = 1
        AND dn.is_return = {is_return}
        {sql_condition}
    ) calc
    WHERE calc.quantity != 0
    GROUP BY calc.dni_name, calc.pi_name
    ORDER BY calc.transaction_date, calc.name, calc.dni_name, calc.pi_name
    """
    print(query)
    result = execute_query_fetch(query=query)
    if result:
        for row in result:
            item_code = row.get("item_code")
            if item_code:
                dbp_price = select_dbp_price(item_code,end_date)
                if dbp_price is not None:
                    row["price_list_rate_dbp"] = dbp_price
        return result


def worker_send_invoice(raw_payloads,is_cancel=False):
    grouped = {}
    for row in raw_payloads:
        so_ref = row.get('name')
        if not so_ref:
            continue
        grouped.setdefault(so_ref, []).append(row)

    def worker(so_ref, rows):
        try:
            payload = build_payload(rows,is_cancel=is_cancel)
            print(payload)
            if is_cancel:
                latest_increment = get_last_cancelled_order_ref_name(order_ref=so_ref)
                if latest_increment:
                    new_order_ref = increment_name(order_ref=latest_increment[0]['order_ref'])
                    payload[0]['DATA'][0]['ORDER_REF'] = new_order_ref
                    payload[0]['DATA'][0]['SFA_ORDERNO'] = new_order_ref
                else:
                    new_order_ref = increment_name(order_ref=so_ref)
                    payload[0]['DATA'][0]['ORDER_REF'] = new_order_ref
                    payload[0]['DATA'][0]['SFA_ORDERNO'] = new_order_ref
                cancel_order = check_cancelled_invoice(order_ref=so_ref)
                if not cancel_order:
                    send_single_invoice(payload,is_cancel=is_cancel)
            else:
                send_single_invoice(payload)
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

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(worker, so_ref, rows)
            for so_ref, rows in grouped.items()
        ]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                print(traceback.format_exc())
                raise Exception(traceback.format_exc())

def check_cancelled_invoice(order_ref):
    query = f"""
        SELECT order_ref
        FROM logs.kino_api_logs 
        WHERE order_ref = '{order_ref}'
        AND inv_type = 'RET01'
        AND kino_status = 'success'
    """
    result = execute_query_fetch(query=query)
    if result:
        return result

def check_sended_so(order_ref):
    query = f"""
        SELECT order_ref
        FROM logs.kino_api_logs
        WHERE order_ref = '{order_ref}'
        AND inv_type = 'INV02'
        AND kino_status = 'success'
    """
    result = execute_query_fetch(query=query)
    if result:
        return result

def get_last_cancelled_order_ref_name(order_ref:str):
    query = f"""
    SELECT order_ref
    FROM logs.kino_api_logs
    WHERE inv_type = 'RET01'
    AND order_ref LIKE '%{order_ref}%'
    AND kino_status = 'success'
    ORDER BY id DESC LIMIT 1
    """
    result = execute_query_fetch(query=query)
    if result:
        return result

def increment_name(order_ref):
    so = order_ref
    part = so.split("-")[-1]
    if len(part) < 3:
        num = int(part)+1
        new_so = "-".join(so.split("-")[:-1])
        return new_so+f"-{num}"
    else:
        num = "-1"
        new_so = so+num
        return new_so

def ids_post_invoice(data_dict: dict):
    order_ref = data_dict.get('ORDER_REF')
    start_date = data_dict.get('START_DATE')
    end_date = data_dict.get('END_DATE')
    try:
        # send first sales order
        if order_ref:
            print("insert so")
            for order in order_ref:
                raw_payloads = create_update_invoice_payload_dn(
                    order_ref=order,
                    start_date=start_date,
                    end_date=end_date
                )
                # for test
                # raw_payloads = mock_data_so()
                if raw_payloads:
                    worker_send_invoice(raw_payloads=raw_payloads)
        else:
            print("insert so")
            raw_payloads = create_update_invoice_payload_dn(
                order_ref=None,
                start_date=start_date,
                end_date=end_date
            )
            # for test
            # raw_payloads = mock_data_so()
            if raw_payloads:
                worker_send_invoice(raw_payloads=raw_payloads)
        
        # RDO invoice
        if order_ref:
            print("cancel RDO")
            for order in order_ref:
                raw_payloads = create_update_invoice_payload_dn(
                    order_ref=order,
                    start_date=start_date,
                    end_date=end_date,
                    cancel=True
                )
                # for test
                # raw_payloads = mock_data_rdo()
                if raw_payloads:
                    worker_send_invoice(raw_payloads=raw_payloads,is_cancel=True)
        else:
            print("cancel RDO")
            raw_payloads = create_update_invoice_payload_dn(
                order_ref=None,
                start_date=start_date,
                end_date=end_date,
                cancel=True
            )
            # for test 
            # raw_payloads = mock_data_rdo()
            if raw_payloads:
                worker_send_invoice(raw_payloads=raw_payloads,is_cancel=True)
        
        # Cancel SO
        if order_ref:
            print("cancel so")
            for order in order_ref:
                raw_payloads = create_post_invoice_payload(
                    order_ref=order,
                    start_date=start_date,
                    end_date=end_date,
                    is_cancel=True
                )
                # for test
                # raw_payloads = mock_data_cancel_so()
                if raw_payloads:
                    worker_send_invoice(raw_payloads=raw_payloads,is_cancel=True)
        else:
            print("cancel so")
            raw_payloads = create_post_invoice_payload(
                order_ref=None,
                start_date=start_date,
                end_date=end_date,
                is_cancel=True
            )
            # for test
            # raw_payloads = mock_data_cancel_so()
            if raw_payloads:
                worker_send_invoice(raw_payloads=raw_payloads,is_cancel=True)

    except Exception:
        err_text = traceback.format_exc()
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

# old post stock
# def ids_post_invoice(data_dict:dict):
#     order_ref = None
#     start_date = None
#     end_date = None
#     try:
#         if data_dict:
#             order_ref = data_dict.get('ORDER_REF',None)
#             start_date = data_dict.get('START_DATE',None)
#             end_date = data_dict.get('END_DATE',None)
#             if order_ref:
#                 for order in order_ref:
#                     raw_payloads = create_post_invoice_payload(order_ref=order,start_date=start_date,end_date=end_date)
#                     unique_so_ref = get_unique_so_ref(payloads=raw_payloads)
#                     for so_ref in unique_so_ref:
#                         try:
#                             single_payloads = []
#                             for payload in raw_payloads:
#                                 if payload.get('name') == so_ref:
#                                     single_payloads.append(payload)
#                             payload = build_payload(single_payloads)
#                             send_single_invoice(payload)
#                         except Exception as error:
#                             print(traceback.format_exc(),error)
#                             err_text = traceback.format_exc()
#                             logger.log({
#                                 "url": None,
#                                 "title": "INVOICE_ERROR",
#                                 "order_ref":order,
#                                 "method": "POST",
#                                 "status_code": 500,
#                                 "kino_status":None,
#                                 "request": None,
#                                 "response": err_text
#                             })
#             else:
#                 raw_payloads = create_post_invoice_payload(order_ref=None,start_date=start_date,end_date=end_date)
#                 unique_so_ref = get_unique_so_ref(payloads=raw_payloads)
#                 for so_ref in unique_so_ref:
#                     try:
#                         single_payloads = []
#                         for payload in raw_payloads:
#                             if payload.get('name') == so_ref:
#                                 single_payloads.append(payload)
#                         payload = build_payload(single_payloads)
#                         send_single_invoice(payload)
#                     except Exception as error:
#                         print(traceback.format_exc(),error)
#                         err_text = traceback.format_exc()
#                         logger.log({
#                             "url": None,
#                             "title": "INVOICE_ERROR",
#                             "order_ref":so_ref,
#                             "method": "POST",
#                             "status_code": 500,
#                             "kino_status":None,
#                             "request": None,
#                             "response": err_text
#                         })
#     except Exception as error:
#         print(traceback.format_exc(),error)
#         err_text = traceback.format_exc()
#         logger.log({
#             "url": None,
#             "title": "INVOICE_ERROR",
#             "order_ref":None,
#             "method": "POST",
#             "status_code": 500,
#             "kino_status":None,
#             "request": None,
#             "response": err_text
#         })

def get_all_balance_kino_item(item_code: str = None, warehouse: str = None,to_date:str=None):
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
    
    if to_date:
        conditions+= " AND sle.posting_date <= %s"
        params.append(to_date)

    query = f"""
    SELECT 
    x.item_code,
    x.warehouse,
    SUM(x.actual_qty) as balance,
    x.sub_brand
	FROM(
        SELECT
            sle.item_code,
            sle.warehouse,
            sle.actual_qty,
            sle.posting_date,
            it.sub_brand
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` it ON it.name = sle.item_code
        {conditions}
       )x
    GROUP BY x.warehouse,x.item_code
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


def create_stock_payload(item_code: str = None, warehouse: str = None,date:str=None):
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
            warehouse=warehouse,
            to_date=date
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
            if kino_stock.get("sub_brand").lower() not in ['maxlife','perro','jojo','kucingku']:
                print(kino_stock.get("sub_brand"))
                print("non maxlife detail\n")
                non_maxlife_detail.append(detail_row)
            if kino_stock.get("sub_brand").lower() in ['maxlife','perro','jojo','kucingku']:
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

def post_stock(data:dict = None):
    print("run post stock\n")
    try:
        item_code = None
        warehouse = None
        date=None
        if data:
            item_code = data.get('item_code',None)
            warehouse = data.get('warehouse',None)
            date=data.get('date',None)
        header_maxlife, header_without_maxlife = create_stock_payload(item_code = item_code,warehouse=warehouse,date=date)
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
                    headers=headers,
                    timeout=(5,20)
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
                    headers=headers,
                    timeout=(5,20)
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


def generate_excel_full_payload_fast(payload, filename=None):
    import pandas as pd
    if not payload:
        raise Exception("Payload kosong")

    rows = []

    for interface in payload:
        interface_base = {
            "INTERFACEID": interface.get("INTERFACEID"),
            "CLIENTID": interface.get("CLIENTID"),
        }

        for data in interface.get("DATA", []):
            data_base = {
                "REGION_CODE": data.get("REGION_CODE"),
                "BRANCH_CODE": data.get("BRANCH_CODE"),
                "ENTITY_CODE": data.get("ENTITY_CODE"),
                "CUST_CODE1": data.get("CUST_CODE1"),
                "CUST_CODE2": data.get("CUST_CODE2"),
                "SALESMAN_CODE": data.get("SALESMAN_CODE"),
                "INV_TYPE": data.get("INV_TYPE"),
                "ORDER_REF": data.get("ORDER_REF"),
                "ORDER_DATE": data.get("ORDER_DATE"),
                "SFA_TGLORDER": data.get("SFA_TGLORDER"),
                "SFA_ORDERNO": data.get("SFA_ORDERNO"),
                "SFA_SLSNO": data.get("SFA_SLSNO"),
            }

            for detail in data.get("DETAIL", []):
                row = {**interface_base, **data_base, **detail}
                rows.append(row)

    df = pd.DataFrame(rows)

    if not filename:
        from datetime import datetime
        filename = f"invoice_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    df.to_excel(filename, index=False)
    return filename



def render_payload_to_json(payload, filename=None):
    import json
    from datetime import datetime
    if not filename:
        filename = f"payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return filename

def get_all_date_in_range(start_date:str,end_date:str):
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    dates = [
        (start + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range((end - start).days + 1)
    ]
    return dates

def manual_ids_post_invoice(data_dict: dict):
    order_ref = data_dict.get('ORDER_REF')
    start_date = data_dict.get('START_DATE')
    end_date = data_dict.get('END_DATE')
    try:
        # send first sales order
        if order_ref:
            print("insert so")
            for order in order_ref:
                raw_payloads = create_update_invoice_payload_dn(
                    order_ref=order,
                    start_date=start_date,
                    end_date=end_date
                )
                # for test
                # raw_payloads = mock_data_so()
                if raw_payloads:
                    manual_send_invoice(raw_payloads=raw_payloads)
        else:
            print("insert so")
            raw_payloads = create_update_invoice_payload_dn(
                order_ref=None,
                start_date=start_date,
                end_date=end_date
            )
            # for test
            # raw_payloads = mock_data_so()
            if raw_payloads:
                manual_send_invoice(raw_payloads=raw_payloads)
        
        # RDO invoice
        if order_ref:
            print("cancel RDO")
            for order in order_ref:
                raw_payloads = create_update_invoice_payload_dn(
                    order_ref=order,
                    start_date=start_date,
                    end_date=end_date,
                    cancel=True
                )
                # for test
                # raw_payloads = mock_data_rdo()
                if raw_payloads:
                    manual_send_invoice(raw_payloads=raw_payloads,is_cancel=True)
        else:
            print("cancel RDO")
            raw_payloads = create_update_invoice_payload_dn(
                order_ref=None,
                start_date=start_date,
                end_date=end_date,
                cancel=True
            )
            # for test 
            # raw_payloads = mock_data_rdo()
            if raw_payloads:
                manual_send_invoice(raw_payloads=raw_payloads,is_cancel=True)
        
        # Cancel SO
        if order_ref:
            print("cancel so")
            for order in order_ref:
                raw_payloads = create_post_invoice_payload(
                    order_ref=order,
                    start_date=start_date,
                    end_date=end_date,
                    is_cancel=True
                )
                # for test
                # raw_payloads = mock_data_cancel_so()
                if raw_payloads:
                    manual_send_invoice(raw_payloads=raw_payloads,is_cancel=True)
        else:
            print("cancel so")
            raw_payloads = create_post_invoice_payload(
                order_ref=None,
                start_date=start_date,
                end_date=end_date,
                is_cancel=True
            )
            # for test
            # raw_payloads = mock_data_cancel_so()
            if raw_payloads:
                manual_send_invoice(raw_payloads=raw_payloads,is_cancel=True)

    except Exception:
        err_text = traceback.format_exc()
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

def manual_send_invoice(raw_payloads,is_cancel):
    grouped = {}
    for row in raw_payloads:
        so_ref = row.get('name')
        if not so_ref:
            continue
        grouped.setdefault(so_ref, []).append(row)
    for so_ref,rows in grouped.items():
        try: 
            payload = build_payload(rows,is_cancel=is_cancel)
            print(payload)
            if is_cancel:
                latest_increment = get_last_cancelled_order_ref_name(order_ref=so_ref)
                if latest_increment:
                    new_order_ref = increment_name(order_ref=latest_increment[0]['order_ref'])
                    payload[0]['DATA'][0]['ORDER_REF'] = new_order_ref
                    payload[0]['DATA'][0]['SFA_ORDERNO'] = new_order_ref
                else:
                    new_order_ref = increment_name(order_ref=so_ref)
                    payload[0]['DATA'][0]['ORDER_REF'] = new_order_ref
                    payload[0]['DATA'][0]['SFA_ORDERNO'] = new_order_ref
                cancel_order = check_cancelled_invoice(order_ref=so_ref)
                if not cancel_order:
                    send_single_invoice(payload,is_cancel=is_cancel)
            else:
                send_single_invoice(payload)
        except Exception as error:
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

def manual_send_data(data_dict:dict):
    order_ref = data_dict.get('order_ref')
    start_date = data_dict.get('start_date')
    end_date = data_dict.get('end_date')
    item_code = data_dict.get('item_code')
    warehouse = data_dict.get('warehouse')
    list_date_from_range = get_all_date_in_range(start_date=start_date,end_date=end_date)
    for date in list_date_from_range:
        # post stock daily
        post_stock_param ={
            "date":date,
            "item_code":item_code,
            "warehouse":warehouse
        }
        post_invoice_param={
            'ORDER_REF':order_ref,
            'START_DATE':date,
            'END_DATE':date
        }
        post_stock(post_stock_param)
        manual_ids_post_invoice(post_invoice_param)


# Generate Excel
if __name__ == '__main__':
    try:
        print("running_create excel\n")
        raw = create_post_invoice_payload(
            order_ref=None,
            start_date='2026-01-01',
            end_date='2026-01-31'
        )

        payload = build_payload(raw)

        file_path = generate_excel_full_payload_fast(payload)
        print(f"Excel generated: {file_path}")
        render_payload_to_json(payload=payload)
        print(f"Json Created\n")

    except Exception:
        print(f"{datetime.now()} : Error in main function", flush=True)
        print(traceback.format_exc())
