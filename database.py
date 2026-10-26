import os

import mysql.connector


def get_connection():
    user = os.getenv("DB_USER") or os.getenv("MYSQL_USER")
    password = os.getenv("DB_PASSWORD") or os.getenv("MYSQL_PASSWORD")
    if not user or not password:
        raise RuntimeError("Set DB_USER/DB_PASSWORD or MYSQL_USER/MYSQL_PASSWORD.")

    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=(
            os.getenv("DB_NAME")
            or os.getenv("MYSQL_DATABASE")
            or "supply_chain_risk_management"
        ),
        user=user,
        password=password,
    )
