import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kino.kino_api import create_post_invoice_payload
import traceback
from datetime import datetime

def main():
    try:
        today = datetime.now().date()
        create_post_invoice_payload(start_date=today, end_date=today)
    except Exception:
        print(traceback.format_exc())