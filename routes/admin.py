from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from models.repositories import execute, query_all, query_one
from routes.audit import log_action
from routes.utils import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ALLOWED_ROLES = {"admin", "manager", "sales", "technicien", "administration"}


@admin_bp.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "sales")
        if not username or not email or not password:
            flash("Veuillez remplir tous les champs.", "danger")
            return redirect(url_for("admin.users"))
        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
            return redirect(url_for("admin.users"))
        if role not in ALLOWED_ROLES:
            role = "sales"
        try:
            user_id = execute(
                """
                INSERT INTO users(username, email, password, role, is_active)
                VALUES(?, ?, ?, ?, 1)
                """,
                (username, email, generate_password_hash(password), role),
            )
            log_action("create", "user", user_id, {"username": username, "role": role})
            flash("Utilisateur créé.", "success")
        except Exception:
            flash("Nom d'utilisateur ou e-mail déjà utilisé.", "danger")
        return redirect(url_for("admin.users"))

    users_list = query_all(
        "SELECT id, username, email, role, is_active FROM users ORDER BY id ASC"
    )
    return render_template("admin_users.html", users=users_list)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    row = query_one("SELECT is_active, username FROM users WHERE id = ?", (user_id,))
    if not row:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))
    if session.get("user_id") == user_id:
        flash("Vous ne pouvez pas désactiver votre propre compte.", "warning")
        return redirect(url_for("admin.users"))
    role_row = query_one("SELECT role FROM users WHERE id = ?", (user_id,))
    if role_row and role_row["role"] == "admin" and row["is_active"] == 1:
        active_admins = query_one(
            "SELECT COUNT(*) AS total FROM users WHERE role = 'admin' AND is_active = 1"
        )["total"]
        if active_admins <= 1:
            flash("Impossible de désactiver le dernier administrateur actif.", "danger")
            return redirect(url_for("admin.users"))
    execute(
        "UPDATE users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (user_id,),
    )
    log_action("toggle_active", "user", user_id, {"username": row["username"]})
    flash("Statut utilisateur mis à jour.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def update_role(user_id):
    target = query_one("SELECT id, role FROM users WHERE id = ?", (user_id,))
    if not target:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))
    role = request.form.get("role", "sales")
    if role not in ALLOWED_ROLES:
        role = "sales"
    if session.get("user_id") == user_id and role != "admin":
        flash("Vous ne pouvez pas retirer votre propre rôle administrateur.", "warning")
        return redirect(url_for("admin.users"))
    if target["role"] == "admin" and role != "admin":
        admins_total = query_one("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")[
            "total"
        ]
        if admins_total <= 1:
            flash("Impossible de rétrograder le dernier administrateur.", "danger")
            return redirect(url_for("admin.users"))
    execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    log_action("change_role", "user", user_id, {"new_role": role})
    flash("Rôle utilisateur mis à jour.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def update_user(user_id):
    target = query_one("SELECT id FROM users WHERE id = ?", (user_id,))
    if not target:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    if not username or not email:
        flash("Nom d'utilisateur et e-mail requis.", "danger")
        return redirect(url_for("admin.users"))
    try:
        execute("UPDATE users SET username = ?, email = ? WHERE id = ?", (username, email, user_id))
        log_action("update_profile", "user", user_id, {"username": username, "email": email})
        flash("Profil utilisateur mis à jour.", "success")
    except Exception:
        flash("Nom d'utilisateur ou e-mail déjà utilisé.", "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/password", methods=["POST"])
@admin_required
def reset_password(user_id):
    target = query_one("SELECT id FROM users WHERE id = ?", (user_id,))
    if not target:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))
    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 6:
        flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
        return redirect(url_for("admin.users"))
    execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    log_action("reset_password", "user", user_id)
    flash("Mot de passe utilisateur mis à jour.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/update", methods=["POST"])
@admin_required
def update_user_full(user_id):
    target = query_one("SELECT id, role FROM users WHERE id = ?", (user_id,))
    if not target:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "sales")
    is_active = 1 if request.form.get("is_active") == "1" else 0
    new_password = request.form.get("new_password", "").strip()

    if not username or not email:
        flash("Nom d'utilisateur et e-mail requis.", "danger")
        return redirect(url_for("admin.users"))
    if role not in ALLOWED_ROLES:
        role = "sales"

    if session.get("user_id") == user_id and role != "admin":
        flash("Vous ne pouvez pas retirer votre propre rôle administrateur.", "warning")
        return redirect(url_for("admin.users"))
    if session.get("user_id") == user_id and is_active == 0:
        flash("Vous ne pouvez pas désactiver votre propre compte.", "warning")
        return redirect(url_for("admin.users"))

    if target["role"] == "admin" and role != "admin":
        admins_total = query_one("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")["total"]
        if admins_total <= 1:
            flash("Impossible de rétrograder le dernier administrateur.", "danger")
            return redirect(url_for("admin.users"))
    if target["role"] == "admin" and is_active == 0:
        active_admins = query_one(
            "SELECT COUNT(*) AS total FROM users WHERE role = 'admin' AND is_active = 1"
        )["total"]
        if active_admins <= 1:
            flash("Impossible de désactiver le dernier administrateur actif.", "danger")
            return redirect(url_for("admin.users"))

    try:
        execute(
            "UPDATE users SET username = ?, email = ?, role = ?, is_active = ? WHERE id = ?",
            (username, email, role, is_active, user_id),
        )
        if new_password:
            if len(new_password) < 6:
                flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
                return redirect(url_for("admin.users"))
            execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (generate_password_hash(new_password), user_id),
            )
            log_action("reset_password", "user", user_id)
        log_action(
            "update_full",
            "user",
            user_id,
            {"username": username, "email": email, "role": role, "is_active": is_active},
        )
        flash("Utilisateur mis à jour.", "success")
    except Exception:
        flash("Nom d'utilisateur ou e-mail déjà utilisé.", "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    target = query_one("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
    if not target:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))
    if session.get("user_id") == user_id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "warning")
        return redirect(url_for("admin.users"))
    if target["role"] == "admin":
        admins_total = query_one("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")[
            "total"
        ]
        if admins_total <= 1:
            flash("Impossible de supprimer le dernier administrateur.", "danger")
            return redirect(url_for("admin.users"))
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    log_action("delete", "user", user_id, {"username": target["username"]})
    flash("Utilisateur supprimé.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/audit")
@admin_required
def audit():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 30
    total = query_one("SELECT COUNT(*) AS total FROM audit_logs")["total"]
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    rows = query_all(
        """
        SELECT id, username, action, entity_type, entity_id, details, ip_address, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """
        ,
        (per_page, offset),
    )
    return render_template("admin_audit.html", rows=rows, page=page, total_pages=total_pages)
