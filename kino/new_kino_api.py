import sys, os
import traceback
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from dotenv import load_dotenv
from collections import defaultdict
from threading import Lock
import json
from log_handler.logs import KinoLogger
from datetime import datetime,timedelta,date
from database import execute_query_fetch, make_db_connection,update_table


LOGIN_LOCK = Lock()

logger = KinoLogger("kino_api_logs")
providers_table = KinoLogger('kino_item_price_result')

load_dotenv()

_KINO_CONFIG_CACHE = {}

def get_kino_config(branch_code, entity_code,warehouse, force_reload=False):
    cache_key = (branch_code,entity_code,warehouse)

    if not force_reload and cache_key in _KINO_CONFIG_CACHE:
        return _KINO_CONFIG_CACHE[cache_key]

    kino_config = {
        "warehouse":None,
        "branch_code":None,
        "entity_code":None,
        "kino_host": None,
        "kino_client_id": None,
        "kino_client_secret": None,
        "kino_access_token": None,
        "kino_access_token_creation": None
    }

    result = execute_query_fetch("""
        SELECT 
            kino_client.client_id AS kino_client_id,
            kino_client.client_secret AS kino_client_secret,
            kino_client.branch_code,
            kino_client.entity_code,
            kino_client.access_token AS kino_access_token,
            kino_client.access_token_creation AS kino_access_token_creation,
            kino_client.warehouse,
            sin.value AS kino_host
        FROM `tabKino Client Details` AS kino_client
        LEFT JOIN `tabSingles` AS sin ON sin.doctype = kino_client.parent
        WHERE sin.field = 'kino_general_host'
    """)
    mapping = {
        "warehouse":"warehouse",
        "branch_code":"branch_code",
        "entity_code":"entity_code",
        "kino_host": "kino_host",
        "kino_client_id": "kino_client_id",
        "kino_client_secret": "kino_client_secret",
        "kino_access_token": "kino_access_token",
        "kino_access_token_creation": "kino_access_token_creation",
    }
    if result:
        for row in result:
            for f, v in row.items():
                if f in mapping:
                    kino_config[mapping[f]] = v

    _KINO_CONFIG_CACHE[cache_key] = kino_config
    return _KINO_CONFIG_CACHE[cache_key]

def update_access_token_and_access_token_creation(value,field,branch_code,entity_code,warehouse):
    query = f"""
        UPDATE `tabKino Client Details`
        SET {field} = '{value}'
        WHERE branch_code = '{branch_code}'
        AND entity_code = '{entity_code}'
        AND warehouse = '{warehouse}'
    """
    result_update = update_table(query=query)
    return result_update

def login(branch_code,entity_code,warehouse):
    def token_expired(token_creation):
        if not token_creation:
            return True

        if isinstance(token_creation, str):
            token_creation = datetime.strptime(
                token_creation, "%Y-%m-%d %H:%M:%S"
            )

        return datetime.now() - token_creation > timedelta(hours=24)

    config = get_kino_config(branch_code=branch_code,entity_code=entity_code,warehouse=warehouse)

    if config["kino_access_token"] and not token_expired(
        config["kino_access_token_creation"]
    ):
        return {"access_token": config["kino_access_token"]}

    with LOGIN_LOCK:
        config = get_kino_config(branch_code=branch_code,entity_code=entity_code,warehouse=warehouse, force_reload=True)
        print("Config inside lock:", config)

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
        update_access_token_and_access_token_creation(
            value = token,
            field = "access_token",
            branch_code=branch_code,
            entity_code=entity_code,
            warehouse=warehouse
        )
        update_access_token_and_access_token_creation(
            value = now,
            field = "access_token_creation",
            branch_code=branch_code,
            entity_code=entity_code,
            warehouse=warehouse
        )
        get_kino_config(branch_code=branch_code,entity_code=entity_code,warehouse=warehouse, force_reload=True)

        return {"access_token": token}

CUSTOMER_MAPPING_CACHE = None
CUSTOMER_MAPPING_LAST_MODIFIED = None

