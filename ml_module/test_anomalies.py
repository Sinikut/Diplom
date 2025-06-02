# test_anomalies.py
import psycopg2
from datetime import datetime


def create_test_anomalies():
    conn = psycopg2.connect(
        dbname="testdb2",
        user="user",
        password="password",
        host="localhost"
    )
    cursor = conn.cursor()

    # 1. Опасный запрос (DROP TABLE)
    cursor.execute("""
        INSERT INTO postgres_log (timestamp, user_name, query)
        VALUES (%s, 'hacker', 'DROP TABLE users; -- SQL injection')
    """, (datetime.now(),))

    # 2. Подозрительный SELECT (возможный SQL-инъекция)
    cursor.execute("""
        INSERT INTO postgres_log (timestamp, user_name, query)
        VALUES (%s, 'suspicious_user', 'SELECT * FROM accounts WHERE 1=1 --')
    """, (datetime.now(),))

    # 3. Необычно большой запрос
    large_query = "SELECT " + ", ".join(f"column_{i}" for i in range(100)) + " FROM massive_table"
    cursor.execute("""
        INSERT INTO postgres_log (timestamp, user_name, query)
        VALUES (%s, 'data_miner', %s)
    """, (datetime.now(), large_query))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_test_anomalies()