from fastapi import FastAPI, Request, Form, Response, Cookie
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import psycopg2
import os
import uuid

os.chdir(os.path.dirname(__file__))

app = FastAPI()

# Shramba sej v spominu (za produkcijo raje DB/redis)
sessions = {}

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

def get_db_connection():
    return psycopg2.connect(
        host="db",
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"]
    )

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/login")
async def login(response: Response, name: str = Form(...)):
    # Vstavi uporabnika v DB, če še ne obstaja
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (name,))
    conn.commit()
    cur.execute("SELECT id FROM users WHERE name = %s;", (name,))
    user_row = cur.fetchone()
    conn.close()

    if not user_row:
        return RedirectResponse(url="/", status_code=302)  # Nekaj je šlo narobe

    user_id = user_row[0]

    # Ustvari session_id in shrani v sessions
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"user_id": user_id, "name": name}

    # Nastavi cookie z session_id
    response = RedirectResponse(url="/home", status_code=302)
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response

@app.get("/home")
async def home(request: Request, session_id: str = Cookie(None)):
    if not session_id or session_id not in sessions:
        return RedirectResponse(url="/", status_code=302)
    user_id = sessions[session_id]["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.description, t.completed
        FROM tasks t
        JOIN task_assignments ta ON t.id = ta.task_id
        WHERE ta.user_id = %s
        ORDER BY t.id;
    """, (user_id,))
    tasks = cur.fetchall()
    cur.execute("SELECT id, name FROM users ORDER BY name;")
    users = cur.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "tasks": tasks, "user_name": sessions[session_id]["name"], "users": users}
    )

@app.get("/logout")
async def logout(response: Response, session_id: str = Cookie(None)):
    if session_id in sessions:
        sessions.pop(session_id)
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_id")
    return response
