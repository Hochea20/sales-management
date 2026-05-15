from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models.repositories import execute, query_all, query_one
from routes.audit import log_action
from routes.utils import permission_required

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")

STATUS_CHOICES = [
    ("en_cours", "En cours"),
    ("en_attente", "En attente"),
    ("termine", "Terminé"),
]
PRIORITY_CHOICES = [
    ("basse", "Basse"),
    ("moyenne", "Moyenne"),
    ("haute", "Haute"),
    ("critique", "Critique"),
]
ASSIGNEE_CHOICES = [
    ("technicien", "Technicien"),
    ("administration", "Administration"),
    ("sales", "Sales"),
]
STAGE_CHOICES = [
    ("cadrage", "Cadrage"),
    ("planification", "Planification"),
    ("lancement", "Lancement"),
    ("execution", "Exécution"),
    ("suivi_client", "Suivi client"),
    ("validation", "Validation"),
    ("livraison", "Livraison"),
    ("cloture", "Clôture"),
]
PROGRESS_CHOICES = [0, 25, 50, 75, 100]
def _active_users():
    return query_all("SELECT id, username, role FROM users WHERE is_active = 1 ORDER BY username ASC")


def _sync_assignments(project_id: int, user_ids):
    execute("DELETE FROM project_user_assignments WHERE project_id = ?", (project_id,))
    for uid in sorted(set(user_ids)):
        execute("INSERT INTO project_user_assignments(project_id, user_id) VALUES (?, ?)", (project_id, uid))


def _sync_project_status(project_id: int):
    row = query_one(
        """
        SELECT
          p.progress,
          (
            SELECT pu.is_blocked
            FROM project_updates pu
            WHERE pu.project_id = p.id
            ORDER BY pu.created_at DESC, pu.id DESC
            LIMIT 1
          ) AS latest_blocked
        FROM projects p
        WHERE p.id = ?
        """,
        (project_id,),
    )
    if not row:
        return
    if (row["latest_blocked"] or 0) == 1:
        status = "en_attente"
    elif (row["progress"] or 0) >= 100:
        status = "termine"
    else:
        status = "en_cours"
    execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))


@projects_bp.route("/")
@permission_required("projects.view")
def list_projects():
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    mine = request.args.get("mine", "0") == "1"
    focus_today = request.args.get("focus_today", "0") == "1"
    current_user_id = session.get("user_id")
    clauses = []
    params = []

    if status in {k for k, _ in STATUS_CHOICES}:
        clauses.append("p.status = ?")
        params.append(status)
    if mine and current_user_id:
        clauses.append(
            "EXISTS (SELECT 1 FROM project_user_assignments pa2 WHERE pa2.project_id = p.id AND pa2.user_id = ?)"
        )
        params.append(current_user_id)
    if focus_today:
        clauses.append(
            """
            (
              date(p.due_date) = date('now')
              OR (date(p.due_date) < date('now') AND p.progress < 100)
              OR EXISTS (
                SELECT 1
                FROM project_updates pu3
                WHERE pu3.project_id = p.id
                  AND pu3.is_blocked = 1
              )
            )
            """
        )
    if q:
        clauses.append("(p.title LIKE ? OR p.owner_name LIKE ? OR p.next_action LIKE ? OR c.name LIKE ?)")
        params.extend([f"%{q}%"] * 4)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    projects = query_all(
        f"""
        SELECT
          p.*,
          c.name AS client_name,
          GROUP_CONCAT(u.username, ', ') AS assignees
        FROM projects p
        LEFT JOIN clients c ON c.id = p.client_id
        LEFT JOIN project_user_assignments pa ON pa.project_id = p.id
        LEFT JOIN users u ON u.id = pa.user_id
        {where_sql}
        GROUP BY p.id
        ORDER BY
          CASE p.priority
            WHEN 'critique' THEN 1
            WHEN 'haute' THEN 2
            WHEN 'moyenne' THEN 3
            ELSE 4
          END,
          p.due_date ASC,
          p.created_at DESC
        """,
        tuple(params),
    )

    blocked_projects = query_all(
        """
        SELECT DISTINCT p.id, p.title, p.due_date
        FROM projects p
        JOIN project_updates pu ON pu.project_id = p.id
        WHERE pu.is_blocked = 1
        ORDER BY pu.created_at DESC
        LIMIT 8
        """
    )
    late_projects = query_all(
        """
        SELECT id, title, due_date, progress
        FROM projects
        WHERE due_date IS NOT NULL
          AND due_date <> ''
          AND date(due_date) < date('now')
          AND progress < 100
        ORDER BY due_date ASC
        LIMIT 8
        """
    )
    my_counts = query_one(
        """
        SELECT
          COUNT(*) AS mine_total,
          SUM(CASE WHEN p.due_date IS NOT NULL AND p.due_date <> '' AND date(p.due_date) = date('now') THEN 1 ELSE 0 END) AS mine_due_today,
          SUM(CASE WHEN p.due_date IS NOT NULL AND p.due_date <> '' AND date(p.due_date) < date('now') AND p.progress < 100 THEN 1 ELSE 0 END) AS mine_overdue
        FROM projects p
        WHERE EXISTS (
          SELECT 1 FROM project_user_assignments pa
          WHERE pa.project_id = p.id AND pa.user_id = ?
        )
        """,
        (current_user_id or 0,),
    )
    my_blocked = query_one(
        """
        SELECT COUNT(*) AS mine_blocked
        FROM projects p
        WHERE EXISTS (
          SELECT 1 FROM project_user_assignments pa
          WHERE pa.project_id = p.id AND pa.user_id = ?
        )
        AND EXISTS (
          SELECT 1 FROM project_updates pu
          WHERE pu.project_id = p.id AND pu.is_blocked = 1
        )
        """,
        (current_user_id or 0,),
    )

    return render_template(
        "projects.html",
        projects=projects,
        q=q,
        status=status,
        mine=mine,
        focus_today=focus_today,
        status_choices=STATUS_CHOICES,
        blocked_projects=blocked_projects,
        late_projects=late_projects,
        my_counts=my_counts,
        my_blocked=my_blocked,
    )


