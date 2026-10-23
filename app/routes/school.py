from datetime import date, datetime
from functools import wraps
import math
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import db
from app.models import (
    ClassSubject,
    Enrollment,
    Evaluation,
    Grade,
    GradeHistory,
    SchoolClass,
    SchoolYear,
    Student,
    Subject,
    TeachingAssignment,
    User,
)
from app.services.results import calculate_student_results, class_enrollments, class_rankings
from app.services.offline import build_offline_snapshot

bp = Blueprint("school", __name__)


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorate


def active_year():
    return SchoolYear.query.filter_by(active=True).first()


@bp.get("/api/offline-snapshot")
@login_required
def offline_snapshot():
    response = make_response(build_offline_snapshot(current_user))
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def teacher_can_access(class_id, subject_id):
    return TeachingAssignment.query.filter_by(
        teacher_id=current_user.id,
        class_id=class_id,
        subject_id=subject_id,
        year_id=active_year().id,
    ).first() is not None


@bp.app_context_processor
def inject_shell_data():
    logo_path = Path(current_app.instance_path) / "school-logo.png"
    return {
        "active_year": active_year(),
        "school_logo_url": url_for("school.logo") if logo_path.is_file() else None,
    }


@bp.get("/logo")
def logo():
    logo_path = Path(current_app.instance_path) / "school-logo.png"
    if not logo_path.is_file():
        abort(404)
    return send_from_directory(current_app.instance_path, "school-logo.png", mimetype="image/png")


@bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        new_password = request.form.get("new_password", "")
        current_password = request.form.get("current_password", "")
        conflicts = User.query.filter(
            db.or_(User.username == username, db.func.lower(User.email) == email),
            User.id != current_user.id,
        ).first()
        if not all((username, email, first_name, last_name)):
            flash("L’identifiant, le nom, le prénom et l’adresse électronique sont obligatoires.", "danger")
        elif conflicts:
            flash("Cet identifiant ou cette adresse électronique est déjà attribué à un autre compte.", "danger")
        elif new_password and (
            len(new_password) < 8 or not current_user.check_password(current_password)
        ):
            flash("Pour changer de mot de passe, saisissez le mot de passe actuel et un nouveau mot de passe d’au moins 8 caractères.", "danger")
        else:
            current_user.username = username
            current_user.email = email
            current_user.first_name = first_name
            current_user.last_name = last_name
            if new_password:
                current_user.set_password(new_password)
            db.session.commit()
            flash("Votre identité et vos préférences ont été mises à jour.", "success")
            return redirect(url_for("school.profile"))
    return render_template("profile.html")


@bp.route("/parametres", methods=["GET", "POST"])
@roles_required("admin")
def settings():
    if request.method == "POST":
        if not current_app.config["PERSISTENT_UPLOADS"]:
            flash(
                "Le stockage durable des fichiers n’est pas configuré sur cet hébergement. "
                "Le logo personnalisé reste disponible en local.",
                "danger",
            )
            return render_template("settings.html")
        upload = request.files.get("school_logo")
        if not upload or not upload.filename:
            flash("Sélectionnez une image de logo à téléverser.", "danger")
        else:
            from PIL import Image, UnidentifiedImageError

            try:
                image = Image.open(upload.stream)
                if image.format not in ("PNG", "JPEG", "WEBP") or image.width > 5000 or image.height > 5000:
                    raise ValueError("Format ou dimensions non pris en charge.")
                image.load()
                image.convert("RGBA").save(
                    Path(current_app.instance_path) / "school-logo.png",
                    format="PNG",
                    optimize=True,
                )
            except (UnidentifiedImageError, OSError, ValueError):
                flash("Le logo doit être une image PNG, JPG ou WEBP valide de 5 000 × 5 000 pixels maximum.", "danger")
            else:
                flash("Le logo de l’établissement a été remplacé.", "success")
                return redirect(url_for("school.settings"))
    return render_template("settings.html")