def load_customer_mapping():
    global CUSTOMER_MAPPING_CACHE, CUSTOMER_MAPPING_LAST_MODIFIED

    # ambil last modified terbaru
    last_modified = execute_query_fetch("""
        SELECT MAX(modified) as last_modified
        FROM `tabCustomer Mapping Detail`
        WHERE parent = 'Kino API Settings'
    """)[0]["last_modified"]

    # kalau cache masih valid then return
    if (
        CUSTOMER_MAPPING_CACHE is not None
        and CUSTOMER_MAPPING_LAST_MODIFIED == last_modified
    ):
        return CUSTOMER_MAPPING_CACHE

    # reload cache
    result = execute_query_fetch("""
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
    """)

    mapping = {}
    for row in result:
        key = (row['store'].lower(), row['channel'].lower())
        mapping[key] = (
            row['cm_cust_code1'],
            row['cm_cust_code2'],
            row['cm_entity'],
            row['cm_branch'],
            row['cm_region']
        )

    CUSTOMER_MAPPING_CACHE = mapping
    CUSTOMER_MAPPING_LAST_MODIFIED = last_modified

    return mapping

def get_customer_code(store:str, channel:str):
    mapping = load_customer_mapping()
    key = (store.lower(), channel.lower())
    if key in mapping:
        return mapping[key]
    raise Exception(f"Customer Code with store {store} and channel {channel} not found")

def remove_kn(item_code: str):
    if item_code.startswith("KN"):
        return item_code[2:]
    return item_code

SALESMAN_MAPPING_CACHE = None
SALESMAN_MAPPING_LAST_MODIFIED = None

def load_salesman_mapping():
    global SALESMAN_MAPPING_CACHE, SALESMAN_MAPPING_LAST_MODIFIED
    # ambil last modified terbaru
    last_modified = execute_query_fetch("""
        SELECT MAX(modified) as last_modified
        FROM `tabSalesman Mapping Detail`
        WHERE parent = 'Kino API Settings'
    """)[0]["last_modified"]
    if SALESMAN_MAPPING_CACHE is not None \
        and SALESMAN_MAPPING_LAST_MODIFIED == last_modified:
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
        key = (row['gms_region'], row['gms_entity'], row['gms_branch'])
        mapping[key] = row
    SALESMAN_MAPPING_CACHE = mapping
    SALESMAN_MAPPING_LAST_MODIFIED = last_modified
    return mapping

def get_salesman_code(key: tuple):
    mapping = load_salesman_mapping()
    if key in mapping:
        return mapping[key]
    raise Exception("Salesman Not Found in Salesman mapping")


def check_trasaction_date_over_closing_date_kino(transaction_date, dn_posting_date,is_cancel = False):
    # always get day 2 of the month (Kino Closing day) or get from database if exist
    query = f"""
    SELECT value FROM `tabSingles`
    WHERE doctype = 'Kino API Settings'
    AND field = 'kino_closing_day'
    """
    result_closing_day = execute_query_fetch(query=query)
    closing_day = result_closing_day[0]['value'] if result_closing_day and int(result_closing_day[0]['value']) > 0 else 2
    today = datetime.now().date()

    today_month_day2 = date(today.year, today.month, int(closing_day))
    new_transaction_date = transaction_date

    # check transaction date
    if isinstance(transaction_date, str):
        transaction_date = datetime.strptime(transaction_date, "%Y-%m-%d").date()
    elif isinstance(transaction_date, datetime):
        transaction_date = transaction_date.date()
    
    # check dn posting date
    if isinstance(dn_posting_date, str):    
        dn_posting_date = datetime.strptime(dn_posting_date, "%Y-%m-%d").date()
    elif isinstance(dn_posting_date, datetime):
        dn_posting_date = dn_posting_date.date()
    
    so_dn_date_diff = abs((transaction_date - dn_posting_date).days)

    if so_dn_date_diff > 60:
        if today.month == 1:
            transaction_date = date(today.year - 1, 12, 1)
        else:
            transaction_date = date(today.year, today.month - 1, 1)

    if is_cancel:
        new_transaction_date = dn_posting_date
    else:
        # condition
        # 1. if transaction date and dn posting date under closing date kino
        # 2. if transaction date under closing date kino, but dn posting date is upper
        if transaction_date <= today_month_day2:
            if dn_posting_date <= today_month_day2:
                new_transaction_date = transaction_date
            elif dn_posting_date > today_month_day2:
                new_transaction_date = date(today.year,today.month,1)
                new_transaction_date = new_transaction_date
    
    if isinstance(new_transaction_date, (date, datetime)):
        return new_transaction_date.isoformat()
    return new_transaction_date

