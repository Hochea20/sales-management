from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.repositories import execute, query_all, query_one
from routes.audit import log_action
from routes.utils import permission_required

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")

SUPPLIER_TYPES = [
    ("fournisseur", "Fournisseur"),
    ("partenaire", "Partenaire"),
]
DELIVERY_STATUS = [
    ("planned", "Prévu"),
    ("in_progress", "En cours"),
    ("partial", "Partiel"),
    ("delivered", "Livré"),
    ("validated", "Validé"),
]
PROGRESS_BY_STATUS = {
    "planned": 10,
    "in_progress": 45,
    "partial": 70,
    "delivered": 90,
    "validated": 100,
}
QUALITY_CHOICES = [
    ("ok", "Conforme"),
    ("warning", "À vérifier"),
    ("issue", "Non conforme"),
]


def _safe_status(value: str) -> str:
    valid = {k for k, _ in DELIVERY_STATUS}
    return value if value in valid else "planned"


def _safe_quality(value: str) -> str:
    valid = {k for k, _ in QUALITY_CHOICES}
    return value if value in valid else "ok"


def _status_labels():
    return {k: label for k, label in DELIVERY_STATUS}


def _quality_labels():
    return {k: label for k, label in QUALITY_CHOICES}


@suppliers_bp.route("/")
@permission_required("suppliers.view")
def list_suppliers():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    clauses = []
    params = []
    if q:
        clauses.append("(s.name LIKE ? OR s.contact_name LIKE ? OR s.service_category LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    suppliers = query_all(
        f"""
        SELECT
          s.*,
          COUNT(d.id) AS deliveries_total,
          SUM(CASE WHEN d.status NOT IN ('delivered', 'validated') THEN 1 ELSE 0 END) AS deliveries_open
        FROM suppliers s
        LEFT JOIN supplier_deliveries d ON d.supplier_id = s.id
        {where_sql}
        GROUP BY s.id
        ORDER BY s.created_at DESC
        """,
        tuple(params),
    )
    score_rows = query_all(
        """
        SELECT
          s.id AS supplier_id,
          COUNT(d.id) AS total_deliveries,
          SUM(CASE WHEN d.status IN ('delivered', 'validated') THEN 1 ELSE 0 END) AS closed_deliveries,
          SUM(
            CASE WHEN d.status IN ('delivered', 'validated')
                   AND COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                   AND COALESCE(d.expected_date, d.planned_date) <> ''
                   AND d.delivered_date IS NOT NULL AND d.delivered_date <> ''
                   AND date(d.delivered_date) <= date(COALESCE(d.expected_date, d.planned_date))
                 THEN 1 ELSE 0 END
          ) AS on_time_deliveries,
          SUM(CASE WHEN d.quality_status = 'issue' THEN 1 ELSE 0 END) AS quality_issues,
          SUM(CASE WHEN d.blocker IS NOT NULL AND d.blocker <> '' THEN 1 ELSE 0 END) AS blocker_count
        FROM suppliers s
        LEFT JOIN supplier_deliveries d ON d.supplier_id = s.id
        GROUP BY s.id
        """
    )
    score_map = {}
    for row in score_rows:
        total = row["total_deliveries"] or 0
        closed = row["closed_deliveries"] or 0
        on_time = row["on_time_deliveries"] or 0
        quality_issues = row["quality_issues"] or 0
        blockers = row["blocker_count"] or 0

        punctuality = (on_time / closed) * 100 if closed else 100
        quality = ((total - quality_issues) / total) * 100 if total else 100
        stability = ((total - blockers) / total) * 100 if total else 100
        reactivity = 100 if (blockers == 0 and quality_issues == 0) else max(30, 100 - ((blockers + quality_issues) * 10))
        score = int((punctuality * 0.4) + (quality * 0.3) + (stability * 0.2) + (reactivity * 0.1))
        score_map[row["supplier_id"]] = max(0, min(100, score))

    suppliers = [
        {
            **dict(item),
            "score": score_map.get(item["id"], 0),
        }
        for item in suppliers
    ]

    alert_clauses = [
        "d.status NOT IN ('delivered', 'validated')",
        "COALESCE(d.expected_date, d.planned_date) IS NOT NULL",
        "COALESCE(d.expected_date, d.planned_date) <> ''",
        "date(COALESCE(d.expected_date, d.planned_date)) < date('now')",
    ]
    alert_params = []
    if status in {"late", "blocked", "quality"}:
        if status == "blocked":
            alert_clauses.append("d.blocker IS NOT NULL AND d.blocker <> ''")
        elif status == "quality":
            alert_clauses.append("d.quality_status = 'issue'")
    alerts = query_all(
        f"""
        SELECT
          d.id,
          d.title,
          d.reference_code,
          COALESCE(d.expected_date, d.planned_date) AS expected_date,
          d.status,
          d.progress,
          d.blocker,
          d.quality_status,
          s.name AS supplier_name
        FROM supplier_deliveries d
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE {' AND '.join(alert_clauses)}
        ORDER BY date(COALESCE(d.expected_date, d.planned_date)) ASC
        LIMIT 12
        """,
        tuple(alert_params),
    )
    decision_items = query_all(
        """
        SELECT
          d.id,
          d.supplier_id,
          s.name AS supplier_name,
          d.title,
          d.reference_code,
          COALESCE(d.expected_date, d.planned_date) AS expected_date,
          d.status,
          d.progress,
          d.amount,
          d.currency,
          d.blocker,
          d.quality_status,
          p.title AS project_title,
          CASE
            WHEN COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                 AND COALESCE(d.expected_date, d.planned_date) <> ''
                 AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
            THEN CAST(julianday('now') - julianday(COALESCE(d.expected_date, d.planned_date)) AS INT)
            ELSE 0
          END AS days_late,
          CASE
            WHEN d.blocker IS NOT NULL AND d.blocker <> '' THEN 'Escalader immédiatement'
            WHEN d.quality_status = 'issue' THEN 'Ouvrir incident qualité'
            WHEN COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                 AND COALESCE(d.expected_date, d.planned_date) <> ''
                 AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
            THEN 'Relancer fournisseur'
            WHEN d.status = 'partial' THEN 'Planifier livraison complémentaire'
            ELSE 'Suivi normal'
          END AS action_recommandee
        FROM supplier_deliveries d
        JOIN suppliers s ON s.id = d.supplier_id
        LEFT JOIN projects p ON p.id = d.project_id
        WHERE
          d.status NOT IN ('delivered', 'validated')
          AND (
            (
              COALESCE(d.expected_date, d.planned_date) IS NOT NULL
              AND COALESCE(d.expected_date, d.planned_date) <> ''
              AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
            )
            OR (d.blocker IS NOT NULL AND d.blocker <> '')
            OR d.quality_status = 'issue'
            OR (
              COALESCE(d.expected_date, d.planned_date) IS NOT NULL
              AND COALESCE(d.expected_date, d.planned_date) <> ''
              AND date(COALESCE(d.expected_date, d.planned_date)) = date('now')
            )
          )
        ORDER BY
          CASE
            WHEN d.blocker IS NOT NULL AND d.blocker <> '' THEN 1
            WHEN d.quality_status = 'issue' THEN 2
            WHEN COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                 AND COALESCE(d.expected_date, d.planned_date) <> ''
                 AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
            THEN 3
            ELSE 4
          END,
          days_late DESC,
          date(COALESCE(d.expected_date, d.planned_date)) ASC
        LIMIT 20
        """
    )
    deliveries_all = query_all(
        """
        SELECT
          d.id,
          s.id AS supplier_id,
          s.name AS supplier_name,
          d.title,
          COALESCE(d.expected_date, d.planned_date) AS expected_date,
          d.status,
          d.progress,
          d.blocker,
          d.quality_status,
          p.title AS project_title,
          CASE
            WHEN COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                 AND COALESCE(d.expected_date, d.planned_date) <> ''
                 AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
            THEN CAST(julianday('now') - julianday(COALESCE(d.expected_date, d.planned_date)) AS INT)
            ELSE 0
          END AS days_late
        FROM supplier_deliveries d
        JOIN suppliers s ON s.id = d.supplier_id
        LEFT JOIN projects p ON p.id = d.project_id
        ORDER BY
          CASE
            WHEN COALESCE(d.expected_date, d.planned_date) IS NULL OR COALESCE(d.expected_date, d.planned_date) = '' THEN 2
            WHEN date(COALESCE(d.expected_date, d.planned_date)) < date('now') THEN 0
            ELSE 1
          END,
          date(COALESCE(d.expected_date, d.planned_date)) ASC,
          d.created_at DESC
        LIMIT 100
        """
    )
    kpis = query_one(
        """
        SELECT
          SUM(CASE WHEN d.status NOT IN ('delivered','validated')
                    AND COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                    AND COALESCE(d.expected_date, d.planned_date) <> ''
                    AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
              THEN 1 ELSE 0 END) AS late_count,
          SUM(CASE WHEN d.status NOT IN ('delivered','validated') AND d.blocker IS NOT NULL AND d.blocker <> '' THEN 1 ELSE 0 END) AS blocked_count,
          SUM(CASE WHEN d.status NOT IN ('delivered','validated') AND d.quality_status = 'issue' THEN 1 ELSE 0 END) AS quality_issue_count,
          SUM(CASE WHEN d.status NOT IN ('delivered','validated') AND ((
                    COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                    AND COALESCE(d.expected_date, d.planned_date) <> ''
                    AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
                  ) OR (d.blocker IS NOT NULL AND d.blocker <> '') OR d.quality_status = 'issue')
              THEN COALESCE(d.amount, 0) ELSE 0 END) AS risk_value,
          SUM(CASE WHEN d.status IN ('delivered','validated') THEN 1 ELSE 0 END) AS delivered_total,
          SUM(CASE WHEN d.status IN ('delivered','validated')
                    AND COALESCE(d.expected_date, d.planned_date) IS NOT NULL
                    AND COALESCE(d.expected_date, d.planned_date) <> ''
                    AND d.delivered_date IS NOT NULL AND d.delivered_date <> ''
                    AND date(d.delivered_date) <= date(COALESCE(d.expected_date, d.planned_date))
              THEN 1 ELSE 0 END) AS delivered_ontime
        FROM supplier_deliveries d
        """
    )
    delivered_total = (kpis["delivered_total"] or 0) if kpis else 0
    delivered_ontime = (kpis["delivered_ontime"] or 0) if kpis else 0
    service_rate = int((delivered_ontime / delivered_total) * 100) if delivered_total else 100

    calendar_items = query_all(
        """
        SELECT
          d.id,
          d.title,
          d.reference_code,
          COALESCE(d.expected_date, d.planned_date) AS expected_date,
          d.status,
          d.progress,
          s.name AS supplier_name
        FROM supplier_deliveries d
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE COALESCE(d.expected_date, d.planned_date) IS NOT NULL
          AND COALESCE(d.expected_date, d.planned_date) <> ''
          AND date(COALESCE(d.expected_date, d.planned_date)) BETWEEN date('now', '-7 day') AND date('now', '+30 day')
        ORDER BY date(COALESCE(d.expected_date, d.planned_date)) ASC, d.created_at DESC
        """
    )

    return render_template(
        "suppliers.html",
        suppliers=suppliers,
        alerts=alerts,
        decision_items=decision_items,
        deliveries_all=deliveries_all,
        kpis=kpis,
        service_rate=service_rate,
        calendar_items=calendar_items,
        q=q,
        status=status,
        status_labels=_status_labels(),
    )