@bp.route("/")
@login_required
def dashboard():
    year = active_year()
    if current_user.role == "enseignant":
        assignments = TeachingAssignment.query.filter_by(teacher_id=current_user.id, year_id=year.id).all()
        assigned_ids = {item.id for item in assignments}
        evaluations = Evaluation.query.filter(Evaluation.teacher_id == current_user.id).order_by(
            Evaluation.held_on.desc()
        ).all()
        return render_template(
            "dashboard.html", mode="teacher", assignments=assignments,
            evaluations=evaluations, assigned_ids=assigned_ids, year=year
        )

    classes = SchoolClass.query.order_by(SchoolClass.name).all()
    evaluations = Evaluation.query.filter_by(year_id=year.id).all()
    pending = [item for item in evaluations if item.status == "Soumise"]
    class_averages = []
    for school_class in classes:
        enrollments = class_enrollments(school_class.id, year.id)
        averages = [
            average
            for enrollment in enrollments
            for _, average, complete in [calculate_student_results(enrollment, "Trimestre 1")]
            if complete and average is not None
        ]
        if averages:
            class_averages.append((school_class.name, round(sum(averages) / len(averages), 2)))
    metrics = {
        "students": Enrollment.query.filter_by(year_id=year.id, status="Inscrit").count(),
        "classes": len(classes),
        "teachers": User.query.filter_by(role="enseignant", active=True).count(),
        "subjects": Subject.query.filter_by(active=True).count(),
        "evaluations": len(evaluations),
        "pending": len(pending),
    }
    return render_template(
        "dashboard.html", mode="management", year=year, metrics=metrics,
        classes=classes, class_averages=class_averages, pending=pending
    )


@bp.route("/eleves", methods=["GET", "POST"])
@roles_required("admin", "direction")
def students():
    year = active_year()
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        matricule = request.form.get("matricule", "").strip().upper()
        class_id = request.form.get("class_id", type=int)
        birth_date_text = request.form.get("birth_date", "").strip()
        try:
            birth_date = date.fromisoformat(birth_date_text)
        except ValueError:
            birth_date = None
        if not first_name or not last_name or not matricule or not class_id or not birth_date:
            flash("Renseignez le nom, le prénom, le matricule, la date de naissance et la classe.", "danger")
        elif not date(2009, 1, 1) <= birth_date <= date(2028, 12, 31):
            flash("La date de naissance doit se situer entre 2009 et 2028.", "danger")
        elif not db.session.get(SchoolClass, class_id):
            flash("Sélectionnez une classe existante.", "danger")
        elif Student.query.filter_by(matricule=matricule).first():
            flash("Ce matricule existe déjà.", "danger")
        else:
            student = Student(
                first_name=first_name, last_name=last_name, matricule=matricule,
                birth_date=birth_date,
                birth_place=request.form.get("birth_place", "").strip() or None,
            )
            db.session.add(student)
            db.session.flush()
            db.session.add(Enrollment(student_id=student.id, class_id=class_id, year_id=year.id))
            db.session.commit()
            flash("L'élève et son inscription ont été enregistrés.", "success")
            return redirect(url_for("school.students"))
    query = Student.query.join(Enrollment).filter(Enrollment.year_id == year.id)
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(
            db.or_(Student.first_name.ilike(f"%{search}%"), Student.last_name.ilike(f"%{search}%"),
                   Student.matricule.ilike(f"%{search}%"))
        )
    selected_class = request.args.get("class_id", type=int)
    if selected_class:
        query = query.filter(Enrollment.class_id == selected_class)
    entries = query.order_by(Student.last_name, Student.first_name).all()
    return render_template(
        "students.html", students=entries, classes=SchoolClass.query.order_by(SchoolClass.name).all(),
        search=search, selected_class=selected_class
    )


