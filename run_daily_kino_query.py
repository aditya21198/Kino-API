import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kino.new_kino_api import load_dbp_cache
import traceback
from datetime import datetime

def main():
    try:
        today = datetime.now().date()
        print(f"Loading DBP cache for date: {today}")
        load_dbp_cache(end_date=today)
    except Exception:
        print(traceback.format_exc())

if __name__ == "__main__":
    main()