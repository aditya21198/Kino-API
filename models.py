from pydantic import BaseModel
from typing import List, Optional

class ManualPostInvoiceKino(BaseModel):
    ORDER_REF:Optional[list] = None
    START_DATE:str
    END_DATE:str

class KinoPostStock(BaseModel):
    item_code:Optional[str]
    warehouse:Optional[str]
    date:Optional[str]=None

class ManualSendData(BaseModel):
    order_ref:Optional[list]=None
    start_date:Optional[str]=None
    end_date:Optional[str]=None
    item_code:Optional[str]=None
    warehouse:Optional[str]=None

class LoadDBPCache(BaseModel):
    end_date:Optional[str]=None