@bp.route("/classes", methods=["GET", "POST"])
@roles_required("admin", "direction")
def classes():
    year = active_year()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        level = request.form.get("level", "").strip()
        track = request.form.get("track", "").strip()
        if not name or not level or not track:
            flash("Renseignez le nom, le niveau et le parcours de la classe.", "danger")
        elif SchoolClass.query.filter_by(name=name).first():
            flash("Une classe portant ce nom existe déjà.", "danger")
        else:
            school_class = SchoolClass(name=name, level=level, track=track)
            db.session.add(school_class)
            db.session.flush()
            for subject_id in request.form.getlist("subject_ids"):
                try:
                    parsed_subject_id = int(subject_id)
                except ValueError:
                    db.session.rollback()
                    flash("La sélection de matières contient une valeur invalide.", "danger")
                    return redirect(url_for("school.classes"))
                subject = db.session.get(Subject, parsed_subject_id)
                if not subject or not subject.active:
                    continue
                coefficient = request.form.get(f"coefficient_{subject.id}", type=float)
                if coefficient is None or not math.isfinite(coefficient) or coefficient <= 0:
                    db.session.rollback()
                    flash(f"Le coefficient de {subject.name} doit être supérieur à zéro.", "danger")
                    return redirect(url_for("school.classes"))
                db.session.add(ClassSubject(
                    class_id=school_class.id,
                    subject_id=subject.id,
                    year_id=year.id,
                    coefficient=coefficient,
                ))
                teacher_id = request.form.get(f"teacher_{subject.id}", type=int)
                if teacher_id:
                    teacher = db.session.get(User, teacher_id)
                    if teacher and teacher.role == "enseignant" and teacher.active:
                        db.session.add(TeachingAssignment(
                            teacher_id=teacher.id,
                            class_id=school_class.id,
                            subject_id=subject.id,
                            year_id=year.id,
                        ))
            db.session.commit()
            flash(f"La classe {school_class.name} a été créée pour {year.label}.", "success")
            return redirect(url_for("school.classes"))
    class_rows = []
    for school_class in SchoolClass.query.order_by(SchoolClass.name).all():
        count = Enrollment.query.filter_by(class_id=school_class.id, year_id=year.id, status="Inscrit").count()
        subjects = ClassSubject.query.filter_by(class_id=school_class.id, year_id=year.id).all()
        class_rows.append((school_class, count, subjects))
    return render_template(
        "classes.html", class_rows=class_rows,
        subjects=Subject.query.filter_by(active=True).order_by(Subject.name).all(),
        teachers=User.query.filter_by(role="enseignant", active=True).order_by(User.last_name).all(),
    )


