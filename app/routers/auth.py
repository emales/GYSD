from fastapi import APIRouter, Request, Form, Depends, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from jose import jwt

# --- Configuration & Setup ---
router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ['SECRET_KEY']
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- Database Connection ---
def get_db_connection():
    return psycopg2.connect(
        host="db",
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        cursor_factory=RealDictCursor
    )
    
# --- Utility Functions ---
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

# --- Authentication Routes ---
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(request: Request, name: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password FROM users WHERE name = %s;", (name,))
    user_row = cur.fetchone()
    conn.close()

    if not user_row or not verify_password(password, user_row['password']):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})

    user_id = user_row['id']
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user_id), "name": name}, expires_delta=access_token_expires
    )

    response = RedirectResponse(url="/home", status_code=302)
    response.set_cookie(key="token", value=access_token, httponly=True)
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
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
        cur.execute("SELECT id FROM households WHERE street = %s AND city = %s AND postcode = %s;", (street, city, postcode))
        household_row = cur.fetchone()

        if household_row:
            household_id = household_row['id']
        else:
            new_household_name = household_name if household_name else "Your Household"
            cur.execute(
                "INSERT INTO households (name, street, city, postcode) VALUES (%s, %s, %s, %s) RETURNING id;",
                (new_household_name, street, city, postcode)
            )
            household_id = cur.fetchone()['id']

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

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("token")
    return response