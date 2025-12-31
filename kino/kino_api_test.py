# mock data for test
import datetime
def mock_data():
    payloads = [
        {
            "INTERFACEID": "T007",
            "CLIENTID": "12",
            "DATA": [
            {
                "REGION_CODE": "1000",
                "BRANCH_CODE": "1202088",
                "ENTITY_CODE": "22",
                "CUST_CODE1": "3430OLKINO005",
                "CUST_CODE2": "OLKINO005",
                "SALESMAN_CODE": "3430LO5101",
                "INV_TYPE": "INV02",
                "ORDER_REF": "SO-ARBT-25-00028260",
                "ORDER_DATE": "2025-11-01",
                "SFA_TGLORDER": "2025-11-01",
                "SFA_ORDERNO": "SO-ARBT-25-00028260",
                "SFA_SLSNO": "3430LO5101",
                "DETAIL": [
                {
                    "PCODE": "110062",
                    "PRICE": 26216.216216,
                    "LINETYPE": "N",
                    "QTY": 2.0,
                    "GROSS": 61621.62,
                    "DISC_ID1": "",
                    "DISC_PRINCIPAL_PCT1": 0.0,
                    "DISC_PRINCIPAL_VAL1": 0.0,
                    "DISC_DIST_PCT1": "1",
                    "DISC_DIST_VAL1": "",
                    "DISC_ID2": "",
                    "DISC_PRINCIPAL_PCT2": 0.0,
                    "DISC_PRINCIPAL_VAL2": 0.0,
                    "DISC_DIST_PCT2": 0.0,
                    "DISC_DIST_VAL2": 0.0,
                    "DISC_ID3": "",
                    "DISC_PRINCIPAL_PCT3": 0.0,
                    "DISC_PRINCIPAL_VAL3": 0.0,
                    "DISC_DIST_PCT3": 0.0,
                    "DISC_DIST_VAL3": 0.0,
                    "DISC_ID4": "",
                    "DISC_PRINCIPAL_PCT4": 0.0,
                    "DISC_PRINCIPAL_VAL4": 0.0,
                    "DISC_DIST_PCT4": 0.0,
                    "DISC_DIST_VAL4": 0.0,
                    "DISC_ID5": "",
                    "DISC_PRINCIPAL_PCT5": 0.0,
                    "DISC_PRINCIPAL_VAL5": 0.0,
                    "DISC_DIST_PCT5": 0.0,
                    "DISC_DIST_VAL5": 0.0,
                    "DISC_ID6": "",
                    "DISC_PRINCIPAL_PCT6": 0.0,
                    "DISC_PRINCIPAL_VAL6": 0.0,
                    "DISC_DIST_PCT6": 0.0,
                    "DISC_DIST_VAL6": 0.0,
                    "TAX_AMT": 6778.3782,
                    "NET": 61621.62,
                    "DISC_TOTAL": 0.0
                }
                ]
            }
            ]
        },
        {
            "INTERFACEID": "T007",
            "CLIENTID": "12",
            "DATA": [
            {
                "REGION_CODE": "1000",
                "BRANCH_CODE": "1202088",
                "ENTITY_CODE": "22",
                "CUST_CODE1": "3430OLKINO006",
                "CUST_CODE2": "OLKINO006",
                "SALESMAN_CODE": "3430LO5101",
                "INV_TYPE": "INV02",
                "ORDER_REF": "SO-ARBT-25-00028488",
                "ORDER_DATE": "2025-11-01",
                "SFA_TGLORDER": "2025-11-01",
                "SFA_ORDERNO": "SO-ARBT-25-00028488",
                "SFA_SLSNO": "3430LO5101",
                "DETAIL": [
                {
                    "PCODE": "104004",
                    "PRICE": 22972.972973,
                    "LINETYPE": "N",
                    "QTY": 1.0,
                    "GROSS": 29711.71,
                    "DISC_ID1": "",
                    "DISC_PRINCIPAL_PCT1": 0.0,
                    "DISC_PRINCIPAL_VAL1": 0.0,
                    "DISC_DIST_PCT1": "1",
                    "DISC_DIST_VAL1": "",
                    "DISC_ID2": "",
                    "DISC_PRINCIPAL_PCT2": 0.0,
                    "DISC_PRINCIPAL_VAL2": 0.0,
                    "DISC_DIST_PCT2": 0.0,
                    "DISC_DIST_VAL2": 0.0,
                    "DISC_ID3": "",
                    "DISC_PRINCIPAL_PCT3": 0.0,
                    "DISC_PRINCIPAL_VAL3": 0.0,
                    "DISC_DIST_PCT3": 0.0,
                    "DISC_DIST_VAL3": 0.0,
                    "DISC_ID4": "",
                    "DISC_PRINCIPAL_PCT4": 0.0,
                    "DISC_PRINCIPAL_VAL4": 0.0,
                    "DISC_DIST_PCT4": 0.0,
                    "DISC_DIST_VAL4": 0.0,
                    "DISC_ID5": "",
                    "DISC_PRINCIPAL_PCT5": 0.0,
                    "DISC_PRINCIPAL_VAL5": 0.0,
                    "DISC_DIST_PCT5": 0.0,
                    "DISC_DIST_VAL5": 0.0,
                    "DISC_ID6": "",
                    "DISC_PRINCIPAL_PCT6": 0.0,
                    "DISC_PRINCIPAL_VAL6": 0.0,
                    "DISC_DIST_PCT6": 0.0,
                    "DISC_DIST_VAL6": 0.0,
                    "TAX_AMT": 3268.2881,
                    "NET": 29711.71,
                    "DISC_TOTAL": 0.0
                }
                ]
            }
            ]
        }
    ]
    return payloads