@bp.route("/matieres", methods=["GET", "POST"])
@roles_required("admin", "direction")
def subjects():
    year = active_year()
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "assign":
            subject_id = request.form.get("subject_id", type=int)
            class_id = request.form.get("class_id", type=int)
            coefficient = request.form.get("coefficient", type=float)
            subject = db.session.get(Subject, subject_id) if subject_id else None
            school_class = db.session.get(SchoolClass, class_id) if class_id else None
            if (
                not subject or not school_class or coefficient is None
                or not math.isfinite(coefficient) or coefficient <= 0
            ):
                flash("Choisissez une matière, une classe et un coefficient supérieur à zéro.", "danger")
                return redirect(url_for("school.subjects"))
            elif ClassSubject.query.filter_by(
                subject_id=subject.id, class_id=school_class.id, year_id=year.id
            ).first():
                flash("Cette matière est déjà associée à cette classe pour l’année en cours.", "warning")
                return redirect(url_for("school.subjects"))
            else:
                db.session.add(ClassSubject(
                    subject_id=subject.id, class_id=school_class.id,
                    year_id=year.id, coefficient=coefficient,
                ))
                db.session.commit()
                flash("Matière et coefficient associés à la classe.", "success")
                return redirect(url_for("school.subjects"))
        elif action != "create":
            abort(400)
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        class_id = request.form.get("class_id", type=int)
        coefficient = request.form.get("coefficient", type=float)
        if action == "create" and (not code or not name):
            flash("Le code et le nom de la matière sont obligatoires.", "danger")
        elif action == "create" and Subject.query.filter(
            db.or_(Subject.code == code, Subject.name.ilike(name))
        ).first():
            flash("Ce code ou ce nom de matière est déjà utilisé.", "danger")
        elif action == "create" and class_id and (
            coefficient is None or not math.isfinite(coefficient) or coefficient <= 0
        ):
            flash("Le coefficient doit être supérieur à zéro.", "danger")
        elif action == "create":
            subject = Subject(code=code, name=name)
            db.session.add(subject)
            db.session.flush()
            if class_id:
                if not db.session.get(SchoolClass, class_id):
                    db.session.rollback()
                    abort(400)
                db.session.add(ClassSubject(
                    class_id=class_id, subject_id=subject.id, year_id=year.id,
                    coefficient=coefficient,
                ))
            db.session.commit()
            flash(f"La matière {name} a été créée.", "success")
            return redirect(url_for("school.subjects"))
    rows = ClassSubject.query.filter_by(year_id=year.id).order_by(ClassSubject.class_id).all()
    return render_template(
        "subjects.html", rows=rows,
        subjects=Subject.query.filter_by(active=True).order_by(Subject.name).all(),
        classes=SchoolClass.query.order_by(SchoolClass.name).all(),
    )


@bp.route("/enseignants", methods=["GET", "POST"])
@roles_required("admin")
def teachers():
    year = active_year()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            password = request.form.get("password", "")
            if not all((username, email, first_name, last_name, password)):
                flash("Tous les champs du dossier enseignant sont obligatoires.", "danger")
            elif len(password) < 8:
                flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
            elif User.query.filter(db.or_(User.username == username, User.email == email)).first():
                flash("Cet identifiant ou cette adresse électronique est déjà utilisé.", "danger")
            else:
                teacher = User(
                    username=username, email=email, first_name=first_name,
                    last_name=last_name, role="enseignant",
                )
                teacher.set_password(password)
                db.session.add(teacher)
                db.session.commit()
                flash(f"Le compte enseignant de {teacher.full_name} a été créé.", "success")
                return redirect(url_for("school.teachers"))
        elif action == "assign":
            teacher_id = request.form.get("teacher_id", type=int)
            class_subject_id = request.form.get("class_subject_id", type=int)
            teacher = db.session.get(User, teacher_id) if teacher_id else None
            class_subject = db.session.get(ClassSubject, class_subject_id) if class_subject_id else None
            if not teacher or teacher.role != "enseignant" or not class_subject or class_subject.year_id != year.id:
                abort(400)
            exists = TeachingAssignment.query.filter_by(
                teacher_id=teacher.id, class_id=class_subject.class_id,
                subject_id=class_subject.subject_id, year_id=year.id,
            ).first()
            if exists:
                flash("Cette affectation existe déjà.", "warning")
            else:
                db.session.add(TeachingAssignment(
                    teacher_id=teacher.id, class_id=class_subject.class_id,
                    subject_id=class_subject.subject_id, year_id=year.id,
                ))
                db.session.commit()
                flash("Affectation enregistrée.", "success")
                return redirect(url_for("school.teachers"))
        else:
            abort(400)
    teacher_rows = User.query.filter_by(role="enseignant").order_by(User.last_name, User.first_name).all()
    assignments = TeachingAssignment.query.filter_by(year_id=year.id).all()
    class_subjects = ClassSubject.query.filter_by(year_id=year.id).all()
    return render_template(
        "teachers.html", teachers=teacher_rows, assignments=assignments,
        class_subjects=class_subjects,
    )


