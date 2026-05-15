from flask import Blueprint, render_template, request

from models.repositories import query_all
from routes.utils import permission_required

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/")
@permission_required("dashboard.view")
def global_search():
    q = request.args.get("q", "").strip()
    clients = []
    appointments = []
    followups = []

    if q:
        like_q = f"%{q}%"
        clients = query_all(
            """
            SELECT id, name, company, email, phone
            FROM clients
            WHERE name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (like_q, like_q, like_q, like_q),
        )
        appointments = query_all(
            """
            SELECT a.id, a.date, a.time, a.location, a.status, c.name AS client_name
            FROM appointments a
            JOIN clients c ON c.id = a.client_id
            WHERE c.name LIKE ? OR a.location LIKE ? OR a.notes LIKE ?
            ORDER BY a.date DESC, a.time DESC
            LIMIT 10
            """,
            (like_q, like_q, like_q),
        )
        followups = query_all(
            """
            SELECT f.id, f.title, f.due_date, f.status, COALESCE(f.context_label, '-') AS client_name
            FROM tracking_items f
            WHERE f.title LIKE ? OR f.notes LIKE ? OR f.context_label LIKE ?
            ORDER BY f.due_date DESC
            LIMIT 10
            """,
            (like_q, like_q, like_q),
        )

    return render_template(
        "search_results.html",
        q=q,
        clients=clients,
        appointments=appointments,
        followups=followups,
    )
