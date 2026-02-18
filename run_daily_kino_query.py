import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kino.kino_api import create_post_invoice_payload
import traceback

def main():
    try:
        create_post_invoice_payload()
    except Exception:
        print(traceback.format_exc())