@bp.route("/notes")
@login_required
def grade_index():
    year = active_year()
    query = Evaluation.query.filter_by(year_id=year.id)
    if current_user.role == "enseignant":
        query = query.filter_by(teacher_id=current_user.id)
    evaluations = query.order_by(Evaluation.held_on.desc()).all()
    return render_template("grade_index.html", evaluations=evaluations)


@bp.route("/evaluations", methods=["GET", "POST"])
@login_required
def evaluations():
    year = active_year()
    if request.method == "POST":
        class_id = request.form.get("class_id", type=int)
        subject_id = request.form.get("subject_id", type=int)
        title = request.form.get("title", "").strip()
        period = request.form.get("period", "")
        assessment_type = request.form.get("assessment_type", "").strip()
        held_on_text = request.form.get("held_on", "")
        max_score = request.form.get("max_score", type=float)
        coefficient = request.form.get("coefficient", type=float)
        class_subject = ClassSubject.query.filter_by(
            class_id=class_id, subject_id=subject_id, year_id=year.id
        ).first()
        if current_user.role == "enseignant":
            teacher_id = current_user.id
            authorized = teacher_can_access(class_id, subject_id)
        elif current_user.role in ("admin", "direction"):
            teacher_id = request.form.get("teacher_id", type=int)
            authorized = bool(
                teacher_id and TeachingAssignment.query.filter_by(
                    teacher_id=teacher_id, class_id=class_id,
                    subject_id=subject_id, year_id=year.id,
                ).first()
            )
        else:
            abort(403)
        try:
            held_on = date.fromisoformat(held_on_text)
        except ValueError:
            held_on = None
        if not title or not class_subject or period not in ("Trimestre 1", "Trimestre 2", "Trimestre 3"):
            flash("Renseignez le titre, une classe et matière associées, et un trimestre valide.", "danger")
        elif assessment_type not in (
            "Interrogation", "Devoir surveillé", "Composition", "Examen",
            "Travaux pratiques", "Évaluation orale",
        ):
            flash("Sélectionnez un type d’évaluation reconnu.", "danger")
        elif (
            not held_on or max_score is None or not math.isfinite(max_score) or max_score <= 0
            or coefficient is None or not math.isfinite(coefficient) or coefficient <= 0
        ):
            flash("La date et les coefficients doivent être valides et supérieurs à zéro.", "danger")
        elif not authorized:
            abort(403)
        else:
            evaluation = Evaluation(
                title=title, class_id=class_id, subject_id=subject_id,
                year_id=year.id, period=period, assessment_type=assessment_type,
                held_on=held_on, max_score=max_score, coefficient=coefficient,
                teacher_id=teacher_id, status="Brouillon",
            )
            db.session.add(evaluation)
            db.session.flush()
            for enrollment in class_enrollments(class_id, year.id):
                db.session.add(Grade(
                    evaluation_id=evaluation.id, enrollment_id=enrollment.id,
                    status="Manquante",
                ))
            db.session.commit()
            flash("L’évaluation a été créée avec une ligne par élève inscrit.", "success")
            return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id))

    assignments = TeachingAssignment.query.filter_by(year_id=year.id).all()
    if current_user.role == "enseignant":
        assignments = [item for item in assignments if item.teacher_id == current_user.id]
    else:
        assignments = [
            item for item in assignments
            if item.teacher_id and db.session.get(User, item.teacher_id).active
        ]
    keys = {(item.class_id, item.subject_id) for item in assignments}
    class_subjects = [
        item for item in ClassSubject.query.filter_by(year_id=year.id).all()
        if (item.class_id, item.subject_id) in keys
    ]
    class_subject_options = [
        (
            item,
            [
                assignment.teacher_id for assignment in assignments
                if assignment.class_id == item.class_id
                and assignment.subject_id == item.subject_id
            ],
        )
        for item in class_subjects
    ]
    return render_template(
        "evaluation_form.html", assignments=assignments,
        class_subject_options=class_subject_options,
        teachers=User.query.filter_by(role="enseignant", active=True).order_by(User.last_name).all(),
        today_iso=date.today().isoformat(),
    )


