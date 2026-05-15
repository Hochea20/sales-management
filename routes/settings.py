from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.repositories import execute, query_all
from routes.audit import log_action
from routes.utils import admin_required

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def upsert_setting(key: str, value: str) -> None:
    execute(
        """
        INSERT INTO app_settings(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


@settings_bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    if request.method == "POST":
        app_name = request.form.get("app_name", "Sales Manager").strip() or "Sales Manager"
        default_theme = request.form.get("default_theme", "light")
        if default_theme not in {"light", "dark"}:
            default_theme = "light"

        items_per_page = request.form.get("items_per_page", "10").strip()
        if not items_per_page.isdigit():
            items_per_page = "10"

        monthly_goal = request.form.get("monthly_goal", "40").strip()
        if not monthly_goal.isdigit():
            monthly_goal = "40"

        widget_limit = request.form.get("actions_widget_limit", "6").strip()
        if not widget_limit.isdigit():
            widget_limit = "6"
        sales_contact_email = request.form.get("sales_contact_email", "sales@ishango-it.com").strip() or "sales@ishango-it.com"

        report_author_name = request.form.get("report_author_name", "").strip() or "Josué Mbuyu wa Kabinga"
        report_author_email = request.form.get("report_author_email", "").strip() or "josue.mbuyu@ishango-it.com"
        report_author_title = request.form.get("report_author_title", "").strip() or "Technical sales"

        upsert_setting("app_name", app_name)
        upsert_setting("default_theme", default_theme)
        upsert_setting("items_per_page", items_per_page)
        upsert_setting("monthly_goal", monthly_goal)
        upsert_setting("actions_widget_limit", widget_limit)
        upsert_setting("sales_contact_email", sales_contact_email)
        upsert_setting("report_author_name", report_author_name)
        upsert_setting("report_author_email", report_author_email)
        upsert_setting("report_author_title", report_author_title)

        log_action(
            "update",
            "settings",
            "app_settings",
            {
                "app_name": app_name,
                "default_theme": default_theme,
                "items_per_page": items_per_page,
                "monthly_goal": monthly_goal,
                "actions_widget_limit": widget_limit,
                "sales_contact_email": sales_contact_email,
                "report_author_name": report_author_name,
                "report_author_email": report_author_email,
                "report_author_title": report_author_title,
            },
        )
        flash("Paramètres mis à jour.", "success")
        return redirect(url_for("settings.index"))

    rows = query_all("SELECT key, value FROM app_settings")
    settings_map = {row["key"]: row["value"] for row in rows}
    return render_template("settings.html", settings=settings_map)
