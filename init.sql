DROP TABLE IF EXISTS task_assignments;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS households;

CREATE TABLE IF NOT EXISTS households (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    street TEXT NOT NULL,
    city TEXT NOT NULL,
    postcode TEXT NOT NULL,
    UNIQUE (street, city, postcode)
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    street TEXT NOT NULL,
    city TEXT NOT NULL,
    postcode TEXT NOT NULL,
    birth_date DATE NOT NULL,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    description TEXT NOT NULL,
    frequency TEXT
);

CREATE TABLE IF NOT EXISTS task_assignments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    assignment_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    completion_timestamp TIMESTAMP,
    deadline TIMESTAMP,
    is_overdue BOOLEAN NOT NULL DEFAULT FALSE,
    days_overdue INTEGER NOT NULL DEFAULT 0,
    UNIQUE (task_id, user_id, deadline)
);