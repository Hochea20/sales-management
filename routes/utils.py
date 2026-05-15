from functools import wraps



from flask import flash, redirect, session, url_for



ROLE_PERMISSIONS = {

    "sales": {

        "dashboard.view",

        "clients.view",

        "clients.manage",

        "appointments.view",

        "appointments.manage",
        "appointments.delete",

        "followups.view",

        "followups.manage",

        "pipeline.view",

        "pipeline.manage",

        "projects.view",

        "projects.manage",
        "projects.delete",

        "suppliers.view",

        "suppliers.manage",
        "suppliers.delete",

    },

    "manager": {

        "dashboard.view",

        "clients.view",

        "clients.manage",

        "clients.delete",

        "appointments.view",

        "appointments.manage",

        "appointments.delete",

        "followups.view",

        "followups.manage",

        "followups.delete",

        "pipeline.view",

        "pipeline.manage",

        "projects.view",

        "projects.manage",

        "projects.delete",

        "suppliers.view",

        "suppliers.manage",

        "suppliers.delete",

        "exports.view",

    },

    "technicien": {
        "dashboard.view",
        "projects.view",
        "projects.manage",
        "suppliers.view",
    },

    "administration": {
        "dashboard.view",
        "projects.view",
        "projects.manage",
        "suppliers.view",
        "suppliers.manage",
    },

    "admin": {"*"},

}





def has_permission(permission: str) -> bool:

    role = session.get("role", "sales")

    permissions = ROLE_PERMISSIONS.get(role, set())

    return "*" in permissions or permission in permissions





def login_required(view_func):

    @wraps(view_func)

    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            return redirect(url_for("auth.login"))

        return view_func(*args, **kwargs)



    return wrapper





def admin_required(view_func):

    @wraps(view_func)

    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            return redirect(url_for("auth.login"))

        if session.get("role") != "admin":

            flash("Accès réservé à l'administrateur.", "warning")

            return redirect(url_for("dashboard.home"))

        return view_func(*args, **kwargs)



    return wrapper





def permission_required(permission: str):

    def decorator(view_func):

        @wraps(view_func)

        def wrapper(*args, **kwargs):

            if "user_id" not in session:

                return redirect(url_for("auth.login"))

            if not has_permission(permission):

                flash("Action non autorisée pour votre rôle.", "warning")

                return redirect(url_for("dashboard.home"))

            return view_func(*args, **kwargs)



        return wrapper



    return decorator

