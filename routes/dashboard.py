from datetime import date

from flask import Blueprint, redirect, render_template, request, session, url_for



from models.repositories import query_all, query_one

from routes.utils import permission_required



dashboard_bp = Blueprint("dashboard", __name__)





def _int_setting(key: str, default: int) -> int:

    row = query_one("SELECT value FROM app_settings WHERE key = ?", (key,))

    if row and str(row["value"]).isdigit():

        return int(row["value"])

    return default





@dashboard_bp.route("/")

@permission_required("dashboard.view")

def home():

    monthly_goal = _int_setting("monthly_goal", 40)
    only_unread = request.args.get("only_unread", "0") == "1"

    actions_limit = _int_setting("actions_widget_limit", 6)



    stats = query_one(

        """

        SELECT

          (SELECT COUNT(*) FROM clients) AS total_clients,

          (SELECT COUNT(*) FROM appointments) AS total_appointments,
          (SELECT COUNT(*) FROM appointments WHERE status = 'pending') AS pending_appointments,
          (SELECT COUNT(*) FROM appointments WHERE status = 'pending' AND datetime(date || ' ' || time) < datetime('now', 'localtime')) AS overdue_appointments,

          (SELECT COUNT(*) FROM tracking_items WHERE status = 'pending') AS pending_followups,

          (SELECT COUNT(*) FROM appointments WHERE status = 'done') AS done_appointments,

          (SELECT COUNT(*) FROM appointments WHERE date(date) = date('now')) AS today_appointments,
          (SELECT COUNT(*) FROM tracking_items WHERE status = 'pending' AND due_date IS NOT NULL AND due_date <> '' AND date(due_date) < date('now')) AS overdue_followups_count,
          (SELECT COUNT(*) FROM projects) AS total_projects,
          (SELECT COUNT(*) FROM projects WHERE status = 'en_attente') AS pending_projects,
          (SELECT COUNT(*) FROM projects WHERE status = 'en_cours') AS active_projects,
          (SELECT COUNT(*) FROM projects WHERE due_date IS NOT NULL AND due_date <> '' AND date(due_date) < date('now') AND progress < 100) AS late_projects,
          (SELECT COUNT(DISTINCT pu.project_id)
             FROM project_updates pu
             JOIN projects p ON p.id = pu.project_id
            WHERE pu.is_blocked = 1
              AND date(pu.created_at) >= date('now', '-30 day')) AS blocked_projects

        """

    )

    monthly = query_one(

        """

        SELECT

          (SELECT COUNT(*) FROM appointments

           WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')) AS month_appointments,

          (SELECT COUNT(*) FROM appointments

           WHERE status = 'done' AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')) AS month_done

        """

    )

    month_done = monthly["month_done"] or 0

    goal_progress = int((month_done / monthly_goal) * 100) if monthly_goal else 0

    goal_progress = min(goal_progress, 100)



    upcoming = query_all(

        """

        SELECT a.id, a.date, a.time, a.location, a.status, c.name AS client_name

        FROM appointments a

        JOIN clients c ON c.id = a.client_id

        WHERE a.status = 'pending'

        ORDER BY a.date ASC, a.time ASC

        LIMIT 8

        """

    )

    overdue_followups = query_all(

        """

        SELECT f.id, f.title, f.due_date, COALESCE(f.context_label, '-') AS client_name
        FROM tracking_items f
        WHERE f.status = 'pending'
          AND f.due_date IS NOT NULL
          AND f.due_date <> ''
          AND date(f.due_date) < date('now')
        ORDER BY date(f.due_date) ASC

        """

    )

    imminent_appointments = query_all(
        """
        SELECT a.id, a.date, a.time, c.name AS client_name, a.location
        FROM appointments a
        JOIN clients c ON c.id = a.client_id
        WHERE a.status = 'pending'
          AND datetime(a.date || ' ' || a.time) BETWEEN datetime('now', 'localtime')
          AND datetime('now', 'localtime', '+1 hour')
        ORDER BY a.date ASC, a.time ASC
        LIMIT 5
        """
    )

    pipeline_summary = query_all(

        """

        SELECT pipeline_stage, COUNT(*) AS total

        FROM clients

        GROUP BY pipeline_stage

        ORDER BY total DESC

        """

    )

    recent_clients = query_all(

        """

        SELECT id, name, company, pipeline_stage, created_at

        FROM clients

        ORDER BY created_at DESC

        LIMIT 6

        """

    )



    actions_today = query_all(

        """

        SELECT 'rdv_today' AS kind, c.name AS client_name, a.time AS item_time, a.location AS subtitle

        FROM appointments a

        JOIN clients c ON c.id = a.client_id

        WHERE date(a.date) = date('now')

        UNION ALL

        SELECT 'followup_overdue' AS kind, COALESCE(f.context_label, '-') AS client_name, '' AS item_time, f.title AS subtitle
        FROM tracking_items f
        WHERE f.status = 'pending'
          AND f.due_date IS NOT NULL
          AND f.due_date <> ''
          AND date(f.due_date) < date('now')

        LIMIT ?

        """,

        (actions_limit,),

    )

    project_kpis = query_one(
        """
        SELECT
          (SELECT COUNT(*) FROM projects) AS total_projects,
          (SELECT COUNT(*) FROM projects WHERE status = 'en_cours') AS active_projects,
          (SELECT COUNT(*) FROM projects WHERE due_date IS NOT NULL AND due_date <> '' AND date(due_date) < date('now') AND progress < 100) AS late_projects,
          (SELECT COUNT(DISTINCT pu.project_id)
             FROM project_updates pu
             JOIN projects p ON p.id = pu.project_id
            WHERE pu.is_blocked = 1
              AND date(pu.created_at) >= date('now', '-30 day')) AS blocked_projects
        """
    )
    weekly_project_actions = query_all(
        """
        SELECT
          p.id AS project_id,
          p.title AS project_title,
          '' AS summary,
          p.next_action,
          p.due_date AS next_action_date,
          COALESCE(
            (
              SELECT pu.risk_level
              FROM project_updates pu
              WHERE pu.project_id = p.id
              ORDER BY pu.created_at DESC, pu.id DESC
              LIMIT 1
            ),
            'moyen'
          ) AS risk_level,
          COALESCE(
            (
              SELECT pu.is_blocked
              FROM project_updates pu
              WHERE pu.project_id = p.id
              ORDER BY pu.created_at DESC, pu.id DESC
              LIMIT 1
            ),
            0
          ) AS is_blocked,
          p.created_at
        FROM projects p
        WHERE p.next_action IS NOT NULL
          AND p.next_action <> ''
          AND p.due_date IS NOT NULL
          AND p.due_date <> ''
          AND date(p.due_date) BETWEEN date('now') AND date('now', '+7 day')
        ORDER BY date(p.due_date) ASC, p.created_at DESC
        LIMIT 8
        """
    )
    recent_project_updates = query_all(
        """
        SELECT
          pu.project_id,
          p.title AS project_title,
          pu.summary,
          pu.risk_level,
          pu.is_blocked,
          pu.created_at
        FROM project_updates pu
        JOIN projects p ON p.id = pu.project_id
        ORDER BY pu.created_at DESC, pu.id DESC
        LIMIT 8
        """
    )
    supplier_kpis = query_one(
        """
        SELECT
          SUM(CASE WHEN d.status NOT IN ('delivered', 'validated')
                    AND d.expected_date IS NOT NULL AND d.expected_date <> ''
                    AND date(d.expected_date) < date('now')
              THEN 1 ELSE 0 END) AS late_count,
          SUM(CASE WHEN d.status NOT IN ('delivered', 'validated')
                    AND d.blocker IS NOT NULL AND d.blocker <> ''
              THEN 1 ELSE 0 END) AS blocked_count,
          SUM(CASE WHEN d.status NOT IN ('delivered', 'validated') AND d.quality_status = 'issue'
              THEN 1 ELSE 0 END) AS quality_issue_count,
          SUM(CASE WHEN d.status NOT IN ('delivered', 'validated')
                    AND (
                      (d.expected_date IS NOT NULL AND d.expected_date <> '' AND date(d.expected_date) < date('now'))
                      OR (d.blocker IS NOT NULL AND d.blocker <> '')
                      OR d.quality_status = 'issue'
                    )
              THEN COALESCE(d.amount, 0) ELSE 0 END) AS risk_value,
          SUM(CASE WHEN d.status IN ('delivered', 'validated') THEN 1 ELSE 0 END) AS delivered_total,
          SUM(CASE WHEN d.status IN ('delivered', 'validated')
                    AND d.expected_date IS NOT NULL AND d.expected_date <> ''
                    AND d.delivered_date IS NOT NULL AND d.delivered_date <> ''
                    AND date(d.delivered_date) <= date(d.expected_date)
              THEN 1 ELSE 0 END) AS delivered_ontime
        FROM supplier_deliveries d
        """
    )
    supplier_decisions = query_all(
        """
        SELECT
          d.supplier_id,
          s.name AS supplier_name,
          d.title,
          d.expected_date,
          d.amount,
          d.currency,
          d.blocker,
          CASE
            WHEN d.blocker IS NOT NULL AND d.blocker <> '' THEN 'Escalader'
            WHEN d.quality_status = 'issue' THEN 'Incident qualité'
            WHEN d.expected_date IS NOT NULL AND d.expected_date <> '' AND date(d.expected_date) < date('now') THEN 'Relancer'
            ELSE 'Suivi'
          END AS action_recommandee
        FROM supplier_deliveries d
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE d.status NOT IN ('delivered', 'validated')
          AND (
            (d.expected_date IS NOT NULL AND d.expected_date <> '' AND date(d.expected_date) <= date('now'))
            OR (d.blocker IS NOT NULL AND d.blocker <> '')
            OR d.quality_status = 'issue'
          )
        ORDER BY
          CASE
            WHEN d.blocker IS NOT NULL AND d.blocker <> '' THEN 1
            WHEN d.quality_status = 'issue' THEN 2
            ELSE 3
          END,
          date(d.expected_date) ASC
        LIMIT 5
        """
    )
    delivered_total_supplier = (supplier_kpis["delivered_total"] or 0) if supplier_kpis else 0
    delivered_ontime_supplier = (supplier_kpis["delivered_ontime"] or 0) if supplier_kpis else 0
    supplier_service_rate = (
        int((delivered_ontime_supplier / delivered_total_supplier) * 100) if delivered_total_supplier else 100
    )

    today_key = date.today().isoformat()
    seen_notifications = set(session.get("seen_notifications", []))
    notifications = []
    if imminent_appointments:
        notif_key = f"imminent:{today_key}"
        notifications.append(
            {
                "key": notif_key,
                "level": "warning",
                "priority": "Élevée",
                "title": "Rendez-vous imminent(s)",
                "message": f"{len(imminent_appointments)} rendez-vous dans l'heure à venir.",
                "seen": notif_key in seen_notifications,
            }
        )
    if overdue_followups:
        notif_key = f"overdue:{today_key}"
        notifications.append(
            {
                "key": notif_key,
                "level": "danger",
                "priority": "Critique",
                "title": "Suivi(s) en retard",
                "message": f"{len(overdue_followups)} suivi(s) nécessitent une action immédiate.",
                "seen": notif_key in seen_notifications,
            }
        )

    if only_unread:
        notifications = [n for n in notifications if not n.get("seen")]

    return render_template(

        "dashboard.html",

        stats=stats,

        monthly=monthly,

        monthly_goal=monthly_goal,

        goal_progress=goal_progress,

        upcoming=upcoming,

        overdue_followups=overdue_followups,

        pipeline_summary=pipeline_summary,

        recent_clients=recent_clients,

        actions_today=actions_today,

        notifications=notifications,
        only_unread=only_unread,

        imminent_appointments=imminent_appointments,
        project_kpis=project_kpis,
        weekly_project_actions=weekly_project_actions,
        recent_project_updates=recent_project_updates,
        supplier_kpis=supplier_kpis,
        supplier_decisions=supplier_decisions,
        supplier_service_rate=supplier_service_rate,

    )


@dashboard_bp.route("/notifications/seen", methods=["POST"])
@permission_required("dashboard.view")
def mark_notification_seen():
    notif_key = request.form.get("notif_key", "").strip()
    if notif_key:
        seen = set(session.get("seen_notifications", []))
        seen.add(notif_key)
        session["seen_notifications"] = sorted(seen)
    return redirect(url_for("dashboard.home"))

