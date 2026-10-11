import os
import sqlite3

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'database')
DB_PATH = os.path.join(DB_DIR, 'timetable.db')
def get_database_url() -> str:
    """Read PostgreSQL URL from environment or Streamlit Secrets without exposing it in source control."""
    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        return value
    try:
        import streamlit as st
        direct = st.secrets.get("DATABASE_URL", "")
        if direct:
            return str(direct).strip()
        database_section = st.secrets.get("database", {})
        if isinstance(database_section, dict):
            return str(database_section.get("url", "")).strip()
    except Exception:
        pass
    return ""


def using_postgres() -> bool:
    return bool(get_database_url())


def get_connection():
    """Return a database connection. PostgreSQL is used when DATABASE_URL is set; otherwise SQLite is used locally."""
    if using_postgres():
        if psycopg is None:
            raise RuntimeError("PostgreSQL is configured but psycopg is not installed. Run: pip install -r requirements.txt")
        return _PGConnectionWrapper(psycopg.connect(get_database_url(), row_factory=dict_row))
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _adapt_sql(sql: str) -> str:
    """Adapt the small set of SQLite-specific syntax used by this module for PostgreSQL."""
    if not using_postgres():
        return sql
    import re
    sql = re.sub(r"\?", "%s", sql)
    sql = re.sub(r"\bINTEGER PRIMARY KEY AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql, flags=re.I)
    sql = re.sub(r"\bINSERT OR IGNORE INTO\b", "INSERT INTO", sql, flags=re.I)
    # All remaining OR IGNORE statements in this module are safe to treat as DO NOTHING.
    if re.match(r"\s*INSERT INTO", sql, flags=re.I) and "ON CONFLICT" not in sql.upper():
        # Only add DO NOTHING to statements that originated from INSERT OR IGNORE.
        # Marker is inserted by the specific SQL strings below where needed.
        pass
    return sql


class _PGCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=None):
        # Avoid PostgreSQL BIGSERIAL sequence collisions when a table already exists.
        import re
        if using_postgres():
            create_match = re.match(
                r"\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                sql,
                flags=re.I,
            )
            if create_match:
                table_name = create_match.group(1)
                check_cursor = self._cursor.connection.cursor()
                try:
                    check_cursor.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
                    if check_cursor.fetchone()[0] is not None:
                        return self
                finally:
                    check_cursor.close()
        adapted = _adapt_sql(sql)
        # PostgreSQL has no sqlite-style lastrowid. For INSERTs, request the generated id.
        import re
        is_insert = bool(re.match(r"\s*INSERT\s+INTO", adapted, flags=re.I))
        if is_insert and re.search(r"\bid\b", adapted, flags=re.I) and "RETURNING" not in adapted.upper():
            adapted = adapted.rstrip().rstrip(';') + " RETURNING id;"
        self._cursor.execute(adapted, params or ())
        self.lastrowid = None
        if is_insert and "RETURNING id" in adapted.upper():
            row = self._cursor.fetchone()
            if row:
                self.lastrowid = row["id"] if isinstance(row, dict) else row[0]
        return self

    def executemany(self, sql, seq_of_params):
        self._cursor.executemany(_adapt_sql(sql), seq_of_params)
        self.lastrowid = None
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PGConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _PGCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._conn.__exit__(exc_type, exc, tb)

    def __getattr__(self, name):
        return getattr(self._conn, name)

