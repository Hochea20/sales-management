from flask import Blueprint, flash, redirect, render_template, request, session, url_for



from models.repositories import execute, query_all, query_one

from routes.audit import log_action

from routes.utils import permission_required



appointments_bp = Blueprint("appointments", __name__, url_prefix="/appointments")
VALID_STATUSES = {"pending", "done"}


def _log_appointment_update(
    appointment_id: int,
    summary: str,
    *,
    status_snapshot: str | None = None,
    date_snapshot: str | None = None,
    time_snapshot: str | None = None,
    location_snapshot: str | None = None,
    notes_snapshot: str | None = None,
):
    user_id = session.get("user_id")
    execute(
        """
        INSERT INTO appointment_updates(
          appointment_id, user_id, summary,
          status_snapshot, date_snapshot, time_snapshot, location_snapshot, notes_snapshot
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            appointment_id,
            user_id,
            summary,
            status_snapshot,
            date_snapshot,
            time_snapshot,
            location_snapshot,
            notes_snapshot,
        ),
    )





def _per_page() -> int:

    row = query_one("SELECT value FROM app_settings WHERE key = 'items_per_page'")

    if row and str(row["value"]).isdigit():

        return max(5, min(int(row["value"]), 100))

    return 10





@appointments_bp.route("/")

@permission_required("appointments.view")

def list_appointments():

    page = max(request.args.get("page", 1, type=int), 1)

    per_page = _per_page()

    view_mode = request.args.get("view", "list")

    q = request.args.get("q", "").strip()

    status = request.args.get("status", "").strip()

    date_from = request.args.get("date_from", "").strip()

    date_to = request.args.get("date_to", "").strip()

    clauses = []

    params = []



    if q:

        clauses.append("(c.name LIKE ? OR a.location LIKE ? OR a.notes LIKE ?)")

        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if status in {"pending", "done"}:

        clauses.append("a.status = ?")

        params.append(status)

    if date_from:

        clauses.append("date(a.date) >= date(?)")

        params.append(date_from)

    if date_to:

        clauses.append("date(a.date) <= date(?)")

        params.append(date_to)



    condition = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    total = query_one(

        f"""

        SELECT COUNT(*) AS total

        FROM appointments a

        JOIN clients c ON c.id = a.client_id

        {condition}

        """,

        tuple(params),

    )["total"]

    total_pages = max((total + per_page - 1) // per_page, 1)

    page = min(page, total_pages)

    offset = (page - 1) * per_page



    appointments = query_all(

        f"""

        SELECT a.*, c.name AS client_name

        FROM appointments a

        JOIN clients c ON c.id = a.client_id

        {condition}

        ORDER BY a.date ASC, a.time ASC

        LIMIT ? OFFSET ?

        """,

        tuple(params + [per_page, offset]),

    )
    today_appointments = query_all(
        """
        SELECT a.*, c.name AS client_name
        FROM appointments a
        JOIN clients c ON c.id = a.client_id
        WHERE date(a.date) = date('now')
        ORDER BY a.time ASC
        LIMIT 12
        """
    )
    updates_map = {}
    if appointments:
        ids = [a["id"] for a in appointments]
        placeholders = ",".join(["?"] * len(ids))
        rows = query_all(
            f"""
            SELECT au.*, u.username
            FROM appointment_updates au
            LEFT JOIN users u ON u.id = au.user_id
            WHERE au.appointment_id IN ({placeholders})
            ORDER BY au.created_at DESC, au.id DESC
            """,
            tuple(ids),
        )
        for r in rows:
            updates_map.setdefault(r["appointment_id"], []).append(r)


    return render_template(

        "appointments.html",

        appointments=appointments,
        today_appointments=today_appointments,
        updates_map=updates_map,

        clients=query_all("SELECT id, name FROM clients ORDER BY name ASC"),

        view_mode=view_mode,

        q=q,

        status=status,

        date_from=date_from,

        date_to=date_to,

        page=page,

        total_pages=total_pages,

    )





@appointments_bp.route("/new", methods=["GET", "POST"])

@permission_required("appointments.manage")

def create_appointment():

    clients = query_all("SELECT id, name FROM clients ORDER BY name ASC")
    selected_client_id = request.args.get("client_id", type=int)
    return_to = request.args.get("return_to", "").strip()
    if not return_to.startswith("/"):
        return_to = ""

    if request.method == "POST":
        status = request.form.get("status", "pending").strip()
        if status not in VALID_STATUSES:
            status = "pending"
        return_to_post = (request.form.get("return_to") or "").strip()
        if not return_to_post.startswith("/"):
            return_to_post = ""

        appointment_id = execute(

            """

            INSERT INTO appointments(client_id, date, time, location, notes, status)

            VALUES (?, ?, ?, ?, ?, ?)

            """,

            (

                request.form.get("client_id"),

                request.form.get("date"),

                request.form.get("time"),

                request.form.get("location"),

                request.form.get("notes"),
                status,

            ),

        )

        log_action("create", "appointment", appointment_id)
        _log_appointment_update(
            appointment_id,
            "Rendez-vous planifié",
            status_snapshot=status,
            date_snapshot=request.form.get("date"),
            time_snapshot=request.form.get("time"),
            location_snapshot=request.form.get("location"),
            notes_snapshot=request.form.get("notes"),
        )

        flash("Rendez-vous planifié.", "success")

        if return_to_post:
            return redirect(return_to_post)
        return redirect(url_for("appointments.list_appointments"))

    return render_template(
        "appointment_form.html",
        appointment=None,
        clients=clients,
        selected_client_id=selected_client_id,
        return_to=return_to,
    )





@appointments_bp.route("/<int:appointment_id>/edit", methods=["GET", "POST"])

@permission_required("appointments.manage")

def edit_appointment(appointment_id):

    appointment = query_one("SELECT * FROM appointments WHERE id = ?", (appointment_id,))

    clients = query_all("SELECT id, name FROM clients ORDER BY name ASC")

    if not appointment:

        flash("Rendez-vous introuvable.", "danger")

        return redirect(url_for("appointments.list_appointments"))

    if request.method == "POST":
        status = request.form.get("status", "pending").strip()
        if status not in VALID_STATUSES:
            status = "pending"

        execute(

            """

            UPDATE appointments

            SET client_id = ?, date = ?, time = ?, location = ?, notes = ?, status = ?

            WHERE id = ?

            """,

            (

                request.form.get("client_id"),

                request.form.get("date"),

                request.form.get("time"),

                request.form.get("location"),

                request.form.get("notes"),
                status,

                appointment_id,

            ),

        )

        log_action("update", "appointment", appointment_id)
        _log_appointment_update(
            appointment_id,
            "Rendez-vous modifié",
            status_snapshot=status,
            date_snapshot=request.form.get("date"),
            time_snapshot=request.form.get("time"),
            location_snapshot=request.form.get("location"),
            notes_snapshot=request.form.get("notes"),
        )

        flash("Rendez-vous mis à jour.", "success")

        return redirect(url_for("appointments.list_appointments"))

    return render_template("appointment_form.html", appointment=appointment, clients=clients)





@appointments_bp.route("/<int:appointment_id>/done", methods=["POST"])

@permission_required("appointments.manage")

def mark_done(appointment_id):

    execute("UPDATE appointments SET status = 'done' WHERE id = ?", (appointment_id,))

    log_action("mark_done", "appointment", appointment_id)
    _log_appointment_update(appointment_id, "Marqué comme terminé", status_snapshot="done")

    flash("Rendez-vous marqué comme terminé.", "success")

    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appointment_id>/status", methods=["POST"])
@permission_required("appointments.manage")
def update_status(appointment_id):
    status = request.form.get("status", "").strip()
    if status not in VALID_STATUSES:
        flash("Statut invalide.", "danger")
        return redirect(url_for("appointments.list_appointments"))

    execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appointment_id))
    log_action("update_status", "appointment", appointment_id, {"status": status})
    _log_appointment_update(appointment_id, "Changement de statut", status_snapshot=status)
    flash("Statut du rendez-vous mis à jour.", "success")
    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appointment_id>/update", methods=["POST"])
@permission_required("appointments.manage")
def quick_update(appointment_id):
    appointment = query_one(
        """
        SELECT a.*, c.name AS client_name
        FROM appointments a
        JOIN clients c ON c.id = a.client_id
        WHERE a.id = ?
        """,
        (appointment_id,),
    )
    if not appointment:
        flash("Rendez-vous introuvable.", "danger")
        return redirect(url_for("appointments.list_appointments"))

    status = request.form.get("status", appointment["status"]).strip()
    if status not in VALID_STATUSES:
        status = appointment["status"]

    date_value = (request.form.get("date") or "").strip() or appointment["date"]
    time_value = (request.form.get("time") or "").strip() or appointment["time"]
    location_value = (request.form.get("location") or "").strip()
    notes_value = (request.form.get("notes") or "").strip()
    summary = (request.form.get("summary") or "").strip() or "Mise à jour"

    execute(
        """
        UPDATE appointments
        SET status = ?,
            date = ?,
            time = ?,
            location = ?,
            notes = ?
        WHERE id = ?
        """,
        (
            status,
            date_value,
            time_value,
            location_value if location_value != "" else appointment["location"],
            notes_value if notes_value != "" else appointment["notes"],
            appointment_id,
        ),
    )
    _log_appointment_update(
        appointment_id,
        summary,
        status_snapshot=status,
        date_snapshot=date_value,
        time_snapshot=time_value,
        location_snapshot=location_value if location_value != "" else appointment["location"],
        notes_snapshot=notes_value if notes_value != "" else appointment["notes"],
    )
    log_action(
        "update",
        "appointment",
        appointment_id,
        {"status": status, "date": date_value, "time": time_value},
    )
    flash("Mise à jour enregistrée.", "success")
    return redirect(url_for("appointments.list_appointments"))





@appointments_bp.route("/<int:appointment_id>/delete", methods=["POST"])

@permission_required("appointments.delete")

def delete_appointment(appointment_id):

    execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))

    log_action("delete", "appointment", appointment_id)

    flash("Rendez-vous supprimé.", "info")

    return redirect(url_for("appointments.list_appointments"))