@suppliers_bp.route("/new", methods=["GET", "POST"])
@permission_required("suppliers.manage")
def create_supplier():
    if request.method == "POST":
        supplier_id = execute(
            """
            INSERT INTO suppliers(
              name, partner_type, contact_name, email, phone, service_category, sla_days, notes, is_active
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form.get("name"),
                request.form.get("partner_type", "fournisseur"),
                request.form.get("contact_name"),
                request.form.get("email"),
                request.form.get("phone"),
                request.form.get("service_category"),
                request.form.get("sla_days") or None,
                request.form.get("notes"),
                1 if request.form.get("is_active", "1") == "1" else 0,
            ),
        )
        log_action("create", "supplier", supplier_id, {"name": request.form.get("name")})
        flash("Fournisseur ajouté.", "success")
        return redirect(url_for("suppliers.list_suppliers"))
    return render_template("supplier_form.html", supplier=None, supplier_types=SUPPLIER_TYPES)


@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@permission_required("suppliers.manage")
def edit_supplier(supplier_id):
    supplier = query_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    if not supplier:
        flash("Fournisseur introuvable.", "danger")
        return redirect(url_for("suppliers.list_suppliers"))
    if request.method == "POST":
        execute(
            """
            UPDATE suppliers
            SET name = ?, partner_type = ?, contact_name = ?, email = ?, phone = ?,
                service_category = ?, sla_days = ?, notes = ?, is_active = ?
            WHERE id = ?
            """,
            (
                request.form.get("name"),
                request.form.get("partner_type", "fournisseur"),
                request.form.get("contact_name"),
                request.form.get("email"),
                request.form.get("phone"),
                request.form.get("service_category"),
                request.form.get("sla_days") or None,
                request.form.get("notes"),
                1 if request.form.get("is_active", "1") == "1" else 0,
                supplier_id,
            ),
        )
        log_action("update", "supplier", supplier_id, {"name": request.form.get("name")})
        flash("Fournisseur mis à jour.", "success")
        return redirect(url_for("suppliers.supplier_detail", supplier_id=supplier_id))
    return render_template("supplier_form.html", supplier=supplier, supplier_types=SUPPLIER_TYPES)


@suppliers_bp.route("/<int:supplier_id>")
@permission_required("suppliers.view")
def supplier_detail(supplier_id):
    supplier = query_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    if not supplier:
        flash("Fournisseur introuvable.", "danger")
        return redirect(url_for("suppliers.list_suppliers"))
    deliveries = query_all(
        """
        SELECT d.*, p.title AS project_title
        FROM supplier_deliveries d
        LEFT JOIN projects p ON p.id = d.project_id
        WHERE d.supplier_id = ?
        ORDER BY date(COALESCE(d.expected_date, d.planned_date)) ASC, d.created_at DESC
        """,
        (supplier_id,),
    )
    timeline = query_all(
        """
        SELECT
          d.id,
          d.title,
          d.reference_code,
          d.status,
          d.progress,
          COALESCE(d.expected_date, d.planned_date) AS expected_date,
          d.delivered_date,
          d.blocker,
          d.quality_status,
          d.created_at,
          CASE
            WHEN d.status IN ('delivered','validated')
                 AND d.delivered_date IS NOT NULL AND d.delivered_date <> ''
                 AND COALESCE(d.expected_date, d.planned_date) IS NOT NULL AND COALESCE(d.expected_date, d.planned_date) <> ''
            THEN CAST(julianday(d.delivered_date) - julianday(COALESCE(d.expected_date, d.planned_date)) AS INT)
            WHEN d.status NOT IN ('delivered','validated')
                 AND COALESCE(d.expected_date, d.planned_date) IS NOT NULL AND COALESCE(d.expected_date, d.planned_date) <> ''
                 AND date(COALESCE(d.expected_date, d.planned_date)) < date('now')
            THEN CAST(julianday('now') - julianday(COALESCE(d.expected_date, d.planned_date)) AS INT)
            ELSE 0
          END AS delay_days
        FROM supplier_deliveries d
        WHERE d.supplier_id = ?
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT 30
        """,
        (supplier_id,),
    )
    projects = query_all("SELECT id, title FROM projects ORDER BY title ASC")
    return render_template(
        "supplier_detail.html",
        supplier=supplier,
        deliveries=deliveries,
        timeline=timeline,
        projects=projects,
        status_choices=DELIVERY_STATUS,
        quality_choices=QUALITY_CHOICES,
        status_labels=_status_labels(),
        quality_labels=_quality_labels(),
        today_date=date.today().isoformat(),
    )


@suppliers_bp.route("/<int:supplier_id>/deliveries/add", methods=["POST"])
@permission_required("suppliers.manage")
def add_delivery(supplier_id):
    supplier = query_one("SELECT id FROM suppliers WHERE id = ?", (supplier_id,))
    if not supplier:
        flash("Fournisseur introuvable.", "danger")
        return redirect(url_for("suppliers.list_suppliers"))
    status = _safe_status(request.form.get("status", "planned"))
    progress = PROGRESS_BY_STATUS.get(status, 10)
    planned_date = date.today().isoformat()
    execute(
        """
        INSERT INTO supplier_deliveries(
          supplier_id, project_id, reference_code, title, planned_date, expected_date,
          delivered_date, status, progress, amount, currency, quality_status, blocker, next_step
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            supplier_id,
            request.form.get("project_id") or None,
            None,
            request.form.get("title"),
            planned_date,
            planned_date,
            request.form.get("delivered_date"),
            status,
            progress,
            request.form.get("amount") or None,
            request.form.get("currency") or "USD",
            _safe_quality(request.form.get("quality_status", "ok")),
            request.form.get("blocker"),
            request.form.get("next_step"),
        ),
    )
    log_action("create", "supplier_delivery", supplier_id, {"title": request.form.get("title"), "status": status})
    flash("Livraison ajoutée.", "success")
    return redirect(url_for("suppliers.supplier_detail", supplier_id=supplier_id))


