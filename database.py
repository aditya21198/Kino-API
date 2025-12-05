import os
import sys
from decimal import Decimal
import traceback
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

#Load env
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_LOGGER_NAME = os.getenv("DB_LOG_NAME")

# Global engine/session holder
ENGINES = {}
SESSIONS = {}
BASES = {}

def make_db_connection(is_logger=False):
    key = "logger" if is_logger else "main"

    # return existing connection
    if key in SESSIONS:
        return SESSIONS[key], BASES[key]

    db_name = DB_LOGGER_NAME if is_logger else DB_NAME

    DATABASE_URL = (
        f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{db_name}"
    )

    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

    # Simpan global
    ENGINES[key] = engine
    SESSIONS[key] = SessionLocal
    BASES[key] = Base

    return SessionLocal, Base

def execute_query_fetch(query: str, params: tuple = (), is_logger=False):
    SessionLocal, _ = make_db_connection(is_logger=is_logger)
    db = SessionLocal()

    try:
        # raw connection
        raw = db.connection().connection
        cursor = raw.cursor()

        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            return None

        columns = [col[0] for col in cursor.description]

        result_dict = [
            {
                col: float(val) if isinstance(val, Decimal) else val
                for col, val in zip(columns, row)
            }
            for row in rows
        ]

        cursor.close()
        return result_dict

    except Exception:
        print("DB Error:", traceback.format_exc())
        return None

    finally:
        db.close()

def get_price_list(item_code: str, price_list: str):
    SessionLocal, _ = make_db_connection()
    db = SessionLocal()

    try:
        raw = db.connection().connection
        cursor = raw.cursor()

        query = """
            SELECT valid_from, price_list, currency, price_list_rate
            FROM `tabItem Price`
            WHERE item_code = %s
            AND price_list = %s
            ORDER BY valid_from DESC
            LIMIT 1
        """

        cursor.execute(query, (item_code, price_list))
        rows = cursor.fetchall()

        if not rows:
            return None

        columns = [col[0] for col in cursor.description]

        result_dict = [
            {
                col: float(val) if isinstance(val, Decimal) else val
                for col, val in zip(columns, row)
            }
            for row in rows
        ]

        cursor.close()
        return result_dict

    except Exception:
        print("DB Error:", traceback.format_exc())
        return None

    finally:
        db.close()