def init_db():
    """Creates tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Admins Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Admin Settings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER UNIQUE NOT NULL,
                college_name TEXT DEFAULT '',
                academic_year TEXT DEFAULT '2026-27',
                department TEXT DEFAULT 'Department of AIML',
                branch TEXT DEFAULT 'AIML',
                default_solver_time_limit INTEGER DEFAULT 60,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Classes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                academic_year TEXT,
                year TEXT,
                semester TEXT,
                branch TEXT,
                section TEXT,
                student_strength INTEGER NOT NULL DEFAULT 60,
                class_teacher TEXT,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Teachers Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                max_periods_per_day INTEGER DEFAULT 6,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Subjects Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL, -- 'Theory' or 'Lab'
                default_periods_per_week INTEGER DEFAULT 3,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                UNIQUE(admin_id, code)
            );
        """)

        # Class Subject Requirements Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS class_subject_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                periods_per_week INTEGER NOT NULL DEFAULT 3,
                consecutive_periods INTEGER DEFAULT 1,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
                UNIQUE(admin_id, class_id, subject_id)
            );
        """)

        # Teacher Subject Assignments Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teacher_subject_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                role TEXT DEFAULT 'PRIMARY', -- 'PRIMARY' or 'CO_TEACHER'
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
                FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
            );
        """)

        # Teacher Availability Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teacher_availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                day_name TEXT NOT NULL,
                period_number INTEGER NOT NULL,
                is_available INTEGER DEFAULT 1,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
                UNIQUE(admin_id, teacher_id, day_name, period_number)
            );
        """)

        # Rooms Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                room_type TEXT DEFAULT 'Classroom',
                capacity INTEGER NOT NULL DEFAULT 60,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Labs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS labs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                lab_type TEXT DEFAULT 'Laboratory',
                capacity INTEGER NOT NULL DEFAULT 40,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Lab Requirements Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lab_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                lab_id INTEGER NOT NULL,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
                FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE,
                UNIQUE(admin_id, subject_id, lab_id)
            );
        """)

        # Working Days Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS working_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                day_name TEXT NOT NULL,
                day_order INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Periods Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS periods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                period_number INTEGER NOT NULL,
                period_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                UNIQUE(admin_id, period_number)
            );
        """)

        # Breaks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS breaks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                break_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                after_period INTEGER NOT NULL,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Hard Constraints Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hard_constraints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                is_enabled INTEGER DEFAULT 1,
                is_mandatory INTEGER DEFAULT 1,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Soft Constraints Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS soft_constraints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                is_enabled INTEGER DEFAULT 1,
                weight INTEGER DEFAULT 5,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Timetable Runs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetable_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                solver_status TEXT NOT NULL,
                objective_value REAL DEFAULT 0.0,
                quality_score REAL DEFAULT 0.0,
                status TEXT NOT NULL,
                message TEXT,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
            );
        """)

        # Timetable Entries Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetable_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                day_name TEXT NOT NULL,
                period_number INTEGER NOT NULL,
                resource_type TEXT NOT NULL, -- 'ROOM' or 'LAB'
                resource_id INTEGER NOT NULL,
                FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                FOREIGN KEY (run_id) REFERENCES timetable_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );
        """)

        conn.commit()

# --- ADMIN DEFAULTS INITIALIZATION ---
def initialize_admin_defaults(admin_id: int):
    """Populates default settings, working days, periods, breaks, and constraint rules for a new admin."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Settings
        cursor.execute("""
            INSERT INTO admin_settings (admin_id, college_name, academic_year, department, branch, default_solver_time_limit)
            VALUES (?, '', '', '', '', 60) ON CONFLICT(admin_id) DO NOTHING;
        """, (admin_id,))

        # Working Days
        days = [
            ("Monday", 1), ("Tuesday", 2), ("Wednesday", 3),
            ("Thursday", 4), ("Friday", 5), ("Saturday", 6)
        ]
        for day_name, order in days:
            cursor.execute("""
                INSERT INTO working_days (admin_id, day_name, day_order, is_active)
                VALUES (?, ?, ?, 1) ON CONFLICT DO NOTHING;
            """, (admin_id, day_name, order))

        # Periods
        period_list = [
            (1, "P1", "09:00 AM", "09:55 AM"),
            (2, "P2", "09:55 AM", "10:50 AM"),
            (3, "P3", "10:50 AM", "11:45 AM"),
            (4, "P4", "11:45 AM", "12:40 PM"),
            (5, "P5", "01:30 PM", "02:25 PM"),
            (6, "P6", "02:25 PM", "03:20 PM")
        ]
        for pnum, pname, start_t, end_t in period_list:
            cursor.execute("""
                INSERT INTO periods (admin_id, period_number, period_name, start_time, end_time, is_active)
                VALUES (?, ?, ?, ?, ?, 1) ON CONFLICT DO NOTHING;
            """, (admin_id, pnum, pname, start_t, end_t))

        # Breaks (Lunch break after P4)
        cursor.execute("""
            INSERT INTO breaks (admin_id, break_name, start_time, end_time, after_period)
            VALUES (?, 'Lunch Break', '12:40 PM', '01:30 PM', 4) ON CONFLICT DO NOTHING;
        """, (admin_id,))

        # Default Hard Constraints
        hard_rules = [
            ("HC1", "Single Subject Per Class Slot", "One class cannot be scheduled for multiple subjects simultaneously.", 1, 1),
            ("HC2", "Teacher Conflict Prevention", "A teacher (or co-teacher) cannot teach multiple classes at the same time.", 1, 1),
            ("HC3", "Room & Lab Conflict Prevention", "A room or laboratory cannot host multiple classes simultaneously.", 1, 1),
            ("HC4", "Required Weekly Periods", "All required subject periods for a class must be scheduled exactly.", 1, 1),
            ("HC5", "Teacher Availability Respect", "Teachers must not be assigned to slots where they are marked unavailable.", 1, 1),
            ("HC6", "Resource Capacity Constraint", "Room/Lab capacity must be greater than or equal to class student strength.", 1, 1),
            ("HC7", "Lab Subject Matching", "Lab subjects must be conducted in their designated laboratories.", 1, 1),
            ("HC8", "Break / Lunch Non-Overlap", "No classes can be scheduled during designated lunch or break slots.", 1, 1),
            ("HC9", "Consecutive Lab Periods", "Lab sessions must be scheduled as consecutive period blocks.", 1, 1),
            ("HC10", "Max Teacher Daily Periods", "Teacher daily period limit must not be exceeded.", 1, 0)
        ]
        for code, name, desc, is_en, is_mand in hard_rules:
            cursor.execute("""
                INSERT INTO hard_constraints (admin_id, code, name, description, is_enabled, is_mandatory)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING;
            """, (admin_id, code, name, desc, is_en, is_mand))

        # Default Soft Constraints
        soft_rules = [
            ("SC1", "Subject Day Distribution", "Spread sessions of each subject evenly across working days.", 1, 8),
            ("SC2", "Avoid Same-Day Subject Repetition", "Avoid scheduling multiple sessions of the same theory subject on one day.", 1, 7),
            ("SC3", "Balance Teacher Workload", "Distribute teaching load evenly for faculty across working days.", 1, 6),
            ("SC4", "Reduce Class Idle Gaps", "Minimize free periods between scheduled classes for students.", 1, 5),
            ("SC5", "Optimal Room Capacity Match", "Prefer room capacities closest to class strength to maximize utilization.", 1, 4),
            ("SC6", "Spread Lab Sessions", "Distribute practical lab sessions across different days of the week.", 1, 6)
        ]
        for code, name, desc, is_en, wt in soft_rules:
            cursor.execute("""
                INSERT INTO soft_constraints (admin_id, code, name, description, is_enabled, weight)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING;
            """, (admin_id, code, name, desc, is_en, wt))

        conn.commit()

