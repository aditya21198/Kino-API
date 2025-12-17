import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import end_of_the_day_invoice_job
import traceback
def main():
    try:
        end_of_the_day_invoice_job()
    except Exception:
        print(traceback.format_exc())

if __name__ == "__main__":
    main()