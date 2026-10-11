# Optimized Time Table with AI

**Optimized Time Table with AI** is a complete, production-quality college timetable optimization system powered by **Google OR-Tools CP-SAT constraint satisfaction engine**, **Python**, and **Streamlit**.

It provides an end-to-end web application allowing authenticated administrators to configure academic data, faculty availability, classrooms/laboratories, and institutional hard/soft constraints to generate mathematical optimal, conflict-free college timetables.

---

## 🌟 Key Features

- **Multi-Admin Data Isolation**: Secure admin authentication (PBKDF2-HMAC-SHA256 password hashing with cryptographically random salt). Every database entity is strictly scoped to `admin_id`.
- **Complete Academic CRUD**: Manage Classes/Sections, Teachers, Subjects, Class-Subject Requirements, and explicit Faculty Assignments (Primary + Co-Teachers).
- **Resource Management**: Configure Classrooms, Laboratories, and map specific Lab Subjects to target labs with capacity validation (`capacity >= student_strength`).
- **Schedule & Availability**: Custom Working Days (Mon-Sat), Period Timings (P1-P6), Lunch/Break slots, and interactive Teacher Availability matrix.
- **Mathematical Optimization Engine**: Built on Google OR-Tools CP-SAT solver. Maximizes soft constraint satisfaction while satisfying 100% of hard constraints.
- **Independent Solution Validator**: Post-generation validation engine that verifies class, teacher, room, lab, and consecutive period constraints independently of CP-SAT before publishing results.
- **Interactive Timetable Views**: Class-wise, Teacher-wise, and Room/Lab-wise timetables complete with Course Summary cards below.
- **Quality Analysis**: Realistic, non-hardcoded quality scoring (0-100) assessing subject distribution, teacher workload balance, student idle gaps, resource utilization, and soft constraint satisfaction.
- **Production Exports**:
  - **Excel**: Multi-tab formatted `.xlsx` workbooks generated with `openpyxl`.
  - **PDF**: Styled landscape `.pdf` documents generated with `ReportLab`.
- **Demo Data Loader**: One-click demo data loading for instant evaluation (using sample Geethanjali College AIML datasets).

---

## 🛠️ Technology Stack

- **Python**: 3.12+
- **Frontend / UI**: Streamlit
- **Optimization Engine**: Google OR-Tools CP-SAT (`ortools.sat.python.cp_model`)
- **Database**: SQLite for local development; PostgreSQL for production when `DATABASE_URL` is configured (environment variable or Streamlit Secrets).
- **Data Processing**: Pandas
- **Exports**: openpyxl (Excel), ReportLab (PDF)
- **Password Security**: `hashlib.pbkdf2_hmac` with `secrets` salt

---

## 📐 System Workflow

```
ADMIN LOGIN / REGISTER
          ↓
   ADMIN DASHBOARD
          ↓
 ACADEMIC DATA ENTRY
   (Classes, Teachers, Subjects, Faculty Assignments, Availability)
          ↓
  RESOURCE & SCHEDULE
   (Rooms, Labs, Days, Periods, Breaks)
          ↓
CONSTRAINTS CONFIGURATION
          ↓
  PRE-SOLVE VALIDATION
          ↓
  GOOGLE OR-TOOLS CP-SAT
          ↓
INDEPENDENT SOLUTION VALIDATION
          ↓
   SAVE TO SQLITE DB
          ↓
DISPLAY TIMETABLE VIEWS & QUALITY ANALYSIS
          ↓
 EXCEL & PDF EXPORT
```

---

## 💻 Installation & Running Locally

1. **Clone or Navigate to Project Directory**:
   ```bash
   cd c:\Users\thriv\OneDrive\Desktop\AIP
   ```

2. **Install Required Packages**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch Application**:
   ```bash
   python -m streamlit run app.py
   ```

4. Open your browser at `http://localhost:8501`.

---

## ☁️ Deployment Notes & Database Architecture

- **Local / Single-User Demo**: SQLite (`database/timetable.db`) is initialized automatically on first launch and provides persistent storage.
- **Production Cloud Deployment**: Cloud container environments (such as Streamlit Community Cloud or Heroku) use ephemeral file systems where local SQLite database files do not persist across server restarts. For multi-tenant production deployments, the database layer (`database.py`) is structured so connections can be pointed to a hosted PostgreSQL instance (e.g. via `psycopg2` or `SQLAlchemy`).

---

## 🔒 Security & Data Integrity

- Passwords are never stored as plain text.
- Parameterized SQL queries prevent SQL injection attacks.
- Foreign keys with `ON DELETE CASCADE` prevent dangling references.
- Deletion safety confirmation and conflict prevention built in.

---

## 📄 License

Developed for AI-Based Timetable Optimization Systems. All rights reserved.


## Database configuration

### Local development
If `DATABASE_URL` is not configured, the application uses the local SQLite database at `database/timetable.db`. The file is intentionally ignored by Git.

### Streamlit Cloud / production
For production, use a hosted PostgreSQL database. Set the connection URL as a secret; do not commit credentials. Streamlit Cloud can use either:

```toml
[database]
url = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

or a `DATABASE_URL` secret/environment variable. The application detects it and uses PostgreSQL for all database operations.

Required production dependency: `psycopg[binary]`.

### Deployment outline
1. Create a hosted PostgreSQL database.
2. Push this project to GitHub without `database/*.db`, `.env`, or secrets.
3. Deploy the repository on Streamlit Community Cloud with `app.py` as the entry point.
4. Add the PostgreSQL URL to Streamlit Cloud Secrets.
5. Start the app. `init_db()` creates the schema in the PostgreSQL database automatically.
6. Register administrators. Each administrator's data is scoped by `admin_id`.

Never place a real PostgreSQL password in Python source code or GitHub.