# --- ADMIN CRUD ---
def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE username = ?;", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_admin(username: str, password_hash: str, salt: str) -> Optional[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if using_postgres():
            cursor.execute("""
                INSERT INTO admins (username, password_hash, salt)
                VALUES (?, ?, ?) RETURNING id;
            """, (username, password_hash, salt))
            row = cursor.fetchone()
            conn.commit()
            return (row["id"] if isinstance(row, dict) else row[0]) if row else None
        cursor.execute("""
            INSERT INTO admins (username, password_hash, salt)
            VALUES (?, ?, ?);
        """, (username, password_hash, salt))
        conn.commit()
        return cursor.lastrowid

def get_admin_settings(admin_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admin_settings WHERE admin_id = ?;", (admin_id,))
        row = cursor.fetchone()
        if not row:
            initialize_admin_defaults(admin_id)
            cursor.execute("SELECT * FROM admin_settings WHERE admin_id = ?;", (admin_id,))
            row = cursor.fetchone()
        return dict(row)

def update_admin_settings(admin_id: int, college_name: str, academic_year: str, department: str, branch: str, time_limit: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE admin_settings
            SET college_name = ?, academic_year = ?, department = ?, branch = ?, default_solver_time_limit = ?
            WHERE admin_id = ?;
        """, (college_name, academic_year, department, branch, time_limit, admin_id))
        conn.commit()

# --- CLASSES CRUD ---
def get_classes(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE admin_id = ? ORDER BY name ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_class_by_id(admin_id: int, class_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE admin_id = ? AND id = ?;", (admin_id, class_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_class(admin_id: int, name: str, academic_year: str, year: str, semester: str, branch: str, section: str, student_strength: int, class_teacher: str) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO classes (admin_id, name, academic_year, year, semester, branch, section, student_strength, class_teacher)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (admin_id, name, academic_year, year, semester, branch, section, student_strength, class_teacher))
        conn.commit()
        return cursor.lastrowid

def update_class(admin_id: int, class_id: int, name: str, academic_year: str, year: str, semester: str, branch: str, section: str, student_strength: int, class_teacher: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE classes
            SET name = ?, academic_year = ?, year = ?, semester = ?, branch = ?, section = ?, student_strength = ?, class_teacher = ?
            WHERE admin_id = ? AND id = ?;
        """, (name, academic_year, year, semester, branch, section, student_strength, class_teacher, admin_id, class_id))
        conn.commit()

def delete_class(admin_id: int, class_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM classes WHERE admin_id = ? AND id = ?;", (admin_id, class_id))
        conn.commit()

# --- TEACHERS CRUD ---
def get_teachers(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teachers WHERE admin_id = ? ORDER BY name ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_teacher_by_id(admin_id: int, teacher_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teachers WHERE admin_id = ? AND id = ?;", (admin_id, teacher_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_teacher(admin_id: int, name: str, email: str, max_periods_per_day: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teachers (admin_id, name, email, max_periods_per_day)
            VALUES (?, ?, ?, ?);
        """, (admin_id, name, email, max_periods_per_day))
        conn.commit()
        return cursor.lastrowid

def update_teacher(admin_id: int, teacher_id: int, name: str, email: str, max_periods_per_day: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teachers
            SET name = ?, email = ?, max_periods_per_day = ?
            WHERE admin_id = ? AND id = ?;
        """, (name, email, max_periods_per_day, admin_id, teacher_id))
        conn.commit()

def delete_teacher(admin_id: int, teacher_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM teachers WHERE admin_id = ? AND id = ?;", (admin_id, teacher_id))
        conn.commit()

# --- SUBJECTS CRUD ---
def get_subjects(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subjects WHERE admin_id = ? ORDER BY code ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_subject_by_id(admin_id: int, subject_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subjects WHERE admin_id = ? AND id = ?;", (admin_id, subject_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_subject(admin_id: int, code: str, name: str, subject_type: str, default_periods_per_week: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subjects (admin_id, code, name, type, default_periods_per_week)
            VALUES (?, ?, ?, ?, ?);
        """, (admin_id, code, name, subject_type, default_periods_per_week))
        conn.commit()
        return cursor.lastrowid

def update_subject(admin_id: int, subject_id: int, code: str, name: str, subject_type: str, default_periods_per_week: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subjects
            SET code = ?, name = ?, type = ?, default_periods_per_week = ?
            WHERE admin_id = ? AND id = ?;
        """, (code, name, subject_type, default_periods_per_week, admin_id, subject_id))
        conn.commit()

def delete_subject(admin_id: int, subject_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subjects WHERE admin_id = ? AND id = ?;", (admin_id, subject_id))
        conn.commit()

# --- CLASS SUBJECT REQUIREMENTS CRUD ---
def get_class_subject_requirements(admin_id: int, class_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if class_id:
            cursor.execute("""
                SELECT r.*, c.name as class_name, s.name as subject_name, s.code as subject_code, s.type as subject_type
                FROM class_subject_requirements r
                JOIN classes c ON r.class_id = c.id
                JOIN subjects s ON r.subject_id = s.id
                WHERE r.admin_id = ? AND r.class_id = ?
                ORDER BY c.name, s.code;
            """, (admin_id, class_id))
        else:
            cursor.execute("""
                SELECT r.*, c.name as class_name, s.name as subject_name, s.code as subject_code, s.type as subject_type
                FROM class_subject_requirements r
                JOIN classes c ON r.class_id = c.id
                JOIN subjects s ON r.subject_id = s.id
                WHERE r.admin_id = ?
                ORDER BY c.name, s.code;
            """, (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_class_subject_requirement(admin_id: int, class_id: int, subject_id: int, periods_per_week: int, consecutive_periods: int = 1) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO class_subject_requirements (admin_id, class_id, subject_id, periods_per_week, consecutive_periods)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(admin_id, class_id, subject_id) DO UPDATE SET periods_per_week=EXCLUDED.periods_per_week, consecutive_periods=EXCLUDED.consecutive_periods;
        """, (admin_id, class_id, subject_id, periods_per_week, consecutive_periods))
        conn.commit()
        return cursor.lastrowid

def delete_class_subject_requirement(admin_id: int, req_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM class_subject_requirements WHERE admin_id = ? AND id = ?;", (admin_id, req_id))
        conn.commit()

# --- FACULTY ASSIGNMENTS CRUD ---
def get_teacher_assignments(admin_id: int, class_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if class_id:
            cursor.execute("""
                SELECT a.*, c.name as class_name, s.name as subject_name, s.code as subject_code, s.type as subject_type, t.name as teacher_name
                FROM teacher_subject_assignments a
                JOIN classes c ON a.class_id = c.id
                JOIN subjects s ON a.subject_id = s.id
                JOIN teachers t ON a.teacher_id = t.id
                WHERE a.admin_id = ? AND a.class_id = ?
                ORDER BY c.name, s.code, a.role;
            """, (admin_id, class_id))
        else:
            cursor.execute("""
                SELECT a.*, c.name as class_name, s.name as subject_name, s.code as subject_code, s.type as subject_type, t.name as teacher_name
                FROM teacher_subject_assignments a
                JOIN classes c ON a.class_id = c.id
                JOIN subjects s ON a.subject_id = s.id
                JOIN teachers t ON a.teacher_id = t.id
                WHERE a.admin_id = ?
                ORDER BY c.name, s.code, a.role;
            """, (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_teacher_assignment(admin_id: int, class_id: int, subject_id: int, teacher_id: int, role: str = 'PRIMARY') -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teacher_subject_assignments (admin_id, class_id, subject_id, teacher_id, role)
            VALUES (?, ?, ?, ?, ?);
        """, (admin_id, class_id, subject_id, teacher_id, role))
        conn.commit()
        return cursor.lastrowid

def delete_teacher_assignment(admin_id: int, assignment_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM teacher_subject_assignments WHERE admin_id = ? AND id = ?;", (admin_id, assignment_id))
        conn.commit()

def clear_teacher_assignments(admin_id: int, class_id: int, subject_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM teacher_subject_assignments WHERE admin_id = ? AND class_id = ? AND subject_id = ?;", (admin_id, class_id, subject_id))
        conn.commit()

# --- TEACHER AVAILABILITY ---
def get_teacher_availability(admin_id: int, teacher_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if teacher_id:
            cursor.execute("""
                SELECT * FROM teacher_availability WHERE admin_id = ? AND teacher_id = ?;
            """, (admin_id, teacher_id))
        else:
            cursor.execute("""
                SELECT * FROM teacher_availability WHERE admin_id = ?;
            """, (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def set_teacher_availability(admin_id: int, teacher_id: int, day_name: str, period_number: int, is_available: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teacher_availability (admin_id, teacher_id, day_name, period_number, is_available)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(admin_id, teacher_id, day_name, period_number) DO UPDATE SET is_available=EXCLUDED.is_available;
        """, (admin_id, teacher_id, day_name, period_number, is_available))
        conn.commit()

# --- ROOMS & LABS CRUD ---
def get_rooms(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE admin_id = ? ORDER BY name ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_room(admin_id: int, name: str, room_type: str, capacity: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rooms (admin_id, name, room_type, capacity)
            VALUES (?, ?, ?, ?);
        """, (admin_id, name, room_type, capacity))
        conn.commit()
        return cursor.lastrowid

def update_room(admin_id: int, room_id: int, name: str, room_type: str, capacity: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE rooms SET name = ?, room_type = ?, capacity = ? WHERE admin_id = ? AND id = ?;
        """, (name, room_type, capacity, admin_id, room_id))
        conn.commit()

def delete_room(admin_id: int, room_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rooms WHERE admin_id = ? AND id = ?;", (admin_id, room_id))
        conn.commit()

def get_labs(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM labs WHERE admin_id = ? ORDER BY name ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_lab(admin_id: int, name: str, lab_type: str, capacity: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO labs (admin_id, name, lab_type, capacity)
            VALUES (?, ?, ?, ?);
        """, (admin_id, name, lab_type, capacity))
        conn.commit()
        return cursor.lastrowid

def update_lab(admin_id: int, lab_id: int, name: str, lab_type: str, capacity: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE labs SET name = ?, lab_type = ?, capacity = ? WHERE admin_id = ? AND id = ?;
        """, (name, lab_type, capacity, admin_id, lab_id))
        conn.commit()

def delete_lab(admin_id: int, lab_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM labs WHERE admin_id = ? AND id = ?;", (admin_id, lab_id))
        conn.commit()

def get_lab_requirements(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lr.*, s.name as subject_name, s.code as subject_code, l.name as lab_name
            FROM lab_requirements lr
            JOIN subjects s ON lr.subject_id = s.id
            JOIN labs l ON lr.lab_id = l.id
            WHERE lr.admin_id = ?;
        """, (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_lab_requirement(admin_id: int, subject_id: int, lab_id: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO lab_requirements (admin_id, subject_id, lab_id)
            VALUES (?, ?, ?)
            ON CONFLICT(admin_id, subject_id, lab_id) DO NOTHING;
        """, (admin_id, subject_id, lab_id))
        conn.commit()
        return cursor.lastrowid

def delete_lab_requirement(admin_id: int, req_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM lab_requirements WHERE admin_id = ? AND id = ?;", (admin_id, req_id))
        conn.commit()

# --- SCHEDULE SETUP (DAYS, PERIODS, BREAKS) ---
def get_working_days(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM working_days WHERE admin_id = ? ORDER BY day_order ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_working_day(admin_id: int, day_name: str, day_order: int, is_active: int = 1) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO working_days (admin_id, day_name, day_order, is_active)
            VALUES (?, ?, ?, ?);
        """, (admin_id, day_name, day_order, is_active))
        conn.commit()
        return cursor.lastrowid

def update_working_day(admin_id: int, day_id: int, day_name: str, day_order: int, is_active: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE working_days SET day_name = ?, day_order = ?, is_active = ? WHERE admin_id = ? AND id = ?;
        """, (day_name, day_order, is_active, admin_id, day_id))
        conn.commit()

def delete_working_day(admin_id: int, day_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM working_days WHERE admin_id = ? AND id = ?;", (admin_id, day_id))
        conn.commit()

def get_periods(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM periods WHERE admin_id = ? ORDER BY period_number ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_period(admin_id: int, period_number: int, period_name: str, start_time: str, end_time: str, is_active: int = 1) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO periods (admin_id, period_number, period_name, start_time, end_time, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(admin_id, period_number) DO UPDATE SET period_name=EXCLUDED.period_name, start_time=EXCLUDED.start_time, end_time=EXCLUDED.end_time, is_active=EXCLUDED.is_active;
        """, (admin_id, period_number, period_name, start_time, end_time, is_active))
        conn.commit()
        return cursor.lastrowid

def update_period(admin_id: int, period_id: int, period_number: int, period_name: str, start_time: str, end_time: str, is_active: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE periods SET period_number = ?, period_name = ?, start_time = ?, end_time = ?, is_active = ? WHERE admin_id = ? AND id = ?;
        """, (period_number, period_name, start_time, end_time, is_active, admin_id, period_id))
        conn.commit()

def delete_period(admin_id: int, period_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM periods WHERE admin_id = ? AND id = ?;", (admin_id, period_id))
        conn.commit()

def get_breaks(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM breaks WHERE admin_id = ? ORDER BY after_period ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def add_break(admin_id: int, break_name: str, start_time: str, end_time: str, after_period: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO breaks (admin_id, break_name, start_time, end_time, after_period)
            VALUES (?, ?, ?, ?, ?);
        """, (admin_id, break_name, start_time, end_time, after_period))
        conn.commit()
        return cursor.lastrowid

def delete_break(admin_id: int, break_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM breaks WHERE admin_id = ? AND id = ?;", (admin_id, break_id))
        conn.commit()

# --- CONSTRAINTS ---
def get_hard_constraints(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hard_constraints WHERE admin_id = ? ORDER BY code ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def update_hard_constraint(admin_id: int, constraint_id: int, is_enabled: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE hard_constraints SET is_enabled = ? WHERE admin_id = ? AND id = ?;", (is_enabled, admin_id, constraint_id))
        conn.commit()

def get_soft_constraints(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM soft_constraints WHERE admin_id = ? ORDER BY code ASC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def update_soft_constraint(admin_id: int, constraint_id: int, is_enabled: int, weight: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE soft_constraints SET is_enabled = ?, weight = ? WHERE admin_id = ? AND id = ?;", (is_enabled, weight, admin_id, constraint_id))
        conn.commit()

# --- TIMETABLE RUNS & ENTRIES ---
def save_timetable_run(
    admin_id: int,
    solver_status: str,
    objective_value: float,
    quality_score: float,
    status: str,
    message: str,
    entries: List[Dict[str, Any]]
) -> int:
    """Saves a timetable generation run and all generated entries."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO timetable_runs (admin_id, solver_status, objective_value, quality_score, status, message)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (admin_id, solver_status, objective_value, quality_score, status, message))
        run_id = cursor.lastrowid

        for entry in entries:
            cursor.execute("""
                INSERT INTO timetable_entries (admin_id, run_id, class_id, subject_id, day_name, period_number, resource_type, resource_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                admin_id,
                run_id,
                entry['class_id'],
                entry['subject_id'],
                entry['day_name'],
                entry['period_number'],
                entry['resource_type'],
                entry['resource_id']
            ))

        conn.commit()
        return run_id

def get_timetable_runs(admin_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timetable_runs WHERE admin_id = ? ORDER BY run_timestamp DESC;", (admin_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_latest_timetable_run(admin_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timetable_runs WHERE admin_id = ? AND status = 'SUCCESS' ORDER BY run_timestamp DESC LIMIT 1;", (admin_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_timetable_entries_by_run(admin_id: int, run_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.*, c.name as class_name, s.name as subject_name, s.code as subject_code, s.type as subject_type
            FROM timetable_entries e
            JOIN classes c ON e.class_id = c.id
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.admin_id = ? AND e.run_id = ?
            ORDER BY e.day_name, e.period_number;
        """, (admin_id, run_id))
        return [dict(r) for r in cursor.fetchall()]

def delete_timetable_run(admin_id: int, run_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM timetable_runs WHERE admin_id = ? AND id = ?;", (admin_id, run_id))
        conn.commit()