def mock_post_stock_maxlife():
    return {
        "INTERFACEID": "T006",
        "CLIENTID": "33",
        "DATA": [
            {
                "DETAIL": [
                    {"PRDCODE": "601004", "WHLOC1": "4001", "WHLOC2": "01", "QTY": 197}
                ]
            }
        ]
    }

def mock_post_stock_non_maxlife():
    return     {
        "INTERFACEID": "T006",
        "CLIENTID": "33",
        "DATA": [
            {
                "DETAIL": [
                    {"PRDCODE": "101001", "WHLOC1": "4001", "WHLOC2": "01", "QTY": 95}
                
                ]
            }
        ]
    }


def mock_data_rdo():
    return [
        {
            'dn': 'DO-ARB-25-00171432', 
            'name': 'SO-ARB-25-00178135', 
            'po_no': '581883197466445226', 
            'grand_total': 38900.01, 
            'master_bundle_item': '', 
            'item_code': 'KN110064', 
            'quantity': 1.0, 
            'harga_jual': 35045.05, 
            'total_amount': 35045.05, 
            'price_list_rate_dbp': 29729.72973, 
            'is_bundle_item': 0, 
            'store': 'Ovale Beauty', 
            'channel': 'Shop | Tokopedia',
            'idx': 1, 
            'sub_brand': 'OVALE', 
            'pi_idx': 0
        }, 
        {
            'dn': 'DO-ARB-25-00171432', 
            'name': 'SO-ARB-25-00178135', 
            'po_no': '581883197466445226', 
            'grand_total': 38900.01, 
            'master_bundle_item': '', 
            'item_code': 'KN110064', 
            'quantity': 1.0, 
            'harga_jual': 35045.05, 
            'total_amount': 35045.05, 
            'price_list_rate_dbp': 29729.72973, 
            'is_bundle_item': 0, 
            'store': 'Ovale Beauty', 
            'channel': 'Shop | Tokopedia', 
            'idx': 1, 
            'sub_brand': 'OVALE', 
            'pi_idx': 0
        }
    ]