# post stock kino
def get_all_balance_kino_item(item_code: str = None, warehouse: str = None,to_date:str=None):
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
    
    if to_date:
        conditions+= " AND sle.posting_date <= %s"
        params.append(to_date)

    query = f"""
    SELECT 
    x.item_code,
    x.warehouse,
    SUM(x.actual_qty) as balance,
    x.sub_brand,
    tis.supplier_part_no
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
    LEFT JOIN `tabItem Supplier` as tis
    ON tis.parent = x.item_code AND tis.idx = 0
    GROUP BY x.warehouse,x.item_code,x.sub_brand
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

def stock_payload_builder():
    final_payload_header = {}

    result = execute_query_fetch("""
        SELECT 
            kino_client.client_id AS kino_client_id,
            kino_client.client_secret AS kino_client_secret,
            kino_client.branch_code,
            kino_client.entity_code,
            kino_client.access_token AS kino_access_token,
            kino_client.access_token_creation AS kino_access_token_creation,
            kino_client.warehouse,
            sin.value AS kino_host
        FROM `tabKino Client Details` AS kino_client
        LEFT JOIN `tabSingles` AS sin ON sin.doctype = kino_client.parent
        WHERE sin.field = 'kino_general_host'
    """)

    for res in result:
        key = (
            res.get("warehouse"),
            res.get("branch_code"),
            res.get("entity_code")
        )

        template_payload_stock = {
            "INTERFACEID": "T006",
            "CLIENTID": res.get("kino_client_id"),
            "DATA": []
        }

        final_payload_header[key] = template_payload_stock

    return final_payload_header

def get_sub_brand_mapping():
    query = """
        SELECT 
            label,
            warehouse,
            branch_code,
            entity_code,
            GROUP_CONCAT(LOWER(sub_brand)) AS sub_brands
        FROM `tabKino Sub Brand Mapping`
        WHERE warehouse IS NOT NULL
            AND branch_code IS NOT NULL
            AND entity_code IS NOT NULL
            AND sub_brand IS NOT NULL
        GROUP BY 
            label, warehouse, branch_code, entity_code
    """
    data = execute_query_fetch(query=query)

    for row in data:
        if row.get("sub_brands"):
            row["sub_brands"] = row["sub_brands"].split(",")
        else:
            row["sub_brands"] = []

    return data

def create_stock_payload(item_code: str = None, warehouse: str = None,date:str=None):
    try:
        kino_stock_balance = get_all_balance_kino_item(
            item_code=item_code,
            warehouse=warehouse,
            to_date=date
        )
        header_template = stock_payload_builder()

        warehouse_mapping = get_warehouse_mapping()
        header_template_key = list(header_template.keys())
        sub_brand_mapping = get_sub_brand_mapping()
        

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
            for header in header_template_key:
                if header[0] == kino_stock.get("warehouse"):
                    if sub_brand_mapping:
                        for sub_brand in sub_brand_mapping:
                            if sub_brand["warehouse"] == header[0] and sub_brand["warehouse"] == kino_stock.get("warehouse") \
                                and sub_brand["branch_code"] == header[1] and sub_brand["entity_code"] == header[2]:
                                if kino_stock.get("sub_brand").lower() in sub_brand["sub_brands"]:
                                    stock_detail = {
                                        "PRDCODE": remove_kn(kino_stock.get("item_code")) if not kino_stock.get("supplier_part_no") else remove_kn(kino_stock.get("supplier_part_no")),
                                        "WHLOC1": whloc1,
                                        "WHLOC2": whloc2,
                                        "QTY": kino_stock.get("balance")
                                    }
                                    try:
                                        detail = header_template[header]["DATA"][0]["DETAIL"]
                                    except (KeyError, IndexError):
                                        header_template[header]["DATA"].append({"DETAIL": []})
                                    header_template[header]["DATA"][0]["DETAIL"].append(stock_detail)
                            if sub_brand["warehouse"] == header[0] and sub_brand["warehouse"] == kino_stock.get("warehouse") \
                                and sub_brand["branch_code"] != header[1] or sub_brand["entity_code"] != header[2]:
                                if kino_stock.get("sub_brand").lower() not in sub_brand["sub_brands"]:
                                    stock_detail = {
                                        "PRDCODE": remove_kn(kino_stock.get("item_code")) if not kino_stock.get("supplier_part_no") else remove_kn(kino_stock.get("supplier_part_no")),
                                        "WHLOC1": whloc1,
                                        "WHLOC2": whloc2,
                                        "QTY": kino_stock.get("balance")
                                    }
                                    try:
                                        detail = header_template[header]["DATA"][0]["DETAIL"]
                                    except (KeyError, IndexError):
                                        header_template[header]["DATA"].append({"DETAIL": []})
                                    header_template[header]["DATA"][0]["DETAIL"].append(stock_detail)
                            if sub_brand["warehouse"] != kino_stock.get("warehouse"):
                                stock_detail = {
                                    "PRDCODE": remove_kn(kino_stock.get("item_code")) if not kino_stock.get("supplier_part_no") else remove_kn(kino_stock.get("supplier_part_no")),
                                    "WHLOC1": whloc1,
                                    "WHLOC2": whloc2,
                                    "QTY": kino_stock.get("balance")
                                }
                                try:
                                    detail = header_template[header]["DATA"][0]["DETAIL"]
                                except (KeyError, IndexError):
                                    header_template[header]["DATA"].append({"DETAIL": []})
                                header_template[header]["DATA"][0]["DETAIL"].append(stock_detail)
                    else:
                        stock_detail = {
                            "PRDCODE": remove_kn(kino_stock.get("item_code")) if not kino_stock.get("supplier_part_no") else remove_kn(kino_stock.get("supplier_part_no")),
                            "WHLOC1": whloc1,
                            "WHLOC2": whloc2,
                            "QTY": kino_stock.get("balance")
                        }
                        try:
                            detail = header_template[header]["DATA"][0]["DETAIL"]
                        except (KeyError, IndexError):
                            header_template[header]["DATA"].append({"DETAIL": []})
                        header_template[header]["DATA"][0]["DETAIL"].append(stock_detail)
        return header_template
    except Exception:
        raise Exception(traceback.format_exc())
        


def safe_response_json(response):
    try:
        return response.json()
    except ValueError:
        return None

def post_stock(data:dict = None):
    try:
        item_code = None
        warehouse = None
        date=None
        if data:
            item_code = data.get('item_code',None)
            warehouse = data.get('warehouse',None)
            date=data.get('date',None)
        payload_all_warehouse = create_stock_payload(item_code = item_code,warehouse=warehouse,date=date)
        for key,value in payload_all_warehouse.items():
            config = get_kino_config(branch_code=key[1],entity_code=key[2],warehouse=key[0])
            access_token = login(branch_code=key[1],entity_code=key[2],warehouse=key[0])['access_token']
            response = requests.post(
                url = config["kino_host"] + "api/stock/balance",
                json = value,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                timeout=(5,10)
            )
            response_data = safe_response_json(response)
            logger.log({
                "title": "STOCK_POST",
                "method": "POST",
                "status_code": response.status_code,
                "kino_status": response_data.get("status") if response_data else None,
                "request": json.dumps(value),
                "response": json.dumps(response_data) if response_data else response.text
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
        print(traceback.format_exc())

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
        calc.transaction_date as posting_date,
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
        result = execute_query_fetch(query=query)
        if result:
            for row in result:
                item_code = row.get("item_code")
                if item_code:
                    dbp_price = select_dbp_price(item_code,end_date)
                    if dbp_price is not None:
                        row["price_list_rate_dbp"] = dbp_price

            return result
    except Exception as error:
        raise Exception(traceback.format_exc())

def create_update_invoice_payload_dn(order_ref_list:list=[],order_ref:str=None,start_date:str=None,end_date:str=None,cancel:bool=False):
    if order_ref_list:
        refs = "', '".join(order_ref_list)
        sql_condition = f"AND dni.against_sales_order IN ('{refs}')"
    else:
        sql_condition = f"AND dni.against_sales_order = '{order_ref}'" if order_ref else ""
    date_condition = f"AND dn.posting_date BETWEEN '{start_date}' AND '{end_date}'" if start_date and end_date else ""
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
        calc.posting_date,
        calc.set_warehouse as warehouse,
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
            so.set_warehouse,
            dn.posting_date,
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
        AND dn.docstatus = 1
        AND dn.is_return = {is_return}
        {date_condition}
        {sql_condition}
    ) calc
    WHERE calc.quantity != 0
    GROUP BY calc.dni_name, calc.pi_name
    ORDER BY calc.transaction_date, calc.name, calc.dni_name, calc.pi_name
    """
    result = execute_query_fetch(query=query)
    if result:
        for row in result:
            item_code = row.get("item_code")
            if item_code:
                dbp_price = select_dbp_price(item_code,end_date)
                if dbp_price is not None:
                    row["price_list_rate_dbp"] = dbp_price
        return result

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