@projects_bp.route("/new", methods=["GET", "POST"])
@permission_required("projects.manage")
def create_project():
    clients = query_all("SELECT id, name FROM clients ORDER BY name ASC")
    users = _active_users()
    if request.method == "POST":
        assignee_user_id = request.form.get("assignee_user_id", type=int)
        project_id = execute(
            """
            INSERT INTO projects(
              title, client_id, owner_name, assignee_type, stage, status, priority, progress,
              next_action, due_date, notes
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form.get("title"),
                request.form.get("client_id") or None,
                request.form.get("owner_name"),
                "technicien",
                "cadrage",
                "en_cours",
                request.form.get("priority", "moyenne"),
                0,
                "",
                request.form.get("due_date"),
                request.form.get("notes"),
            ),
        )
        _sync_assignments(project_id, [assignee_user_id] if assignee_user_id else [])
        _sync_project_status(project_id)
        log_action("create", "project", project_id, {"title": request.form.get("title")})
        flash("Projet créé.", "success")
        return redirect(url_for("projects.project_detail", project_id=project_id))
    return render_template(
        "project_form.html",
        project=None,
        assigned_user_id=None,
        clients=clients,
        users=users,
        status_choices=STATUS_CHOICES,
        priority_choices=PRIORITY_CHOICES,
        stage_choices=STAGE_CHOICES,
    )


@projects_bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
@permission_required("projects.manage")
def edit_project(project_id):
    project = query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.list_projects"))
    clients = query_all("SELECT id, name FROM clients ORDER BY name ASC")
    users = _active_users()
    assigned_rows = query_all(
        "SELECT user_id FROM project_user_assignments WHERE project_id = ?",
        (project_id,),
    )
    assigned_user_ids = [row["user_id"] for row in assigned_rows]
    assigned_user_id = assigned_user_ids[0] if assigned_user_ids else None

    if request.method == "POST":
        assignee_type = request.form.get("assignee_type", project["assignee_type"] or "technicien")
        if assignee_type not in {k for k, _ in ASSIGNEE_CHOICES}:
            assignee_type = "technicien"
        assignee_user_id = request.form.get("assignee_user_id", type=int)
        execute(
            """
            UPDATE projects
            SET title = ?, client_id = ?, owner_name = ?, assignee_type = ?,
                priority = ?, next_action = ?, due_date = ?, notes = ?
            WHERE id = ?
            """,
            (
                request.form.get("title"),
                request.form.get("client_id") or None,
                request.form.get("owner_name"),
                assignee_type,
                request.form.get("priority", "moyenne"),
                request.form.get("next_action", project["next_action"]),
                request.form.get("due_date"),
                request.form.get("notes"),
                project_id,
            ),
        )
        _sync_assignments(project_id, [assignee_user_id] if assignee_user_id else [])
        _sync_project_status(project_id)
        log_action("update", "project", project_id, {"title": request.form.get("title")})
        flash("Projet mis à jour.", "success")
        return redirect(url_for("projects.project_detail", project_id=project_id))
    return render_template(
        "project_form.html",
        project=project,
        assigned_user_id=assigned_user_id,
        clients=clients,
        users=users,
        status_choices=STATUS_CHOICES,
        priority_choices=PRIORITY_CHOICES,
        assignee_choices=ASSIGNEE_CHOICES,
        stage_choices=STAGE_CHOICES,
    )


@projects_bp.route("/<int:project_id>")
@permission_required("projects.view")
def project_detail(project_id):
    project = query_one(
        """
        SELECT p.*, c.name AS client_name
        FROM projects p
        LEFT JOIN clients c ON c.id = p.client_id
        WHERE p.id = ?
        """,
        (project_id,),
    )
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.list_projects"))

    _sync_project_status(project_id)
    project = query_one(
        "SELECT p.*, c.name AS client_name FROM projects p LEFT JOIN clients c ON c.id = p.client_id WHERE p.id = ?",
        (project_id,),
    )

    updates = query_all(
        """
        SELECT pu.*, u.username
        FROM project_updates pu
        LEFT JOIN users u ON u.id = pu.user_id
        WHERE pu.project_id = ?
        ORDER BY pu.created_at DESC, pu.id DESC
        LIMIT 100
        """,
        (project_id,),
    )
    return render_template(
        "project_detail.html",
        project=project,
        updates=updates,
        stage_choices=STAGE_CHOICES,
        progress_choices=PROGRESS_CHOICES,
    )


@projects_bp.route("/<int:project_id>/updates", methods=["POST"])
@permission_required("projects.manage")
def add_project_update(project_id):
    project = query_one("SELECT id, stage, progress FROM projects WHERE id = ?", (project_id,))
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.list_projects"))
    summary = request.form.get("summary", "").strip()
    if not summary:
        flash("Le résumé du suivi est requis.", "danger")
        return redirect(url_for("projects.project_detail", project_id=project_id))
    risk_level = request.form.get("risk_level", "moyen")
    if risk_level not in {"faible", "moyen", "eleve"}:
        risk_level = "moyen"
    is_blocked = 1 if request.form.get("is_blocked") == "1" else 0
    stage = request.form.get("stage", "").strip()
    if stage not in {k for k, _ in STAGE_CHOICES}:
        stage = None
    progress = request.form.get("progress", type=int)
    if progress not in PROGRESS_CHOICES:
        progress = None
    selected_stage = stage if stage is not None else project["stage"]
    selected_progress = progress if progress is not None else project["progress"]

    if stage is not None and progress is not None:
        execute(
            "UPDATE projects SET stage = ?, progress = ?, next_action = ? WHERE id = ?",
            (stage, progress, request.form.get("next_action"), project_id),
        )
    elif stage is not None:
        execute(
            "UPDATE projects SET stage = ?, next_action = ? WHERE id = ?",
            (stage, request.form.get("next_action"), project_id),
        )
    elif progress is not None:
        execute(
            "UPDATE projects SET progress = ?, next_action = ? WHERE id = ?",
            (progress, request.form.get("next_action"), project_id),
        )
    else:
        execute("UPDATE projects SET next_action = ? WHERE id = ?", (request.form.get("next_action"), project_id))

    execute(
        """
        INSERT INTO project_updates(
          project_id, user_id, update_type, summary, result, next_action, next_action_date, risk_level, is_blocked, stage_snapshot, progress_snapshot
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            session.get("user_id"),
            request.form.get("update_type", "suivi"),
            summary,
            request.form.get("result"),
            request.form.get("next_action"),
            request.form.get("next_action_date"),
            risk_level,
            is_blocked,
            selected_stage,
            selected_progress,
        ),
    )
    _sync_project_status(project_id)
    log_action("add_update", "project", project_id, {"summary": summary})
    flash("Entrée de suivi ajoutée.", "success")
    return redirect(url_for("projects.project_detail", project_id=project_id))


@projects_bp.route("/<int:project_id>/delete", methods=["POST"])
@permission_required("projects.delete")
def delete_project(project_id):
    execute("DELETE FROM projects WHERE id = ?", (project_id,))
    log_action("delete", "project", project_id)
    flash("Projet supprimé.", "info")
    return redirect(url_for("projects.list_projects"))
