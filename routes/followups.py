from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.repositories import execute, query_all, query_one
from routes.audit import log_action
from routes.utils import permission_required

followups_bp = Blueprint("followups", __name__, url_prefix="/followups")


def _sync_auto_tracking_items() -> None:
    active_keys = []

    appointment_items = query_all(
        """
        SELECT
          a.id,
          a.date,
          a.time,
          a.location,
          c.name AS client_name
        FROM appointments a
        JOIN clients c ON c.id = a.client_id
        WHERE a.status = 'pending'
          AND datetime(a.date || ' ' || a.time) < datetime('now', 'localtime')
        """
    )
    for item in appointment_items:
        key = f"auto:appointment:{item['id']}"
        active_keys.append(key)
        execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES (?, 'appointment', ?, ?, ?, ?, 'pending', 'haute', ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(tracking_key) DO UPDATE SET
              title = excluded.title,
              context_label = excluded.context_label,
              due_date = excluded.due_date,
              status = 'pending',
              priority = excluded.priority,
              notes = excluded.notes,
              is_auto = 1,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                item["id"],
                "Rendez-vous en retard",
                item["client_name"],
                item["date"],
                f"Heure prévue: {item['time']}" + (f" - {item['location']}" if item["location"] else ""),
            ),
        )

    project_items = query_all(
        """
        SELECT id, title, due_date, stage, progress
        FROM projects
        WHERE status IN ('en_cours', 'en_attente')
          AND due_date IS NOT NULL
          AND due_date <> ''
          AND date(due_date) < date('now')
          AND progress < 100
        """
    )
    for item in project_items:
        key = f"auto:project-late:{item['id']}"
        active_keys.append(key)
        execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES (?, 'project', ?, ?, ?, ?, 'pending', 'critique', ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(tracking_key) DO UPDATE SET
              title = excluded.title,
              context_label = excluded.context_label,
              due_date = excluded.due_date,
              status = 'pending',
              priority = excluded.priority,
              notes = excluded.notes,
              is_auto = 1,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                item["id"],
                "Projet en retard",
                item["title"],
                item["due_date"],
                f"Étape: {(item['stage'] or '-').replace('_', ' ').title()} | Progression: {item['progress'] or 0}%",
            ),
        )

    # Always surface latest project stage/progress updates (even without an action date),
    # so that progress changes entered in the journal appear in the centralized "Suivis".
    latest_project_updates = query_all(
        """
        SELECT
          pu.project_id,
          p.title AS project_title,
          p.due_date,
          p.stage,
          p.progress,
          pu.summary,
          pu.next_action,
          pu.next_action_date,
          pu.is_blocked,
          pu.created_at
        FROM project_updates pu
        JOIN projects p ON p.id = pu.project_id
        WHERE pu.id IN (
          SELECT MAX(id)
          FROM project_updates
          GROUP BY project_id
        )
          AND p.progress < 100
        ORDER BY pu.created_at DESC, pu.id DESC
        LIMIT 50
        """
    )
    for item in latest_project_updates:
        key = f"auto:project-status:{item['project_id']}"
        active_keys.append(key)
        notes = f"Étape: {(item['stage'] or '-').replace('_', ' ').title()} | Progression: {item['progress'] or 0}%"
        if item["next_action"]:
            notes += f"\nProchaine action: {item['next_action']}"
        if item["next_action_date"]:
            notes += f"\nÉchéance: {item['next_action_date']}"
        if item["is_blocked"]:
            notes += "\nBloqué: Oui"
        execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES (?, 'project', ?, ?, ?, ?, 'pending', 'moyenne', ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(tracking_key) DO UPDATE SET
              title = excluded.title,
              context_label = excluded.context_label,
              due_date = excluded.due_date,
              status = 'pending',
              priority = excluded.priority,
              notes = excluded.notes,
              is_auto = 1,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                item["project_id"],
                "État du projet",
                item["project_title"],
                item["due_date"],
                notes,
            ),
        )

    upcoming_project_updates = query_all(
        """
        SELECT
          pu.project_id,
          p.title AS project_title,
          p.stage,
          p.progress,
          pu.next_action,
          pu.next_action_date
        FROM project_updates pu
        JOIN projects p ON p.id = pu.project_id
        WHERE pu.next_action IS NOT NULL
          AND pu.next_action <> ''
          AND pu.next_action_date IS NOT NULL
          AND pu.next_action_date <> ''
          AND date(pu.next_action_date) BETWEEN date('now') AND date('now', '+30 day')
        ORDER BY pu.project_id ASC, date(pu.next_action_date) ASC, pu.created_at DESC, pu.id DESC
        """
    )
    seen_projects = set()
    for item in upcoming_project_updates:
        project_id = item["project_id"]
        if project_id in seen_projects:
            continue
        seen_projects.add(project_id)
        key = f"auto:project-action:{project_id}"
        active_keys.append(key)
        execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES (?, 'project', ?, ?, ?, ?, 'pending', 'moyenne', ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(tracking_key) DO UPDATE SET
              title = excluded.title,
              context_label = excluded.context_label,
              due_date = excluded.due_date,
              status = 'pending',
              priority = excluded.priority,
              notes = excluded.notes,
              is_auto = 1,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                project_id,
                "Prochaine action projet",
                item["project_title"],
                item["next_action_date"],
                f"{item['next_action']}\nÉtape: {(item['stage'] or '-').replace('_', ' ').title()} | Progression: {item['progress'] or 0}%",
            ),
        )

    supplier_items = query_all(
        """
        SELECT d.id, d.title, d.expected_date, s.name AS supplier_name
        FROM supplier_deliveries d
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE d.status NOT IN ('delivered', 'validated')
          AND d.expected_date IS NOT NULL
          AND d.expected_date <> ''
          AND date(d.expected_date) < date('now')
        """
    )
    for item in supplier_items:
        key = f"auto:supplier-late:{item['id']}"
        active_keys.append(key)
        execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES (?, 'supplier_delivery', ?, ?, ?, ?, 'pending', 'haute', ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(tracking_key) DO UPDATE SET
              title = excluded.title,
              context_label = excluded.context_label,
              due_date = excluded.due_date,
              status = 'pending',
              priority = excluded.priority,
              notes = excluded.notes,
              is_auto = 1,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                item["id"],
                "Livraison fournisseur en retard",
                item["supplier_name"],
                item["expected_date"],
                item["title"],
            ),
        )

    auto_rows = query_all("SELECT tracking_key FROM tracking_items WHERE is_auto = 1")
    active_set = set(active_keys)
    for row in auto_rows:
        if row["tracking_key"] not in active_set:
            execute("DELETE FROM tracking_items WHERE tracking_key = ?", (row["tracking_key"],))