def repost_failed_invoice(data_dict:dict):
    order_ref = data_dict.get('ORDER_REF')
    end_date = data_dict.get('END_DATE')
    order_ref_list = data_dict.get('ORDER_REF_LIST',[])
    try:
        payload_stock_all_warehouse = create_stock_payload(item_code = None,warehouse=None,date=end_date)
        if order_ref_list:
            # check dn submitted
            raw_payloads_dn_submit = create_update_invoice_payload_dn(
                order_ref_list=order_ref_list
            )
            if raw_payloads_dn_submit:
                worker_send_invoice(raw_payloads=raw_payloads_dn_submit,stock_payload=payload_stock_all_warehouse)
            # check dn rdo
            raw_payloads_dn_submit_rdo = create_update_invoice_payload_dn(
                order_ref_list=order_ref_list,
                cancel=True
            )
            if raw_payloads_dn_submit_rdo:
                worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads_dn_submit_rdo,stock_payload=payload_stock_all_warehouse)
            # check so cancel
            raw_payloads_so_cancel = create_post_invoice_payload(
                order_ref_list=order_ref_list,
                is_cancel=True
            )
            if raw_payloads_so_cancel:
                worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads_so_cancel,stock_payload=payload_stock_all_warehouse)
        else:
            for order in order_ref:
                # check dn submitted
                raw_payloads_dn_submit = create_update_invoice_payload_dn(
                    order_ref=order
                )
                if raw_payloads_dn_submit:
                    worker_send_invoice(raw_payloads=raw_payloads_dn_submit,stock_payload=payload_stock_all_warehouse)
                # check dn rdo
                raw_payloads_dn_submit_rdo = create_update_invoice_payload_dn(
                    order_ref=order,
                    cancel=True
                )
                if raw_payloads_dn_submit_rdo:
                    worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads_dn_submit_rdo,stock_payload=payload_stock_all_warehouse)
                # check so cancel
                raw_payloads_so_cancel = create_post_invoice_payload(
                    order_ref=order,
                    is_cancel=True
                )
                if raw_payloads_so_cancel:
                    worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads_so_cancel,stock_payload=payload_stock_all_warehouse)
    except Exception:
        err_text = traceback.format_exc()
        logger.log({
            "url": None,
            "title": "REPOST_INVOICE_ERROR",
            "order_ref": None,
            "method": "POST",
            "status_code": 500,
            "kino_status": None,
            "request": None,
            "response": err_text
        })

