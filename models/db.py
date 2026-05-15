import sqlite3
import os

from pathlib import Path



from flask import g

from werkzeug.security import generate_password_hash



BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "crm.sqlite3"





def get_db() -> sqlite3.Connection:

    if "db" not in g:

        connection = sqlite3.connect(DB_PATH)
        connection.execute("PRAGMA foreign_keys = ON")

        connection.row_factory = sqlite3.Row

        g.db = connection

    return g.db





def close_db(_error=None) -> None:

    db = g.pop("db", None)

    if db is not None:

        db.close()





def init_db() -> None:

    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")

    cursor = connection.cursor()

    cursor.executescript(

        """

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            email TEXT UNIQUE,

            password TEXT NOT NULL,

            is_active INTEGER NOT NULL DEFAULT 1,

            role TEXT NOT NULL DEFAULT 'sales'

        );



        CREATE TABLE IF NOT EXISTS clients (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            company TEXT,

            phone TEXT,

            location TEXT,

            address TEXT,

            activity_domain TEXT,

            email TEXT,

            notes TEXT,

            pipeline_stage TEXT NOT NULL DEFAULT 'prospect',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP

        );



        CREATE TABLE IF NOT EXISTS appointments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            client_id INTEGER NOT NULL,

            date TEXT NOT NULL,

            time TEXT NOT NULL,

            location TEXT,

            notes TEXT,

            status TEXT NOT NULL DEFAULT 'pending',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE

        );

        CREATE TABLE IF NOT EXISTS appointment_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            user_id INTEGER,
            summary TEXT NOT NULL,
            status_snapshot TEXT,
            date_snapshot TEXT,
            time_snapshot TEXT,
            location_snapshot TEXT,
            notes_snapshot TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );



        CREATE TABLE IF NOT EXISTS followups (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            appointment_id INTEGER NOT NULL,

            title TEXT NOT NULL,

            due_date TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'pending',

            notes TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE

        );

        CREATE TABLE IF NOT EXISTS tracking_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_key TEXT UNIQUE NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_id INTEGER,
            title TEXT NOT NULL,
            context_label TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            priority TEXT NOT NULL DEFAULT 'moyenne',
            notes TEXT,
            is_auto INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );



        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            client_id INTEGER,
            owner_name TEXT,
            assignee_type TEXT NOT NULL DEFAULT 'technicien',
            assignee_name TEXT,
            stage TEXT NOT NULL DEFAULT 'cadrage',
            status TEXT NOT NULL DEFAULT 'en_cours',
            priority TEXT NOT NULL DEFAULT 'moyenne',
            progress INTEGER NOT NULL DEFAULT 0,
            next_action TEXT,
            due_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS project_user_assignments (
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(project_id, user_id),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS project_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER,
            update_type TEXT NOT NULL DEFAULT 'suivi',
            summary TEXT NOT NULL,
            result TEXT,
            next_action TEXT,
            next_action_date TEXT,
            risk_level TEXT NOT NULL DEFAULT 'moyen',
            is_blocked INTEGER NOT NULL DEFAULT 0,
            stage_snapshot TEXT,
            progress_snapshot INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS project_milestones (
            project_id INTEGER NOT NULL,
            milestone_key TEXT NOT NULL,
            is_done INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(project_id, milestone_key),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            partner_type TEXT NOT NULL DEFAULT 'fournisseur',
            contact_name TEXT,
            email TEXT,
            phone TEXT,
            service_category TEXT,
            sla_days INTEGER,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS supplier_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            project_id INTEGER,
            reference_code TEXT,
            title TEXT NOT NULL,
            planned_date TEXT,
            expected_date TEXT,
            delivered_date TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            progress INTEGER NOT NULL DEFAULT 10,
            amount REAL,
            currency TEXT NOT NULL DEFAULT 'USD',
            quality_status TEXT NOT NULL DEFAULT 'ok',
            blocker TEXT,
            next_step TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (

            key TEXT PRIMARY KEY,

            value TEXT NOT NULL

        );



        CREATE TABLE IF NOT EXISTS audit_logs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER,

            username TEXT,

            action TEXT NOT NULL,

            entity_type TEXT NOT NULL,

            entity_id TEXT,

            details TEXT,

            ip_address TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP

        );

        """

    )



    user_columns = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]

    if "role" not in user_columns:

        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'sales'")

    if "email" not in user_columns:

        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")

    if "is_active" not in user_columns:

        cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")



    client_columns = [row[1] for row in cursor.execute("PRAGMA table_info(clients)").fetchall()]

    if "pipeline_stage" not in client_columns:

        cursor.execute(

            "ALTER TABLE clients ADD COLUMN pipeline_stage TEXT NOT NULL DEFAULT 'prospect'"

        )
    if "location" not in client_columns:
        cursor.execute("ALTER TABLE clients ADD COLUMN location TEXT")
    if "address" not in client_columns:
        cursor.execute("ALTER TABLE clients ADD COLUMN address TEXT")
    if "activity_domain" not in client_columns:
        cursor.execute("ALTER TABLE clients ADD COLUMN activity_domain TEXT")

    project_columns = [row[1] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
    if "assignee_name" not in project_columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN assignee_name TEXT")
    if "stage" not in project_columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN stage TEXT NOT NULL DEFAULT 'cadrage'")
    project_update_columns = [row[1] for row in cursor.execute("PRAGMA table_info(project_updates)").fetchall()]
    if "stage_snapshot" not in project_update_columns:
        cursor.execute("ALTER TABLE project_updates ADD COLUMN stage_snapshot TEXT")
    if "progress_snapshot" not in project_update_columns:
        cursor.execute("ALTER TABLE project_updates ADD COLUMN progress_snapshot INTEGER")

    tracking_columns = [row[1] for row in cursor.execute("PRAGMA table_info(tracking_items)").fetchall()]
    if "context_label" not in tracking_columns:
        cursor.execute("ALTER TABLE tracking_items ADD COLUMN context_label TEXT")
    if "is_auto" not in tracking_columns:
        cursor.execute("ALTER TABLE tracking_items ADD COLUMN is_auto INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in tracking_columns:
        cursor.execute("ALTER TABLE tracking_items ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP")

    cursor.execute("SELECT COUNT(*) FROM tracking_items")
    tracking_count = cursor.fetchone()[0]
    if tracking_count == 0:
        cursor.execute(
            """
            INSERT INTO tracking_items(tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto)
            SELECT
              'legacy-followup:' || f.id,
              'followup',
              f.id,
              f.title,
              c.name,
              f.due_date,
              f.status,
              'moyenne',
              f.notes,
              0
            FROM followups f
            JOIN appointments a ON a.id = f.appointment_id
            JOIN clients c ON c.id = a.client_id
            """
        )

    # Cleanup legacy orphan rows created when SQLite FK enforcement was disabled.
    cursor.execute("DELETE FROM appointments WHERE client_id NOT IN (SELECT id FROM clients)")
    cursor.execute(
        "DELETE FROM appointment_updates WHERE appointment_id NOT IN (SELECT id FROM appointments)"
    )
    cursor.execute("DELETE FROM followups WHERE appointment_id NOT IN (SELECT id FROM appointments)")
    cursor.execute("DELETE FROM project_user_assignments WHERE project_id NOT IN (SELECT id FROM projects)")
    cursor.execute("DELETE FROM project_user_assignments WHERE user_id NOT IN (SELECT id FROM users)")
    cursor.execute("DELETE FROM project_updates WHERE project_id NOT IN (SELECT id FROM projects)")
    cursor.execute("DELETE FROM project_milestones WHERE project_id NOT IN (SELECT id FROM projects)")
    cursor.execute("DELETE FROM supplier_deliveries WHERE supplier_id NOT IN (SELECT id FROM suppliers)")



    cursor.execute("SELECT id, password, email FROM users WHERE username = ?", ("admin",))

    admin = cursor.fetchone()

    bootstrap_admin_password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "ChangeMeNow!123")
    if admin is None:

        cursor.execute(

            "INSERT INTO users(username, email, password, role, is_active) VALUES(?, ?, ?, ?, 1)",

            ("admin", "admin@crm.local", generate_password_hash(bootstrap_admin_password), "admin"),

        )

    else:

        current_password = admin[1] or ""

        if not current_password.startswith(("pbkdf2:", "scrypt:")):

            cursor.execute(

                "UPDATE users SET password = ? WHERE id = ?",

                (generate_password_hash(current_password), admin[0]),

            )

        if not admin[2]:

            cursor.execute(

                "UPDATE users SET email = ? WHERE id = ?",

                ("admin@crm.local", admin[0]),

            )



    # Keep bootstrap admin with admin privileges.

    cursor.execute("UPDATE users SET role = 'admin' WHERE username = 'admin'")

    cursor.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_clients_location ON clients(location);
        CREATE INDEX IF NOT EXISTS idx_clients_name_company ON clients(name, company);
        CREATE INDEX IF NOT EXISTS idx_appointments_client_date ON appointments(client_id, date, time);
        CREATE INDEX IF NOT EXISTS idx_appointments_status_date ON appointments(status, date);
        CREATE INDEX IF NOT EXISTS idx_tracking_status_due ON tracking_items(status, due_date);
        CREATE INDEX IF NOT EXISTS idx_tracking_source ON tracking_items(source_type, source_id);
        CREATE INDEX IF NOT EXISTS idx_projects_client_status ON projects(client_id, status);
        CREATE INDEX IF NOT EXISTS idx_projects_due_status ON projects(due_date, status);
        CREATE INDEX IF NOT EXISTS idx_project_updates_project_created ON project_updates(project_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_supplier_deliveries_status_expected ON supplier_deliveries(status, expected_date);
        """
    )



    defaults = {

        "app_name": "Sales Manager",

        "default_theme": "light",

        "items_per_page": "10",

        "monthly_goal": "40",

        "actions_widget_limit": "6",
        "sales_contact_email": "sales@ishango-it.com",
        "report_author_name": "Josué Mbuyu wa Kabinga",
        "report_author_email": "josue.mbuyu@ishango-it.com",
        "report_author_title": "Technical sales",

    }

    for key, value in defaults.items():

        cursor.execute(

            "INSERT OR IGNORE INTO app_settings(key, value) VALUES(?, ?)",

            (key, value),

        )



    connection.commit()

    connection.close()