@suppliers_bp.route("/deliveries/<int:delivery_id>/status", methods=["POST"])
@permission_required("suppliers.manage")
def update_delivery_status(delivery_id):
    delivery = query_one("SELECT id, supplier_id FROM supplier_deliveries WHERE id = ?", (delivery_id,))
    if not delivery:
        flash("Livraison introuvable.", "danger")
        return redirect(url_for("suppliers.list_suppliers"))
    status = _safe_status(request.form.get("status", "planned"))
    progress = PROGRESS_BY_STATUS.get(status, 10)
    quality = _safe_quality(request.form.get("quality_status", "ok"))
    execute(
        """
        UPDATE supplier_deliveries
        SET status = ?, progress = ?, quality_status = ?, blocker = ?, next_step = ?, delivered_date = ?
        WHERE id = ?
        """,
        (
            status,
            progress,
            quality,
            request.form.get("blocker"),
            request.form.get("next_step"),
            request.form.get("delivered_date"),
            delivery_id,
        ),
    )
    log_action("update", "supplier_delivery", delivery_id, {"status": status})
    flash("Statut de livraison mis à jour.", "success")
    return redirect(url_for("suppliers.supplier_detail", supplier_id=delivery["supplier_id"]))


@suppliers_bp.route("/<int:supplier_id>/delete", methods=["POST"])
@permission_required("suppliers.delete")
def delete_supplier(supplier_id):
    execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    log_action("delete", "supplier", supplier_id)
    flash("Fournisseur supprimé.", "info")
    return redirect(url_for("suppliers.list_suppliers"))
