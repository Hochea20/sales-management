from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for



from models.repositories import execute, query_all, query_one

from routes.audit import log_action

from routes.utils import permission_required



clients_bp = Blueprint("clients", __name__, url_prefix="/clients")

STAGE_OPTIONS = [
    ("prospect", "Prospect"),
    ("qualified", "Qualifié"),
    ("proposal", "Proposition"),
    ("negotiation", "Négociation"),
    ("won", "Gagné"),
    ("lost", "Perdu"),
]
STAGE_LABELS = {key: label for key, label in STAGE_OPTIONS}





def _per_page() -> int:

    row = query_one("SELECT value FROM app_settings WHERE key = 'items_per_page'")

    if row and str(row["value"]).isdigit():

        return max(5, min(int(row["value"]), 100))

    return 10





@clients_bp.route("/")

@permission_required("clients.view")

def list_clients():

    page = max(request.args.get("page", 1, type=int), 1)

    per_page = _per_page()

    q = request.args.get("q", "").strip()

    location = request.args.get("location", "").strip()

    clauses = []

    params = []



    if q:

        clauses.append("(name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ? OR location LIKE ? OR address LIKE ?)")

        params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])

    if location:

        clauses.append("location = ?")

        params.append(location)



    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    total = query_one(

        f"SELECT COUNT(*) AS total FROM clients {where_clause}",

        tuple(params),

    )["total"]

    total_pages = max((total + per_page - 1) // per_page, 1)

    page = min(page, total_pages)

    offset = (page - 1) * per_page



    clients = query_all(

        f"""

        SELECT * FROM clients

        {where_clause}

        ORDER BY created_at DESC

        LIMIT ? OFFSET ?

        """,

        tuple(params + [per_page, offset]),

    )

    locations = query_all(

        "SELECT DISTINCT location FROM clients WHERE location IS NOT NULL AND location <> '' ORDER BY location ASC"

    )

    return render_template(

        "clients.html",

        clients=clients,

        q=q,

        location=location,

        locations=locations,

        page=page,

        total_pages=total_pages,
        stage_labels=STAGE_LABELS,

    )





@clients_bp.route("/new", methods=["GET", "POST"])

@permission_required("clients.manage")

def create_client():

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        name = company
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        address = request.form.get("address", "").strip()
        activity_domain = request.form.get("activity_domain", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes")
        pipeline_stage = request.form.get("pipeline_stage", "prospect")
        duplicate = query_one(
            """
            SELECT id
            FROM clients
            WHERE lower(COALESCE(company, name)) = lower(?)
              AND (
                (? <> '' AND lower(COALESCE(email, '')) = lower(?))
                OR (? <> '' AND lower(COALESCE(company, name, '')) = lower(?))
                OR (? <> '' AND COALESCE(phone, '') = ?)
              )
            LIMIT 1
            """,
            (company, email, email, company, company, phone, phone),
        )
        if duplicate:
            flash("Ce client existe déjà (nom + email/entreprise/téléphone).", "warning")
            return render_template("client_form.html", client=None, stage_options=STAGE_OPTIONS)

        client_id = execute(

            """

            INSERT INTO clients(name, company, phone, location, address, activity_domain, email, notes, pipeline_stage)

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

            """,

            (

                name,

                company,

                phone,

                location,

                address,

                activity_domain,

                email,

                notes,

                pipeline_stage,

            ),

        )

        log_action("create", "client", client_id, {"company": company})

        flash("Client ajouté.", "success")

        return redirect(url_for("clients.list_clients"))

    return render_template("client_form.html", client=None, stage_options=STAGE_OPTIONS)





@clients_bp.route("/<int:client_id>/edit", methods=["GET", "POST"])

@permission_required("clients.manage")

def edit_client(client_id):

    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))

    if not client:

        flash("Client introuvable.", "danger")

        return redirect(url_for("clients.list_clients"))

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        name = company
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        address = request.form.get("address", "").strip()
        activity_domain = request.form.get("activity_domain", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes")
        pipeline_stage = request.form.get("pipeline_stage", "prospect")
        duplicate = query_one(
            """
            SELECT id
            FROM clients
            WHERE id <> ?
              AND lower(COALESCE(company, name)) = lower(?)
              AND (
                (? <> '' AND lower(COALESCE(email, '')) = lower(?))
                OR (? <> '' AND lower(COALESCE(company, name, '')) = lower(?))
                OR (? <> '' AND COALESCE(phone, '') = ?)
              )
            LIMIT 1
            """,
            (client_id, company, email, email, company, company, phone, phone),
        )
        if duplicate:
            flash("Un autre client similaire existe déjà (nom + email/entreprise/téléphone).", "warning")
            client_preview = {
                "id": client_id,
                "name": name,
                "company": company,
                "phone": phone,
                "location": location,
                "address": address,
                "activity_domain": activity_domain,
                "email": email,
                "notes": notes,
                "pipeline_stage": pipeline_stage,
            }
            return render_template("client_form.html", client=client_preview, stage_options=STAGE_OPTIONS)

        execute(

            """

            UPDATE clients

            SET name = ?, company = ?, phone = ?, location = ?, address = ?, activity_domain = ?, email = ?, notes = ?, pipeline_stage = ?

            WHERE id = ?

            """,

            (

                name,

                company,

                phone,

                location,

                address,

                activity_domain,

                email,

                notes,

                pipeline_stage,

                client_id,

            ),

        )

        log_action("update", "client", client_id, {"company": company})

        flash("Client mis à jour.", "success")

        return redirect(url_for("clients.list_clients"))

    return render_template("client_form.html", client=client, stage_options=STAGE_OPTIONS)


@clients_bp.route("/<int:client_id>")
@permission_required("clients.view")
def client_detail(client_id):
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if not client:
        flash("Client introuvable.", "danger")
        return redirect(url_for("clients.list_clients"))

    client_label = (client["company"] or client["name"] or "").strip()

    appt_stats = query_one(
        """
        SELECT
          COUNT(*) AS total_appointments,
          SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_appointments,
          SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done_appointments
        FROM appointments
        WHERE client_id = ?
        """,
        (client_id,),
    )
    next_appointment = query_one(
        """
        SELECT *
        FROM appointments
        WHERE client_id = ?
          AND status = 'pending'
          AND date(date) >= date('now')
        ORDER BY date(date) ASC, time ASC
        LIMIT 1
        """,
        (client_id,),
    )
    last_done_appointment = query_one(
        """
        SELECT *
        FROM appointments
        WHERE client_id = ?
          AND status = 'done'
        ORDER BY date(date) DESC, time DESC
        LIMIT 1
        """,
        (client_id,),
    )
    pending_tracking = query_one(
        """
        SELECT COUNT(*) AS total
        FROM tracking_items ti
        WHERE ti.status = 'pending'
          AND (
            (
              ti.source_type IN ('appointment', 'followup')
              AND EXISTS (
                SELECT 1 FROM appointments a
                WHERE a.id = ti.source_id AND a.client_id = ?
              )
            )
            OR lower(COALESCE(ti.context_label, '')) = lower(?)
          )
        """,
        (client_id, client_label),
    )
    projects = query_all(
        """
        SELECT id, title, status, stage, progress, next_action, due_date, priority
        FROM projects
        WHERE client_id = ?
        ORDER BY
          CASE priority
            WHEN 'critique' THEN 1
            WHEN 'haute' THEN 2
            WHEN 'moyenne' THEN 3
            ELSE 4
          END,
          due_date ASC,
          created_at DESC
        """,
        (client_id,),
    )
    timeline = query_all(
        """
        SELECT *
        FROM (
          SELECT
            a.created_at AS event_at,
            'Rendez-vous' AS event_type,
            ('RDV le ' || COALESCE(a.date, '-') || ' à ' || COALESCE(a.time, '-')) AS title,
            ('Statut: ' || COALESCE(a.status, '-')) AS details
          FROM appointments a
          WHERE a.client_id = ?
          UNION ALL
          SELECT
            pu.created_at AS event_at,
            'Projet' AS event_type,
            p.title AS title,
            pu.summary AS details
          FROM project_updates pu
          JOIN projects p ON p.id = pu.project_id
          WHERE p.client_id = ?
          UNION ALL
          SELECT
            ti.created_at AS event_at,
            'Suivi' AS event_type,
            ti.title AS title,
            COALESCE(ti.notes, ti.context_label, '-') AS details
          FROM tracking_items ti
          WHERE lower(COALESCE(ti.context_label, '')) = lower(?)
        )
        ORDER BY datetime(event_at) DESC
        LIMIT 30
        """,
        (client_id, client_id, client_label),
    )

    return render_template(
        "client_detail.html",
        client=client,
        stage_labels=STAGE_LABELS,
        appt_stats=appt_stats or {},
        next_appointment=next_appointment,
        last_done_appointment=last_done_appointment,
        pending_tracking=(pending_tracking["total"] if pending_tracking else 0),
        projects=projects,
        timeline=timeline,
    )


@clients_bp.route("/<int:client_id>/notes", methods=["POST"])
@permission_required("clients.manage")
def add_client_note(client_id):
    client = query_one("SELECT id, notes FROM clients WHERE id = ?", (client_id,))
    if not client:
        flash("Client introuvable.", "danger")
        return redirect(url_for("clients.list_clients"))

    note_text = request.form.get("note_text", "").strip()
    if not note_text:
        flash("Veuillez saisir une note.", "warning")
        return redirect(url_for("clients.client_detail", client_id=client_id))

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    current = (client["notes"] or "").strip()
    appended = f"[{stamp}] {note_text}" if not current else f"{current}\n[{stamp}] {note_text}"
    execute("UPDATE clients SET notes = ? WHERE id = ?", (appended, client_id))
    log_action("update_notes", "client", client_id, {"note": note_text})
    flash("Note ajoutée.", "success")
    return redirect(url_for("clients.client_detail", client_id=client_id))


@clients_bp.route("/<int:client_id>/delete", methods=["POST"])

@permission_required("clients.delete")

def delete_client(client_id):

    execute("DELETE FROM clients WHERE id = ?", (client_id,))

    log_action("delete", "client", client_id)

    flash("Client supprimé.", "info")

    return redirect(url_for("clients.list_clients"))