def grouped_data_by_order_id(query_result: list, is_cancel: bool = False):
    inv_type = "INV02"
    if is_cancel:
        inv_type = "RET01"

    grouped_data = {}

    for row in query_result:
        order_id = row.get('name')
        warehouse = row.get('warehouse')
        if not order_id:
            continue

        if order_id not in grouped_data:
            grouped_data[order_id] = []

            try:
                # === CUSTOMER CODE ===
                store = row.get('store')
                channel = row.get('channel')

                cust_code1, cust_code2, entity_code, branch_code, region_code = \
                    get_customer_code(
                        store=store,
                        channel=channel
                    )

                salesman_code = get_salesman_code(
                    key=(region_code, entity_code, branch_code)
                )['gms_salesman_id']

                transaction_date = (
                    row.get("transaction_date").isoformat()
                    if row.get("transaction_date")
                    else None
                )

                posting_date = (
                    row.get('posting_date').isoformat()
                    if row.get('posting_date')
                    else None
                )
                new_transaction_date = check_trasaction_date_over_closing_date_kino(transaction_date=transaction_date,dn_posting_date=posting_date,is_cancel=is_cancel)

                grouped_data[order_id].append({
                    'REGION_CODE': region_code,
                    'BRANCH_CODE': branch_code,
                    'ENTITY_CODE': str(entity_code),
                    'CUST_CODE1': cust_code1,
                    'CUST_CODE2': cust_code2,
                    'SALESMAN_CODE': salesman_code,
                    'INV_TYPE': inv_type,
                    'ORDER_REF': order_id,
                    'ORDER_DATE': new_transaction_date,
                    'SFA_TGLORDER': new_transaction_date,
                    'SFA_ORDERNO': order_id,
                    'SFA_SLSNO': salesman_code,
                    "WAREHOUSE": warehouse
                })

            except Exception as e:
                #skip order ini aja
                print(f"[SKIP ORDER {order_id}] {e}")
                grouped_data.pop(order_id, None)
                continue

    return grouped_data

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

            # kalau item_code belum ada then create
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

            # kalau item_code sudah ada then SUM
            else:
                item = grouped_detail[order_id][item_code]
                item['QTY'] += abs(row.get('quantity', 0.0))
                item['GROSS'] += abs(row.get('total_amount', 0.0))
                item['TAX_AMT'] += abs(row.get('tax_amount', 0.0))
                item['NET'] += abs(row.get('amount', 0.0))

        # convert dict ke list (biar sama kayak sebelumnya)
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

