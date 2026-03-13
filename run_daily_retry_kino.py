import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import resend_kino_invoice
from datetime import datetime
import traceback


def main():
    try:
        today = datetime.now().date()
        print(f"Loading DBP cache for date: {today}")
        resend_kino_invoice()
    except Exception:
        print(traceback.format_exc())

if __name__ == "__main__":
    main()