def _source_url(item):
    source_type = item["source_type"]
    source_id = item["source_id"]
    if not source_id:
        return None
    if source_type == "appointment":
        return url_for("appointments.list_appointments")
    if source_type == "project":
        return url_for("projects.project_detail", project_id=source_id)
    if source_type == "supplier_delivery":
        row = query_one("SELECT supplier_id FROM supplier_deliveries WHERE id = ?", (source_id,))
        if row:
            return url_for("suppliers.supplier_detail", supplier_id=row["supplier_id"])
        return url_for("suppliers.list_suppliers")
    return None


@followups_bp.route("/")
@permission_required("followups.view")
def list_followups():
    _sync_auto_tracking_items()
    tracking_total = query_one("SELECT COUNT(1) AS total FROM tracking_items")["total"]
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 12
    status = request.args.get("status", "").strip()
    source_type = request.args.get("source_type", "").strip()
    q = request.args.get("q", "").strip()
    clauses = []
    params = []
    if status in {"pending", "done"}:
        clauses.append("status = ?")
        params.append(status)
    if source_type in {"manual", "appointment", "project", "supplier_delivery", "followup"}:
        clauses.append("source_type = ?")
        params.append(source_type)
    if q:
        clauses.append("(title LIKE ? OR context_label LIKE ? OR notes LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    condition = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = query_one(f"SELECT COUNT(*) AS total FROM tracking_items {condition}", tuple(params))["total"]
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    followups = query_all(
        f"""
        SELECT
          *,
          CASE WHEN status = 'pending' AND due_date IS NOT NULL AND due_date <> '' AND date(due_date) < date('now') THEN 1 ELSE 0 END AS is_overdue
        FROM tracking_items
        {condition}
        ORDER BY
          CASE priority
            WHEN 'critique' THEN 1
            WHEN 'haute' THEN 2
            WHEN 'moyenne' THEN 3
            ELSE 4
          END,
          is_overdue DESC,
          COALESCE(due_date, '9999-12-31') ASC,
          created_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [per_page, offset]),
    )
    items = []
    source_labels = {
        "manual": "Manuel",
        "appointment": "Rendez-vous",
        "project": "Projet",
        "supplier_delivery": "Fournisseur",
        "followup": "Ancien suivi",
    }
    for row in followups:
        item = dict(row)
        item["source_label"] = source_labels.get(item["source_type"], item["source_type"])
        item["source_url"] = _source_url(row)
        items.append(item)
    return render_template(
        "followups.html",
        followups=items,
        tracking_total=tracking_total,
        status=status,
        source_type=source_type,
        q=q,
        page=page,
        total_pages=total_pages,
    )


@followups_bp.route("/new", methods=["GET", "POST"])
@permission_required("followups.manage")
def create_followup():
    selected_appointment_id = request.args.get("appointment_id", type=int)
    default_due_date = (date.today() + timedelta(days=2)).isoformat()
    prefill_context = request.args.get("context_label", "").strip()
    prefill_title = request.args.get("title", "").strip()
    return_to = request.args.get("return_to", "").strip()
    if not return_to.startswith("/"):
        return_to = ""
    appointments = query_all(
        """
        SELECT a.id, a.date, c.name AS client_name
        FROM appointments a
        JOIN clients c ON c.id = a.client_id
        ORDER BY a.date DESC
        """
    )
    if request.method == "POST":
        appointment_id = request.form.get("appointment_id", type=int)
        title = request.form.get("title", "").strip()
        return_to_post = (request.form.get("return_to") or "").strip()
        if not return_to_post.startswith("/"):
            return_to_post = ""
        if not title:
            flash("Le titre du suivi est requis.", "danger")
            return redirect(url_for("followups.create_followup", appointment_id=selected_appointment_id or ""))
        context_label = (request.form.get("context_label") or "").strip()
        source_type = "manual"
        source_id = None
        tracking_key = f"manual:{date.today().isoformat()}:{title}:{request.form.get('due_date', '')}:{request.form.get('notes', '')}"
        if appointment_id:
            appt = query_one(
                """
                SELECT a.id, c.name AS client_name
                FROM appointments a
                JOIN clients c ON c.id = a.client_id
                WHERE a.id = ?
                """,
                (appointment_id,),
            )
            if appt:
                source_type = "appointment"
                source_id = appt["id"]
                context_label = appt["client_name"]
                tracking_key = f"manual:appointment:{appt['id']}:{title}:{request.form.get('due_date', '')}"
        followup_id = execute(
            """
            INSERT INTO tracking_items(
              tracking_key, source_type, source_id, title, context_label, due_date, status, priority, notes, is_auto, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, CURRENT_TIMESTAMP)
            """,
            (
                tracking_key,
                source_type,
                source_id,
                title,
                context_label,
                request.form.get("due_date"),
                request.form.get("priority", "moyenne"),
                request.form.get("notes"),
            ),
        )
        log_action("create", "tracking_item", followup_id, {"title": title, "source_type": source_type})
        flash("Suivi créé.", "success")
        if return_to_post:
            return redirect(return_to_post)
        return redirect(url_for("followups.list_followups"))
    return render_template(
        "followup_form.html",
        followup=None,
        appointments=appointments,
        selected_appointment_id=selected_appointment_id,
        default_due_date=default_due_date,
        prefill_context=prefill_context,
        prefill_title=prefill_title,
        return_to=return_to,
    )


@followups_bp.route("/<int:followup_id>/done", methods=["POST"])
@permission_required("followups.manage")
def mark_followup_done(followup_id):
    execute("UPDATE tracking_items SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (followup_id,))
    log_action("mark_done", "tracking_item", followup_id)
    flash("Suivi marqué comme terminé.", "success")
    return redirect(url_for("followups.list_followups"))


@followups_bp.route("/<int:followup_id>/delete", methods=["POST"])
@permission_required("followups.delete")
def delete_followup(followup_id):
    row = query_one("SELECT is_auto FROM tracking_items WHERE id = ?", (followup_id,))
    if not row:
        flash("Suivi introuvable.", "danger")
        return redirect(url_for("followups.list_followups"))
    if row["is_auto"]:
        flash("Ce suivi est automatique. Traitez l'élément dans son module source.", "warning")
        return redirect(url_for("followups.list_followups"))
    execute("DELETE FROM tracking_items WHERE id = ?", (followup_id,))
    log_action("delete", "tracking_item", followup_id)
    flash("Suivi supprimé.", "info")
    return redirect(url_for("followups.list_followups"))