def mock_data_so():
    return [
    {
        "name": "SO-ARB-25-00177945",
        "po_no": "251230NUVM6TT6",
        "transaction_date": datetime.date(2025, 12, 30),
        "grand_total_with_vat": 21960.0,

        "master_bundle_item": "KN601059B3",
        "item_code": "KN601059",
        "sub_brand": "MAXLIFE",

        "quantity": 3.0,
        "harga_jual": 19783.78,
        "total_amount": 19783.78,
        "tax_amount": 2176.2158,
        "amount": 21959.9958,

        "is_bundle_item": 1,
        "store": "MAXlife & Perro Official Store",
        "channel": "SHOPEE",

        "price_list_rate_dbp": 5888.030888
    },
    {
        "name": "SO-ARB-25-00177945",
        "po_no": "251230NUVM6TT6",
        "transaction_date": datetime.date(2025, 12, 30),
        "grand_total_with_vat": 21960.0,

        "master_bundle_item": "KN601059B3",
        "item_code": "KN601059",
        "sub_brand": "MAXLIFE",

        "quantity": 3.0,
        "harga_jual": 19783.78,
        "total_amount": 19783.78,
        "tax_amount": 2176.2158,
        "amount": 21959.9958,

        "is_bundle_item": 1,
        "store": "MAXlife & Perro Official Store",
        "channel": "SHOPEE",

        "price_list_rate_dbp": 5888.030888
    },
    {
        "name": "SO-ARB-25-00178332",
        "po_no": "251230P8F8C2C1",
        "transaction_date": datetime.date(2025, 12, 30),
        "grand_total_with_vat": 68000.0,

        "master_bundle_item": "KN104002+KN104003",
        "item_code": "KN104002",
        "sub_brand": "CLICK",

        "quantity": 1.0,
        "harga_jual": 30630.63,
        "total_amount": 30630.63,
        "tax_amount": 3369.3693,
        "amount": 33999.9993,

        "is_bundle_item": 1,
        "store": "Click Official Shop",
        "channel": "SHOPEE",

        "price_list_rate_dbp": 22972.972973
    },
    {
        "name": "SO-ARB-25-00178332",
        "po_no": "251230P8F8C2C1",
        "transaction_date": datetime.date(2025, 12, 30),
        "grand_total_with_vat": 68000.0,

        "master_bundle_item": "KN104002+KN104003",
        "item_code": "KN104003",
        "sub_brand": "CLICK",

        "quantity": 1.0,
        "harga_jual": 30630.63,
        "total_amount": 30630.63,
        "tax_amount": 3369.3693,
        "amount": 33999.9993,

        "is_bundle_item": 1,
        "store": "Click Official Shop",
        "channel": "SHOPEE",

        "price_list_rate_dbp": 22972.972973
    }
]


def mock_data_cancel_so():
    return [
        {
        "name": "SO-ARB-25-00177945",
        "po_no": "251230NUVM6TT6",
        "transaction_date": datetime.date(2025, 12, 30),
        "grand_total_with_vat": 21960.0,

        "master_bundle_item": "KN601059B3",
        "item_code": "KN601059",
        "sub_brand": "MAXLIFE",

        "quantity": 3.0,
        "harga_jual": 19783.78,
        "total_amount": 19783.78,
        "tax_amount": 2176.2158,
        "amount": 21959.9958,

        "is_bundle_item": 1,
        "store": "MAXlife & Perro Official Store",
        "channel": "SHOPEE",

        "price_list_rate_dbp": 5888.030888
    },
    {
        "name": "SO-ARB-25-00177945",
        "po_no": "251230NUVM6TT6",
        "transaction_date": datetime.date(2025, 12, 30),
        "grand_total_with_vat": 21960.0,

        "master_bundle_item": "KN601059B3",
        "item_code": "KN601059",
        "sub_brand": "MAXLIFE",

        "quantity": 3.0,
        "harga_jual": 19783.78,
        "total_amount": 19783.78,
        "tax_amount": 2176.2158,
        "amount": 21959.9958,

        "is_bundle_item": 1,
        "store": "MAXlife & Perro Official Store",
        "channel": "SHOPEE",

        "price_list_rate_dbp": 5888.030888
    }
    ]