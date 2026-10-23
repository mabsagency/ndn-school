from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app import db
from app.models import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    offline_sync = request.headers.get("X-NDN-Offline-Sync") == "1"
    if current_user.is_authenticated and not offline_sync:
        return redirect(url_for("school.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            db.or_(User.username == username, db.func.lower(User.email) == username.lower()),
            User.active.is_(True),
        ).first()
        if user and user.check_password(password):
            login_user(user, remember=False)
            if offline_sync:
                return jsonify(authenticated=True, username=user.username)
            return redirect(url_for("school.dashboard"))
        if offline_sync:
            return jsonify(authenticated=False, message="Identifiant ou mot de passe incorrect."), 401
        flash("Identifiant ou mot de passe incorrect.", "danger")
    return render_template("login.html")


@bp.post("/logout")
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("auth.login"))