@bp.route("/evaluation/<int:evaluation_id>", methods=["GET", "POST"])
@login_required
def grade_entry(evaluation_id):
    evaluation = db.get_or_404(Evaluation, evaluation_id)
    correction_mode = (
        evaluation.status == "Validée"
        and current_user.role in ("admin", "direction")
        and request.args.get("correction") == "1"
    )
    if current_user.role == "enseignant":
        if evaluation.teacher_id != current_user.id or not teacher_can_access(
            evaluation.class_id, evaluation.subject_id
        ):
            abort(403)
    elif current_user.role not in ("admin", "direction"):
        abort(403)
    if evaluation.status in ("Soumise", "Validée") and current_user.role == "enseignant":
        flash("Cette fiche est verrouillée après soumission.", "warning")
        return redirect(url_for("school.grade_index"))
    if evaluation.status == "Validée" and request.method == "POST" and not correction_mode:
        abort(409)
    if evaluation.status == "Soumise" and request.method == "POST":
        abort(409)

    enrollments = class_enrollments(evaluation.class_id, evaluation.year_id)
    existing = {grade.enrollment_id: grade for grade in evaluation.grades}
    if request.method == "POST":
        correction_reason = request.form.get("correction_reason", "").strip()
        if evaluation.status == "Validée" and (
            request.form.get("action") != "correct" or not correction_reason
        ):
            flash("Une justification est obligatoire pour corriger une fiche validée.", "danger")
            return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id, correction=1))
        for enrollment in enrollments:
            score_text = request.form.get(f"score_{enrollment.id}", "").strip()
            status = request.form.get(f"status_{enrollment.id}", "Note")
            observation = request.form.get(f"observation_{enrollment.id}", "").strip()[:200]
            if status in ("Absent", "Dispensé"):
                score = None
            elif status == "Manquante" or score_text == "":
                score, status = None, "Manquante"
            else:
                try:
                    score = float(score_text)
                except ValueError:
                    flash(f"Note invalide pour {enrollment.student.full_name}.", "danger")
                    return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id))
                if not math.isfinite(score) or score < 0 or score > evaluation.max_score:
                    flash(
                        f"La note de {enrollment.student.full_name} doit être comprise entre 0 et {evaluation.max_score:g}.",
                        "danger",
                    )
                    return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id))
                status = "Note"
            grade = existing.get(enrollment.id)
            if grade is None:
                grade = Grade(evaluation_id=evaluation.id, enrollment_id=enrollment.id)
                db.session.add(grade)
                existing[enrollment.id] = grade
            if evaluation.status == "Validée" and (
                grade.score != score or grade.status != status or grade.observation != (observation or None)
            ):
                db.session.add(GradeHistory(
                    grade_id=grade.id, changed_by=current_user.id,
                    old_score=grade.score, new_score=score,
                    old_status=grade.status, new_status=status,
                    old_observation=grade.observation, new_observation=observation or None,
                    reason=correction_reason[:300],
                ))
            grade.score, grade.status, grade.observation = score, status, observation or None
        action = request.form.get("action")
        if action == "correct":
            db.session.commit()
            flash("Correction enregistrée dans l’historique.", "success")
            return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id))
        if action == "submit":
            missing = sum(1 for enrollment in enrollments if (
                          request.form.get(f"status_{enrollment.id}") == "Manquante"
                          or not request.form.get(f"score_{enrollment.id}", "").strip())
                          and request.form.get(f"status_{enrollment.id}") != "Dispensé"
                          and request.form.get(f"status_{enrollment.id}") != "Absent")
            if missing:
                db.session.rollback()
                flash(f"Il reste {missing} note(s) manquante(s). Complétez la fiche avant de la soumettre.", "danger")
                return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id))
            evaluation.status = "Soumise"
            evaluation.submitted_at = datetime.utcnow()
        db.session.commit()
        flash("Fiche soumise pour validation." if action == "submit" else "Brouillon enregistré.", "success")
        return redirect(url_for("school.grade_entry", evaluation_id=evaluation.id))

    return render_template(
        "grade_entry.html", evaluation=evaluation, enrollments=enrollments, grades=existing,
        correction_mode=correction_mode,
        history=(
            GradeHistory.query.join(Grade, GradeHistory.grade_id == Grade.id)
            .filter(Grade.evaluation_id == evaluation.id)
            .order_by(GradeHistory.changed_at.desc()).all()
        ),
    )


