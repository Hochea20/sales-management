import os
from flask import Flask

from models.db import close_db, init_db
from models.repositories import query_one
from routes.admin import admin_bp
from routes.appointments import appointments_bp
from routes.auth import auth_bp
from routes.clients import clients_bp
from routes.dashboard import dashboard_bp
from routes.exports import exports_bp
from routes.followups import followups_bp
from routes.pipeline import pipeline_bp
from routes.projects import projects_bp
from routes.search import search_bp
from routes.settings import settings_bp
from routes.suppliers import suppliers_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-insecure-key-change-me")
    templates_reload = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    app.config["TEMPLATES_AUTO_RELOAD"] = templates_reload
    app.jinja_env.auto_reload = templates_reload

    # Initialize database schema and seed default user.
    init_db()
    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(followups_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(exports_bp)

    @app.context_processor
    def inject_global_settings():
        app_name = "Sales Manager"
        default_theme = "light"
        row = query_one("SELECT value FROM app_settings WHERE key = 'app_name'")
        if row:
            app_name = row["value"]
        row_theme = query_one("SELECT value FROM app_settings WHERE key = 'default_theme'")
        if row_theme and row_theme["value"] in {"light", "dark"}:
            default_theme = row_theme["value"]
        return {"app_name": app_name, "default_theme": default_theme}

    return app


if __name__ == "__main__":
    application = create_app()
    debug_mode = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    application.run(debug=debug_mode)
