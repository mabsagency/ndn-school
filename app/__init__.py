import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, send_from_directory
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    database_url = os.environ.get(
        "DATABASE_URL", "sqlite:///" + str(Path(app.instance_path) / "ndn_school.db")
    )
    if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:////"):
        database_url = "sqlite:///" + str(Path(app.instance_path) / database_url.removeprefix("sqlite:///"))
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        WTF_CSRF_TIME_LIMIT=None,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Connectez-vous pour accéder à cet espace."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)

    from app import models
    from app.routes import auth, school

    app.register_blueprint(auth.bp)
    app.register_blueprint(school.bp)

    @app.after_request
    def protect_dynamic_responses(response):
        if not request.path.startswith("/static/") and request.path != "/service-worker.js":
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/service-worker.js")
    def service_worker():
        response = send_from_directory(
            Path(app.static_folder) / "js",
            "service-worker.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.cli.command("init-db")
    def init_db():
        """Create the database schema and load fictional demonstration data."""
        from app.seed import seed_demo_data

        db.create_all()
        seed_demo_data()
        print("Base NDN créée et données de démonstration chargées.")

    @app.cli.command("backup-db")
    def backup_db():
        """Create a consistent SQLite backup in the instance folder."""
        import sqlite3
        from datetime import datetime

        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        if not uri.startswith("sqlite:///"):
            raise RuntimeError("Cette commande de sauvegarde est réservée à SQLite.")
        source = Path(uri.removeprefix("sqlite:///"))
        if not source.is_absolute():
            source = Path(app.instance_path) / source
        if not source.exists():
            raise RuntimeError("La base de données n'existe pas encore.")
        destination = Path(app.instance_path) / (
            "ndn-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db"
        )
        with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        print(f"Sauvegarde créée : {destination}")

    return app