@bp.route("/validations", methods=["GET", "POST"])
@roles_required("admin", "direction")
def validations():
    if request.method == "POST":
        evaluation = db.get_or_404(Evaluation, request.form.get("evaluation_id", type=int))
        decision = request.form.get("decision")
        if evaluation.status != "Soumise":
            abort(409)
        if decision == "refuser":
            reason = request.form.get("reason", "").strip()
            if not reason:
                flash("Un motif est obligatoire pour refuser une fiche.", "danger")
                return redirect(url_for("school.validations"))
            evaluation.status = "Brouillon"
            evaluation.refusal_reason = reason[:300]
            evaluation.submitted_at = None
        elif decision == "valider":
            evaluation.status = "Validée"
            evaluation.validated_by = current_user.id
            evaluation.validated_at = datetime.utcnow()
            evaluation.refusal_reason = None
            enrolled_ids = {item.id for item in class_enrollments(evaluation.class_id, evaluation.year_id)}
            submitted_grades = {
                grade.enrollment_id: grade
                for grade in Grade.query.filter_by(evaluation_id=evaluation.id).all()
            }
            incomplete = [
                enrollment_id for enrollment_id in enrolled_ids
                if enrollment_id not in submitted_grades
                or submitted_grades[enrollment_id].status not in ("Note", "Absent", "Dispensé")
                or (
                    submitted_grades[enrollment_id].status == "Note"
                    and (
                        submitted_grades[enrollment_id].score is None
                        or submitted_grades[enrollment_id].score < 0
                        or submitted_grades[enrollment_id].score > evaluation.max_score
                    )
                )
            ]
            if incomplete:
                db.session.rollback()
                flash("Cette fiche contient des notes manquantes et ne peut pas être validée.", "danger")
                return redirect(url_for("school.validations"))
        else:
            flash("Décision non reconnue.", "danger")
            return redirect(url_for("school.validations"))
        db.session.commit()
        flash("Décision enregistrée.", "success")
        return redirect(url_for("school.validations"))
    pending = Evaluation.query.filter_by(status="Soumise").order_by(Evaluation.submitted_at).all()
    return render_template("validations.html", evaluations=pending)


@bp.route("/classements")
@roles_required("admin", "direction", "enseignant")
def rankings():
    year = active_year()
    class_id = request.args.get("class_id", type=int)
    period = request.args.get("period", "Trimestre 1")
    if current_user.role == "enseignant":
        assigned = TeachingAssignment.query.filter_by(teacher_id=current_user.id, year_id=year.id).all()
        allowed_classes = {item.class_id for item in assigned}
        classes = SchoolClass.query.filter(SchoolClass.id.in_(allowed_classes)).all() if allowed_classes else []
        if class_id not in allowed_classes:
            class_id = classes[0].id if classes else None
    else:
        classes = SchoolClass.query.order_by(SchoolClass.name).all()
    ranking_rows = class_rankings(class_id, year.id, period) if class_id else []
    return render_template(
        "rankings.html", classes=classes, selected_class=class_id, period=period,
        ranking_rows=ranking_rows
    )


