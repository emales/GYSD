from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from jose import jwt, JWTError

# --- Configuration & Setup ---
router = APIRouter()
templates = Jinja2Templates(directory="templates")
SECRET_KEY = os.environ.get('SECRET_KEY', 'a_very_secret_key')
ALGORITHM = "HS256"

# --- Database Connection ---
def get_db_connection():
    return psycopg2.connect(
        host="db",
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        cursor_factory=RealDictCursor
    )

# --- Dependency ---
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

# --- Task Routes ---
@router.get("/home", response_class=HTMLResponse)
async def home(request: Request, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    user_name = cur.fetchone()['name']

    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # Tasks due today
    cur.execute("""
        SELECT ta.id, t.description, ta.deadline
        FROM tasks t
        JOIN task_assignments ta ON t.id = ta.task_id
        WHERE ta.user_id = %s AND ta.deadline::date = %s AND NOT ta.is_completed
        ORDER BY ta.deadline;
    """, (user_id, today))
    tasks_today = cur.fetchall()

    # Tasks due this week (excluding today)
    cur.execute("""
        SELECT ta.id, t.description, ta.deadline
        FROM tasks t
        JOIN task_assignments ta ON t.id = ta.task_id
        WHERE ta.user_id = %s AND ta.deadline::date > %s AND ta.deadline::date <= %s AND NOT ta.is_completed
        ORDER BY ta.deadline;
    """, (user_id, today, end_of_week))
    tasks_week = cur.fetchall()

    # Other tasks (due after this week)
    cur.execute("""
        SELECT ta.id, t.description, ta.deadline
        FROM tasks t
        JOIN task_assignments ta ON t.id = ta.task_id
        WHERE ta.user_id = %s AND ta.deadline::date > %s AND NOT ta.is_completed
        ORDER BY ta.deadline DESC;
    """, (user_id, end_of_week))
    tasks_other = cur.fetchall()

    conn.close()
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user_name": user_name,
            "tasks_today": [tuple(row.values()) for row in tasks_today],
            "tasks_week": [tuple(row.values()) for row in tasks_week],
            "tasks_other": [tuple(row.values()) for row in tasks_other],
        }
    )
    
@router.get("/add-task", response_class=HTMLResponse)
async def add_task_page(request: Request, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT household_id FROM users WHERE id = %s;", (user_id,))
    household_id_row = cur.fetchone()
    household_id = household_id_row['household_id'] if household_id_row else None

    household_members = []
    if household_id:
        cur.execute("SELECT id, name FROM users WHERE household_id = %s ORDER BY name;", (household_id,))
        household_members = cur.fetchall()
    
    conn.close()
    
    return templates.TemplateResponse(
        "add_task.html",
        {
            "request": request,
            "household_members": [tuple(row.values()) for row in household_members]
        }
    )

@router.post("/add-task")
async def add_task_form_submission(
    description: str = Form(...),
    assignee: str = Form(...),
    frequency: str = Form(...),
    custom_frequency_value: int = Form(None),
    custom_frequency_unit: str = Form(None),
    deadline: date = Form(None),
    user_id: int = Depends(get_current_user_id)
):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db_connection()
    cur = conn.cursor()

    # Create the task
    cur.execute("INSERT INTO tasks (description, frequency) VALUES (%s, %s) RETURNING id;", (description, frequency))
    task_id = cur.fetchone()['id']

    # Determine assignees
    assignees = []
    if assignee == "all":
        cur.execute("SELECT household_id FROM users WHERE id = %s;", (user_id,))
        household_id = cur.fetchone()['household_id']
        cur.execute("SELECT id FROM users WHERE household_id = %s;", (household_id,))
        assignees = [row['id'] for row in cur.fetchall()]
    else:
        assignees.append(int(assignee))

    # Calculate the deadline for the first assignment
    first_deadline = None
    today = date.today()
    if frequency == 'One time':
        first_deadline = deadline
    elif frequency == 'Daily':
        first_deadline = today
    elif frequency == 'Weekly':
        first_deadline = today + timedelta(weeks=1)
    elif frequency == 'Monthly':
        first_deadline = today + relativedelta(months=1)
    elif frequency == 'Custom':
        if custom_frequency_unit == 'day':
            first_deadline = today + timedelta(days=custom_frequency_value)
        elif custom_frequency_unit == 'week':
            first_deadline = today + timedelta(weeks=custom_frequency_value)
        elif custom_frequency_unit == 'month':
            first_deadline = today + relativedelta(months=custom_frequency_value)
        elif custom_frequency_unit == 'year':
            first_deadline = today + relativedelta(years=custom_frequency_value)

    # Create the single, initial task assignment
    if first_deadline:
        # Combine date with end-of-day time
        deadline_timestamp = datetime.combine(first_deadline, datetime.max.time())
        for user in assignees:
            cur.execute(
                "INSERT INTO task_assignments (task_id, user_id, deadline) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING;",
                (task_id, user, deadline_timestamp)
            )

    conn.commit()
    conn.close()
    return RedirectResponse(url="/home", status_code=302)


@router.post("/complete-task/{task_assignment_id}")
async def complete_task(task_assignment_id: int, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE task_assignments SET is_completed = TRUE, completion_timestamp = %s WHERE id = %s AND user_id = %s;",
        (datetime.now(), task_assignment_id, user_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}