def worker_send_invoice(raw_payloads, is_cancel=False, stock_payload=None):
    from services import kino_get_replacement_item
    grouped = {}
    kino_items_replacement = kino_get_replacement_item()

    for row in raw_payloads:
        so_ref = row.get('name')
        item_code = row.get('item_code')
        if kino_items_replacement:
            for replancement_item in kino_items_replacement:
                if replancement_item['item_code'] == item_code:
                    row['item_code'] = replancement_item['supplier_part_no']
                    break
        
        if not so_ref:
            continue
        grouped.setdefault(so_ref, []).append(row)

    for so_ref, rows in grouped.items():
        try:
            payload = build_payload(rows, is_cancel=is_cancel)

            header = payload[0]['DATA'][0]
            payload_key = (
                header['WAREHOUSE'],
                header['BRANCH_CODE'],
                header['ENTITY_CODE']
            )

            config = get_kino_config(
                branch_code=header['BRANCH_CODE'],
                entity_code=header['ENTITY_CODE'],
                warehouse=header['WAREHOUSE'],
                force_reload=True
            )

            stock_payload_header = {
                payload_key: {
                    "INTERFACEID": "T006",
                    "CLIENTID": config.get('kino_client_id'),
                    "DATA": [{"DETAIL": []}]
                }
            }
            aggregate_item_code = defaultdict(int)

            for data in payload[0].get("DATA", []):
                for detail in data.get("DETAIL", []):
                    pcode = detail["PCODE"]
                    qty = detail["QTY"]
                    aggregate_item_code[pcode] += qty

            stock_map = {}

            if stock_payload:
                for key, stock in stock_payload.items():
                    if key != payload_key:
                        continue

                    for stock_detail in stock.get("DATA", [])[0].get("DETAIL", []):
                        map_key = key + (stock_detail["PRDCODE"],)

                        if map_key not in stock_map:
                            stock_map[map_key] = {
                                "PRDCODE": stock_detail["PRDCODE"],
                                "WHLOC1": stock_detail["WHLOC1"],
                                "WHLOC2": stock_detail["WHLOC2"],
                                "QTY": stock_detail["QTY"]
                            }
                        else:
                            stock_map[map_key]["QTY"] += stock_detail["QTY"]

            for (warehouse,branch_code,entity_code,pcode), stock_detail in stock_map.items():
                if pcode not in aggregate_item_code:
                    continue

                stock_payload_header[payload_key]["DATA"][0]["DETAIL"].append({
                    "PRDCODE": pcode,
                    "WHLOC1": stock_detail["WHLOC1"],
                    "WHLOC2": stock_detail["WHLOC2"],
                    "QTY": stock_detail["QTY"] + aggregate_item_code[pcode]
                })
            
            if stock_payload_header[payload_key]["DATA"][0]["DETAIL"]:
                post_stock(data=stock_payload_header[payload_key])
            if is_cancel:
                latest_increment = get_last_cancelled_order_ref_name(order_ref=so_ref)

                if latest_increment:
                    new_order_ref = increment_name(
                        order_ref=latest_increment[0]['order_ref']
                    )
                else:
                    new_order_ref = increment_name(order_ref=so_ref)

                payload[0]['DATA'][0]['ORDER_REF'] = new_order_ref
                payload[0]['DATA'][0]['SFA_ORDERNO'] = new_order_ref

                cancel_order = check_cancelled_invoice(order_ref=so_ref)

                if not cancel_order:
                    send_single_invoice(payload, is_cancel=is_cancel)   
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
            print(err_text)

