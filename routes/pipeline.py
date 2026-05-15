from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.repositories import execute, query_all
from routes.audit import log_action
from routes.utils import permission_required

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")

PIPELINE_STAGES = [
    ("prospect", "Prospect"),
    ("qualified", "Qualifié"),
    ("proposal", "Proposition"),
    ("negotiation", "Négociation"),
    ("won", "Gagné"),
    ("lost", "Perdu"),
]


@pipeline_bp.route("/")
@permission_required("pipeline.view")
def board():
    q = request.args.get("q", "").strip()
    company = request.args.get("company", "").strip()
    clauses = []
    params = []
    if q:
        clauses.append("(name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
    if company:
        clauses.append("company = ?")
        params.append(company)
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    clients = query_all(
        f"""
        SELECT id, name, company, email, phone, pipeline_stage
        FROM clients
        {where_clause}
        ORDER BY created_at DESC
        """
        ,
        tuple(params),
    )
    companies = query_all(
        "SELECT DISTINCT company FROM clients WHERE company IS NOT NULL AND company <> '' ORDER BY company ASC"
    )
    grouped = {key: [] for key, _ in PIPELINE_STAGES}
    for client in clients:
        grouped.setdefault(client["pipeline_stage"], []).append(client)
    return render_template(
        "pipeline.html",
        stages=PIPELINE_STAGES,
        grouped=grouped,
        q=q,
        company=company,
        companies=companies,
    )


@pipeline_bp.route("/move", methods=["POST"])
@permission_required("pipeline.manage")
def move():
    client_id = request.form.get("client_id", type=int)
    stage = request.form.get("stage", "")
    valid_stages = {key for key, _ in PIPELINE_STAGES}
    if not client_id or stage not in valid_stages:
        flash("Mouvement invalide.", "danger")
        return redirect(url_for("pipeline.board"))

    execute(
        "UPDATE clients SET pipeline_stage = ? WHERE id = ?",
        (stage, client_id),
    )
    log_action("move_stage", "client", client_id, {"stage": stage})
    flash("Étape du pipeline mise à jour.", "success")
    return redirect(url_for("pipeline.board"))
