from flask import Blueprint, flash, redirect, render_template, request, session, url_for







from werkzeug.security import check_password_hash















from models.repositories import query_one

from routes.audit import log_action















auth_bp = Blueprint("auth", __name__, url_prefix="/auth")























@auth_bp.route("/login", methods=["GET", "POST"])







def login():







    if session.get("user_id"):







        return redirect(url_for("dashboard.home"))















    if request.method == "POST":







        identifier = request.form.get("identifier", "").strip()







        password = request.form.get("password", "").strip()







        user = query_one(







            """







            SELECT id, username, email, password, role







            FROM users







            WHERE (lower(username) = lower(?) OR lower(email) = lower(?))



              AND is_active = 1







            """,







            (identifier, identifier),







        )







        if user and check_password_hash(user["password"], password):







            session["user_id"] = user["id"]







            session["username"] = user["username"]







            session["role"] = user["role"]







            session["email"] = user["email"]







            log_action("login", "session", user["id"], {"identifier": identifier})

            flash("Connexion réussie.", "success")







            return redirect(url_for("dashboard.home"))







        flash("Identifiants invalides.", "danger")















    return render_template("login.html")























@auth_bp.route("/logout")







def logout():







    session.clear()







    flash("Vous êtes déconnecté.", "info")







    return redirect(url_for("auth.login"))







