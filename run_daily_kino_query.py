import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kino.kino_api import load_dbp_cache
import traceback
from datetime import datetime

def main():
    try:
        today = datetime.now().date()
        load_dbp_cache(end_date=today)
    except Exception:
        print(traceback.format_exc())