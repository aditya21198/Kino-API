from pydantic import BaseModel
from typing import List, Optional

class ManualPostInvoiceKino(BaseModel):
    ORDER_REF:Optional[list] = None
    START_DATE:str
    END_DATE:str

class KinoPostStock(BaseModel):
    item_code:Optional[str]
    warehouse:Optional[str]