def send_single_invoice(payload: json,is_cancel:bool=False):
    inv_type = "INV02"
    if is_cancel:
        inv_type = "RET01"
    data = payload
    header = payload[0]['DATA'][0]
    config = get_kino_config(
        branch_code=header['BRANCH_CODE'],
        entity_code=header['ENTITY_CODE'],
        warehouse=header['WAREHOUSE'],
        force_reload=True
    )
    token = login(
        branch_code=header['BRANCH_CODE'],
        entity_code=header['ENTITY_CODE'],
        warehouse=header['WAREHOUSE']
    )['access_token']
    data[0]['CLIENTID'] = config.get('kino_client_id')
    # buang warehouse
    for header in data:
        for item in header.get("DATA", []):
            item.pop("WAREHOUSE", None)

    url = config.get('kino_host')+'api/ids/extclient/masterpayload'
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    try:
        response = requests.post(url, json=data[0], headers=headers,timeout=(5,60))

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
            "kino_status":None,
            "request": data[0],
            "response": e
        })
        print("Error sending payload:", err_text)
        return {"status": "error", "payload": payload, "response": str(e)}

def ids_post_invoice(data_dict: dict):
    order_ref = data_dict.get('ORDER_REF')
    start_date = data_dict.get('START_DATE')
    end_date = data_dict.get('END_DATE')
    try:
        # send first sales order
        payload_stock_all_warehouse = create_stock_payload(item_code = None,warehouse=None,date=end_date)
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
                    worker_send_invoice(raw_payloads=raw_payloads,stock_payload = payload_stock_all_warehouse)
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
                worker_send_invoice(raw_payloads=raw_payloads,stock_payload = payload_stock_all_warehouse)
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
                    worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads,stock_payload = payload_stock_all_warehouse)
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
                worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads,stock_payload = payload_stock_all_warehouse)
        
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
                    worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads,stock_payload = payload_stock_all_warehouse)
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
                worker_send_invoice(is_cancel=True,raw_payloads=raw_payloads,stock_payload = payload_stock_all_warehouse)
        

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

if __name__ == '__main__':
    import pprint
    from kino_api_test import mock_data_query_invoice
    payload_stock_all_warehouse = create_stock_payload(item_code ='OVALE-DUMMYBLUE',warehouse=None,date='2026-04-24')
    # worker_send_invoice(raw_payloads=mock_data_query_invoice(),stock_payload=payload_stock_all_warehouse)
    print(payload_stock_all_warehouse)
