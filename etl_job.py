import psycopg2
import os
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import logging

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    """Establishes a connection to the database."""
    try:
        conn = psycopg2.connect(
            host="db",
            database=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"]
        )
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Could not connect to database: {e}")
        raise

def update_overdue_tasks(cur):
    """Marks tasks as overdue and increments the overdue day counter."""
    logging.info("Checking for overdue tasks...")
    # Update tasks that are past their deadline and not completed
    cur.execute("""
        UPDATE task_assignments
        SET 
            is_overdue = TRUE,
            days_overdue = days_overdue + 1
        WHERE deadline < NOW() AND NOT is_completed;
    """)
    updated_count = cur.rowcount
    logging.info(f"Updated {updated_count} overdue task(s).")

def create_new_assignments(cur):
    """Creates new assignments for recurring tasks."""
    logging.info("Checking for new recurring tasks to create...")
    
    # Get all tasks that are not 'One time'
    cur.execute("SELECT id, description, frequency FROM tasks WHERE frequency != 'One time';")
    recurring_tasks = cur.fetchall()
    
    today = date.today()
    
    for task_id, description, frequency in recurring_tasks:
        # Find all users assigned to this task's previous instances
        cur.execute("""
            SELECT DISTINCT user_id FROM task_assignments WHERE task_id = %s;
        """, (task_id,))
        assigned_users = [row[0] for row in cur.fetchall()]

        if not assigned_users:
            continue

        # Determine the next deadline based on the frequency
        next_deadline = None
        if frequency == 'Daily':
            next_deadline = today + timedelta(days=1)
        elif frequency == 'Weekly':
            next_deadline = today + timedelta(weeks=1)
        # Add other frequencies as needed...

        if next_deadline:
            logging.info(f"Creating new '{frequency}' assignment for task '{description}' with deadline {next_deadline}.")
            # Insert new assignments for each user for the next period
            for user_id in assigned_users:
                cur.execute("""
                    INSERT INTO task_assignments (task_id, user_id, deadline)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (task_id, user_id, deadline) DO NOTHING;
                """, (task_id, user_id, next_deadline))


def main():
    """Main function to run the ETL job."""
    logging.info("Starting daily ETL job...")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        update_overdue_tasks(cur)
        # In a real scenario, you would expand this logic significantly
        # create_new_assignments(cur) # You can enable this when ready
        
        conn.commit()
        cur.close()
        logging.info("ETL job finished successfully.")
    except (Exception, psycopg2.DatabaseError) as error:
        logging.error(f"Error in ETL job: {error}")
        if conn is not None:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    main()