@bp.route("/bulletins")
@roles_required("admin", "direction")
def bulletins():
    year = active_year()
    class_id = request.args.get("class_id", type=int)
    period = request.args.get("period", "Trimestre 1")
    classes = SchoolClass.query.order_by(SchoolClass.name).all()
    enrollments = class_enrollments(class_id, year.id) if class_id else []
    ranking = {enrollment.id: (rank, average) for rank, enrollment, average
               in class_rankings(class_id, year.id, period)} if class_id else {}
    results = []
    for enrollment in enrollments:
        _, average, complete = calculate_student_results(enrollment, period)
        results.append((enrollment, average, complete, ranking.get(enrollment.id)))
    return render_template(
        "bulletins.html", classes=classes, selected_class=class_id, period=period, results=results
    )


@bp.route("/bulletin/<int:enrollment_id>/<period>")
@roles_required("admin", "direction")
def bulletin_pdf(enrollment_id, period):
    enrollment = db.get_or_404(Enrollment, enrollment_id)
    if period not in ("Trimestre 1", "Trimestre 2", "Trimestre 3"):
        abort(404)
    subject_results, overall, complete = calculate_student_results(enrollment, period)
    if not complete or overall is None:
        flash("Ce bulletin est incomplet : seules les fiches validées sont prises en compte.", "warning")
        return redirect(url_for("school.bulletins", class_id=enrollment.class_id, period=period))
    rankings = class_rankings(enrollment.class_id, enrollment.year_id, period)
    rank = next((position for position, item, _ in rankings if item.id == enrollment.id), None)
    buffer = __import__("io").BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                                 topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("NdnTitle", parent=styles["Title"], textColor=colors.HexColor("#174A70"),
                           alignment=TA_CENTER, fontSize=18)
    story = [
        Paragraph("COLLÈGE CATHOLIQUE BILINGUE", styles["Heading2"]),
        Paragraph("NOTRE-DAME DES NATIONS · YAOUNDÉ", styles["Normal"]),
        Spacer(1, 8*mm),
        Paragraph("BULLETIN SCOLAIRE", title),
        Paragraph(f"{enrollment.school_year.label} · {period}", styles["Heading3"]),
        Spacer(1, 5*mm),
        Paragraph(
            f"<b>Élève :</b> {enrollment.student.full_name} &nbsp;&nbsp; "
            f"<b>Matricule :</b> {enrollment.student.matricule}<br/>"
            f"<b>Classe :</b> {enrollment.school_class.name}",
            styles["Normal"],
        ),
        Spacer(1, 6*mm),
    ]
    data = [["Matière", "Moyenne /20", "Coef.", "Points"]]
    for result in subject_results:
        data.append([result.subject, f"{result.average:.2f}", f"{result.coefficient:g}",
                     f"{result.weighted_points:.2f}"])
    data.append(["MOYENNE GÉNÉRALE", f"{overall:.2f}", "", ""])
    table = Table(data, colWidths=[77*mm, 35*mm, 22*mm, 32*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#174A70")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cad9e5")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f6fc")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 6*mm),
                  Paragraph(f"<b>Rang :</b> {rank or '—'} / {len(rankings)}", styles["Normal"]),
                  Spacer(1, 20*mm),
                  Paragraph("Signature du responsable pédagogique : ______________________________", styles["Normal"]),
                  Spacer(1, 10*mm),
                  Paragraph("Cachet de l'établissement", styles["Normal"])])
    document.build(story)
    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="bulletin-{enrollment.student.matricule}-{period[-1]}.pdf"'
    )
    return response


@bp.route("/rapports")
@roles_required("admin", "direction")
def reports():
    year = active_year()
    summary = []
    for school_class in SchoolClass.query.order_by(SchoolClass.name).all():
        enrollments = class_enrollments(school_class.id, year.id)
        complete = [
            average for enrollment in enrollments
            for _, average, is_complete in [calculate_student_results(enrollment, "Trimestre 1")]
            if is_complete and average is not None
        ]
        summary.append((school_class, len(enrollments), len(complete),
                        round(sum(complete) / len(complete), 2) if complete else None))
    return render_template("reports.html", summary=summary)
