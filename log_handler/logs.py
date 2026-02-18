# logs.py
import json
import traceback
from database import make_db_connection

class KinoLogger:
    def __init__(self, table_name="kino_api_logs", is_logger=True,is_asi=False):
        self._table = table_name
        self.is_logger = is_logger
        self.is_asi = is_asi

        SessionLocal, _ = make_db_connection(is_logger=is_logger,is_asi=is_asi)
        self.SessionLocal = SessionLocal

    def ensure_table(self, log_keys):
        db = self.SessionLocal()
        conn = db.connection().connection
        cur = conn.cursor()

        try:
            # check table exist
            cur.execute("SHOW TABLES LIKE %s", (self._table,))
            exists = cur.fetchone()

            if not exists:
                # Table doesn’t exist → make new columns
                base_columns = [
                    "id INT AUTO_INCREMENT PRIMARY KEY",
                    "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ]

                dynamic_columns = []
                for k in log_keys:
                    if "json" in k.lower():
                        dynamic_columns.append(f"`{k}` LONGTEXT")
                    else:
                        dynamic_columns.append(f"`{k}` TEXT")

                create_sql = f"""
                    CREATE TABLE `{self._table}` (
                        {', '.join(base_columns + dynamic_columns)}
                    )
                """
                cur.execute(create_sql)

            else:
                # Table exists → ensure columns exist
                cur.execute(f"DESCRIBE `{self._table}`")
                existing_cols = {row[0] for row in cur.fetchall()}

                # ensure created_at column always exists
                if "created_at" not in existing_cols:
                    cur.execute(
                        f"ALTER TABLE `{self._table}` "
                        "ADD COLUMN `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP"
                    )

                # ensure dynamic columns exist
                for k in log_keys:
                    if k not in existing_cols:
                        col_type = "LONGTEXT" if "json" in k.lower() else "TEXT"
                        cur.execute(
                            f"ALTER TABLE `{self._table}` ADD COLUMN `{k}` {col_type}"
                        )

            conn.commit()

        except Exception:
            print("Table Ensure Error:", traceback.format_exc())
            conn.rollback()

        finally:
            cur.close()
            db.close()


    def log(self, logs: dict):
        db = self.SessionLocal()
        conn = db.connection().connection
        cur = conn.cursor()

        try:
            # serialize json-like values
            processed_logs = {}
            for k, v in logs.items():
                if isinstance(v, (dict, list)):
                    processed_logs[k] = json.dumps(v)
                else:
                    processed_logs[k] = v

            # ensure table + columns exist
            self.ensure_table(processed_logs.keys())

            # build insert query
            columns = ', '.join([f"`{k}`" for k in processed_logs.keys()])
            values_placeholders = ', '.join(['%s'] * len(processed_logs))

            sql = (
                f"INSERT INTO `{self._table}` ({columns}) "
                f"VALUES ({values_placeholders})"
            )

            cur.execute(sql, list(processed_logs.values()))
            conn.commit()

            return cur.lastrowid

        except Exception:
            print("Log Insert Error:", traceback.format_exc())
            conn.rollback()
            return None

        finally:
            cur.close()
            db.close()
    
    def log_bulk(self, logs_list: list, batch_size: int = 1000):
        if self._table == "kino_api_logs":
            return 0
        if not self.is_asi:
            return 0
        if not logs_list:
            return 0

        db = self.SessionLocal()
        conn = db.connection().connection
        cur = conn.cursor()

        try:
            # normalize & serialize
            processed_list = []
            for logs in logs_list:
                processed_row = {}
                for k, v in logs.items():
                    if isinstance(v, (dict, list)):
                        processed_row[k] = json.dumps(v)
                    else:
                        processed_row[k] = v
                processed_list.append(processed_row)

            # ensure table & columns exist
            all_keys = set()
            for row in processed_list:
                all_keys.update(row.keys())

            self.ensure_table(all_keys)

            columns = list(all_keys)
            columns_sql = ', '.join([f"`{k}`" for k in columns])
            placeholders = ', '.join(['%s'] * len(columns))

            sql = f"""
                INSERT INTO `{self._table}` ({columns_sql})
                VALUES ({placeholders})
            """

            # prepare values in correct column order
            values = []
            for row in processed_list:
                values.append(tuple(row.get(col) for col in columns))

            # batch insert
            for i in range(0, len(values), batch_size):
                batch = values[i:i+batch_size]
                cur.executemany(sql, batch)

            conn.commit()
            return len(values)

        except Exception:
            print("Bulk Log Insert Error:", traceback.format_exc())
            conn.rollback()
            return 0

        finally:
            cur.close()
            db.close()
