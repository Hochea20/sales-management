import sqlite3
import uuid


def main() -> None:
    db = sqlite3.connect("crm.sqlite3")
    c = db.cursor()

    def one(sql: str) -> int:
        return int(c.execute(sql).fetchone()[0])

    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print("tables", tables)
    print("db_file", "crm.sqlite3")

    print("clients_total", one("SELECT COUNT(1) FROM clients"))
    print("appointments_total", one("SELECT COUNT(1) FROM appointments"))
    print("followups_total", one("SELECT COUNT(1) FROM followups"))
    print("projects_total", one("SELECT COUNT(1) FROM projects"))
    print("suppliers_total", one("SELECT COUNT(1) FROM suppliers"))
    print("supplier_deliveries_total", one("SELECT COUNT(1) FROM supplier_deliveries"))

    if "tracking_items" in tables:
        cols = c.execute("PRAGMA table_info(tracking_items)").fetchall()
        print("tracking_items_columns", [col[1] for col in cols])
    else:
        print("tracking_items_columns", "MISSING_TABLE")
    print(
        "projects_with_next_action_7d",
        one(
            """
            SELECT COUNT(1)
            FROM projects
            WHERE next_action IS NOT NULL
              AND next_action != ''
              AND due_date IS NOT NULL
              AND due_date != ''
              AND date(due_date) BETWEEN date('now') AND date('now', '+7 day')
            """
        ),
    )
    print(
        "tracking_project_action",
        one("SELECT COUNT(1) FROM tracking_items WHERE tracking_key LIKE 'auto:project-action:%'"),
    )
    print("tracking_total", one("SELECT COUNT(1) FROM tracking_items"))
    print("tracking_pending", one("SELECT COUNT(1) FROM tracking_items WHERE status='pending'"))

    if "tracking_items" in tables:
        key = f"diag:{uuid.uuid4().hex}"
        c.execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES(?, 'manual', NULL, 'Diag suivi', '', NULL, 'pending', 'moyenne', 'test', 0, CURRENT_TIMESTAMP)
            """,
            (key,),
        )
        db.commit()
        print("diag_insert_ok", key)
        print("tracking_total_after_insert", one("SELECT COUNT(1) FROM tracking_items"))

    rows = c.execute(
        """
        SELECT tracking_key, source_type, context_label, due_date, status, notes
        FROM tracking_items
        ORDER BY updated_at DESC
        LIMIT 10
        """
    ).fetchall()
    print("tracking_samples", rows)

    db.close()


if __name__ == "__main__":
    main()

