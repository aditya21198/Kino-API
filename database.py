import os
import sys
from decimal import Decimal
import traceback
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

#Load env
load_dotenv()

# DB_USER = os.getenv("DB_USER")
# DB_PASS = os.getenv("DB_PASS")
# DB_HOST = os.getenv("DB_HOST")
# DB_PORT = os.getenv("DB_PORT")
# DB_NAME = os.getenv("DB_NAME")
# DB_LOGGER_NAME = os.getenv("DB_LOG_NAME")

# Global engine/session holder
ENGINES = {}
SESSIONS = {}
BASES = {}

def make_db_connection(is_logger=False,is_asi=False,is_providers=False):
    if is_asi:
        DB_USER = os.getenv("DB_USER_ASI")
        DB_PASS = os.getenv("DB_PASS_ASI")
        DB_HOST = os.getenv("DB_HOST_ASI")
        DB_PORT = os.getenv("DB_PORT_ASI")
        DB_NAME = os.getenv("DB_NAME_ASI")
        DB_LOGGER_NAME = os.getenv("DB_LOG_NAME_ASI")
    else:
        DB_USER = os.getenv("DB_USER")
        DB_PASS = os.getenv("DB_PASS")
        DB_HOST = os.getenv("DB_HOST")
        DB_PORT = os.getenv("DB_PORT")
        DB_NAME = os.getenv("DB_NAME")
        DB_LOGGER_NAME = os.getenv("DB_LOG_NAME")
    
    if is_logger:
        key = 'logger'
    elif is_asi:
        key = 'asi'
    else:
        key = 'main'

    # key = "logger" if is_logger else "main"

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

def update_table(query:str,is_logger=False,is_asi=False):
    SessionLocal, _ = make_db_connection(is_logger=is_logger,is_asi=is_asi)
    db = SessionLocal()
    try:
        raw = db.connection().connection
        cursor = raw.cursor()
        cursor.execute(query)
        raw.commit()
        cursor.close()
        return True
    except Exception:
        print("DB Error:", traceback.format_exc())
        return False
    finally:
        db.close()

def execute_query_fetch(query: str, params: tuple = (), is_logger=False,is_asi=False):
    SessionLocal, _ = make_db_connection(is_logger=is_logger,is_asi=is_asi)
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
