import psycopg2
import os

DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("POSTGRES_DB", "checklist")
DB_USER = os.environ.get("POSTGRES_USER", "user")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "password")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def get_tasks():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM tasks ORDER BY id;")
    tasks = cur.fetchall()
    conn.close()
    return tasks

def add_task(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO tasks (name) VALUES (%s);", (name,))
    conn.commit()
    conn.close()

def delete_task(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s;", (id,))
    conn.commit()
    conn.close()
