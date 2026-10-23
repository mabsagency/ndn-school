import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, send_from_directory
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def normalize_database_url(database_url, instance_path):
    url = make_url(database_url)
    if url.drivername in ("postgres", "postgresql", "postgresql+psycopg2"):
        url = url.set(drivername="postgresql+psycopg")
        if url.host and "supabase" in url.host and "sslmode" not in url.query:
            url = url.update_query_dict({"sslmode": "require"})
        return url

    if url.drivername == "sqlite" and url.database not in (None, "", ":memory:"):
        database = Path(url.database)
        if not database.is_absolute():
            database = Path(instance_path) / database
        return URL.create("sqlite", database=str(database))
    return url


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    database_url = os.environ.get("DATABASE_URL")
    prototype_mode = bool(os.environ.get("VERCEL") and not database_url)
    if not database_url:
        if prototype_mode:
            database_url = "sqlite:////tmp/ndn-school-prototype.db"
        else:
            database_url = f"sqlite:///{Path(app.instance_path) / 'ndn_school.db'}"
    database_url = normalize_database_url(database_url, app.instance_path)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key and os.environ.get("VERCEL") and not prototype_mode:
        raise RuntimeError("SECRET_KEY doit être configurée dans les variables d’environnement Vercel.")
    is_vercel = bool(os.environ.get("VERCEL"))
    engine_options = {"pool_pre_ping": True}
    if database_url.drivername.startswith("postgresql"):
        engine_options["connect_args"] = {"prepare_threshold": None}
        if is_vercel:
            engine_options["poolclass"] = NullPool
    app.config.update(
        SECRET_KEY=secret_key or (
            "ndn-school-prototype-only-do-not-use-with-real-data"
            if prototype_mode else secrets.token_hex(32)
        ),
        SQLALCHEMY_DATABASE_URI=database_url.render_as_string(hide_password=False),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        PROTOTYPE_MODE=prototype_mode,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_vercel or os.environ.get("COOKIE_SECURE", "0") == "1",
        WTF_CSRF_TIME_LIMIT=None,
        PERSISTENT_UPLOADS=not is_vercel,
    )
    if test_config:
        app.config.update(test_config)

    if not is_vercel:
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

    @app.get("/health")
    def health():
        try:
            db.session.execute(db.select(1))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Health check failed because the database is unavailable.")
            return {"status": "unavailable"}, 503
        return "", 204

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

    @app.cli.command("create-admin")
    def create_admin():
        """Interactively create the first production administrator."""
        import click

        from app.models import User

        if User.query.filter_by(role="admin", active=True).first():
            raise click.ClickException("Un administrateur actif existe déjà.")
        username = click.prompt("Identifiant administrateur").strip()
        email = click.prompt("Adresse électronique").strip().lower()
        first_name = click.prompt("Prénom").strip()
        last_name = click.prompt("Nom").strip()
        password = click.prompt(
            "Mot de passe (12 caractères minimum)", hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 12:
            raise click.ClickException("Le mot de passe doit contenir au moins 12 caractères.")
        if User.query.filter(
            db.or_(User.username == username, db.func.lower(User.email) == email)
        ).first():
            raise click.ClickException("Cet identifiant ou cette adresse électronique existe déjà.")
        user = User(
            username=username, email=email, first_name=first_name,
            last_name=last_name, role="admin", active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo("Compte administrateur créé.")

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
