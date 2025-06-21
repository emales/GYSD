from fastapi import FastAPI, Request, Form, Response, Cookie, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles 
import psycopg2
import os
import uuid
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta, date

os.chdir(os.path.dirname(__file__))

# --- Configuration ---
SECRET_KEY = os.environ['SECRET_KEY']  # IMPORTANT: Change this to a long, random, secret key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- FastAPI App Initialization ---
app = FastAPI()

# --- Static Files and Templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Database Connection ---
def get_db_connection():
    return psycopg2.connect(
        host="db",
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"]
    )

# --- Security (Password Hashing and JWT) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user_id(token: str = Cookie(None)):
    if token is None:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return int(user_id)
    except (JWTError, ValueError):
        return None

# --- Routes ---
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, name: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password FROM users WHERE name = %s;", (name,))
    user_row = cur.fetchone()
    conn.close()

    if not user_row or not verify_password(password, user_row[1]):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})

    user_id = user_row[0]
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user_id), "name": name}, expires_delta=access_token_expires
    )

    response = RedirectResponse(url="/home", status_code=302)
    response.set_cookie(key="token", value=access_token, httponly=True)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    birth_date: date = Form(...),
    street: str = Form(...),
    city: str = Form(...),
    postcode: str = Form(...),
    household_name: str = Form(None)
):
    hashed_password = get_password_hash(password)
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check if a household with the same address already exists
        cur.execute("SELECT id FROM households WHERE street = %s AND city = %s AND postcode = %s;", (street, city, postcode))
        household_row = cur.fetchone()

        if household_row:
            household_id = household_row[0]
        else:
            # If no household exists, create a new one
            new_household_name = household_name if household_name else "Your Household"
            cur.execute(
                "INSERT INTO households (name, street, city, postcode) VALUES (%s, %s, %s, %s) RETURNING id;",
                (new_household_name, street, city, postcode)
            )
            household_id = cur.fetchone()[0]

        # Insert the new user with the correct household_id
        cur.execute(
            "INSERT INTO users (name, password, birth_date, street, city, postcode, household_id) VALUES (%s, %s, %s, %s, %s, %s, %s);",
            (name, hashed_password, birth_date, street, city, postcode, household_id)
        )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username already exists or there was a database error."})
    finally:
        conn.close()

    return RedirectResponse(url="/login", status_code=302)


@app.get("/home", response_class=HTMLResponse)
async def home(request: Request, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db_connection()
    cur = conn.cursor()

    # Get user info and their household ID
    cur.execute("SELECT name, household_id FROM users WHERE id = %s;", (user_id,))
    user_info = cur.fetchone()
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    user_name, household_id = user_info

    # Get tasks assigned to the current user
    cur.execute("""
        SELECT t.id, t.description, t.completed
        FROM tasks t
        JOIN task_assignments ta ON t.id = ta.task_id
        WHERE ta.user_id = %s
        ORDER BY t.id;
    """, (user_id,))
    tasks = cur.fetchall()

    conn.close()
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "tasks": tasks,
            "user_name": user_name
        }
    )


@app.get("/add-task", response_class=HTMLResponse)
async def add_task_page(request: Request, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT household_id FROM users WHERE id = %s;", (user_id,))
    household_id_row = cur.fetchone()
    household_id = household_id_row[0] if household_id_row else None

    household_members = []
    if household_id:
        cur.execute("SELECT id, name FROM users WHERE household_id = %s ORDER BY name;", (household_id,))
        household_members = cur.fetchall()
    
    conn.close()
    
    return templates.TemplateResponse(
        "add_task.html",
        {
            "request": request,
            "household_members": household_members
        }
    )


@app.post("/add-task")
async def add_task_form_submission(
    description: str = Form(...),
    assignee: str = Form(...),
    user_id: int = Depends(get_current_user_id)
):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO tasks (description) VALUES (%s) RETURNING id;", (description,))
    task_id = cur.fetchone()[0]

    if assignee == "all":
        # Get the household ID of the logged-in user
        cur.execute("SELECT household_id FROM users WHERE id = %s;", (user_id,))
        household_id_row = cur.fetchone()
        if household_id_row:
            household_id = household_id_row[0]
            # Get all users in that household
            cur.execute("SELECT id FROM users WHERE household_id = %s;", (household_id,))
            members = cur.fetchall()
            for member in members:
                cur.execute("INSERT INTO task_assignments (task_id, user_id) VALUES (%s, %s);", (task_id, member[0]))
    else:
        # Assign to a specific user
        cur.execute("INSERT INTO task_assignments (task_id, user_id) VALUES (%s, %s);", (task_id, int(assignee)))

    conn.commit()
    conn.close()
    return RedirectResponse(url="/home", status_code=302)


@app.get("/lists", response_class=HTMLResponse)
async def lists_page(request: Request, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("lists.html", {"request": request})


@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("token")
    return response
