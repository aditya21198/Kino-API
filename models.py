from pydantic import BaseModel
from typing import List, Optional

class DetailItem(BaseModel):
    PCODE: str
    PRICE: str
    LINETYPE: str
    QTY: str
    GROSS: str
    DISC_ID1: Optional[str]
    DISC_PRINCIPAL_PCT1: Optional[str]
    DISC_PRINCIPAL_VAL1: Optional[str]
    DISC_DIST_PCT1: Optional[str]
    DISC_DIST_VAL1: Optional[str]
    DISC_ID2: Optional[str]
    DISC_PRINCIPAL_PCT2: Optional[str]
    DISC_PRINCIPAL_VAL2: Optional[str]
    DISC_DIST_PCT2: Optional[str]
    DISC_DIST_VAL2: Optional[str]
    DISC_ID3: Optional[str]
    DISC_PRINCIPAL_PCT3: Optional[str]
    DISC_PRINCIPAL_VAL3: Optional[str]
    DISC_DIST_PCT3: Optional[str]
    DISC_DIST_VAL3: Optional[str]
    DISC_ID4: Optional[str]
    DISC_PRINCIPAL_PCT4: Optional[str]
    DISC_PRINCIPAL_VAL4: Optional[str]
    DISC_DIST_PCT4: Optional[str]
    DISC_DIST_VAL4: Optional[str]
    DISC_ID5: Optional[str]
    DISC_PRINCIPAL_PCT5: Optional[str]
    DISC_PRINCIPAL_VAL5: Optional[str]
    DISC_DIST_PCT5: Optional[str]
    DISC_DIST_VAL5: Optional[str]
    DISC_ID6: Optional[str]
    DISC_PRINCIPAL_PCT6: Optional[str]
    DISC_PRINCIPAL_VAL6: Optional[str]
    DISC_DIST_PCT6: Optional[str]
    DISC_DIST_VAL6: Optional[str]
    TAX_AMT: str
    NET: str
    DISC_TOTAL: str

class DataItem(BaseModel):
    REGION_CODE: str
    ENTITY_CODE: str
    BRANCH_CODE: str
    CUST_CODE1: str
    CUST_CODE2: str
    SALESMAN_CODE: str
    INV_TYPE: str
    ORDER_REF: str
    ORDER_DATE: str
    SFA_TGLORDER: str
    SFA_ORDERNO: str
    SFA_SLSNO: str
    DETAIL: List[DetailItem]

class IncomingPayload(BaseModel):
    INTERFACEID: str
    CLIENTID: str
    START_DATE:str
    END_DATE:str
    DATA: List[DataItem]


class ManualPostInvoiceKino(BaseModel):
    ORDER_REF:Optional[str] = None
    START_DATE:str
    END_DATE:str

class DetailItem(BaseModel):
    PRDCODE: str
    WHLOC1: str
    WHLOC2: str
    QTY: str


class DataItem(BaseModel):
    DETAIL: List[DetailItem]


class ManualPostStock(BaseModel):
    INTERFACEID: str
    CLIENTID: str
    DATA: List[DataItem]