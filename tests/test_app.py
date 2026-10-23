from io import BytesIO
from pathlib import Path
import re

import pytest

from app.models import (
    ClassSubject, Enrollment, Evaluation, Grade, GradeHistory, SchoolClass, Student, Subject,
    TeachingAssignment, User,
)
from app import create_app, db, normalize_database_url
from app.services.results import (
    calculate_class_average,
    calculate_student_results,
    class_rankings,
)


def test_login_and_role_protection(client, login_user):
    response = login_user(client, "admin23", "admin000")
    assert response.status_code == 200
    assert b"Bonjour, Aline" in response.data
    client.post("/logout")
    login_user(client, "enseignant", "NDN-Prof-2026!")
    assert client.get("/eleves").status_code == 403
    assert client.get("/enseignants").status_code == 403
    assert client.get("/parametres").status_code == 403
    assert client.get("/evaluations").status_code == 200


def test_invalid_login_is_rejected(client):
    response = client.post("/login", data={"username": "admin23", "password": "incorrect"})
    assert b"Identifiant ou mot de passe incorrect" in response.data


def test_login_for_offline_sync_preserves_csrf_validation(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    login_page = client.get("/login")
    token = re.search(rb'type="hidden" name="csrf_token" value="([^"]+)"', login_page.data)
    assert token

    headers = {"X-NDN-Offline-Sync": "1"}
    success = client.post("/login", data={
        "username": "admin23", "password": "admin000",
        "csrf_token": token.group(1).decode(),
    }, headers=headers)
    assert success.status_code == 200
    assert success.json == {"authenticated": True, "username": "admin23"}


def test_offline_sync_revalidates_password_when_a_session_is_already_open(client, login_user):
    login_user(client, "admin23", "admin000")
    headers = {"X-NDN-Offline-Sync": "1"}
    wrong_password = client.post("/login", data={
        "username": "admin23", "password": "wrong-password",
    }, headers=headers)
    assert wrong_password.status_code == 401
    assert wrong_password.json["authenticated"] is False

    correct_password = client.post("/login", data={
        "username": "admin23", "password": "admin000",
    }, headers=headers)
    assert correct_password.status_code == 200
    assert correct_password.json == {"authenticated": True, "username": "admin23"}


def test_admin_demo_uses_updated_username(client, login_user):
    old_username = client.post("/login", data={
        "username": "admin", "password": "admin000"
    })
    assert b"Identifiant ou mot de passe incorrect" in old_username.data
    response = login_user(client, "admin23", "admin000")
    assert b"Bonjour, Aline" in response.data


def test_management_pages_render_for_authorized_user(client, login_user):
    login_user(client, "admin23", "admin000")
    for path in (
        "/eleves", "/classes", "/matieres", "/enseignants", "/evaluations", "/notes", "/validations",
        "/classements", "/bulletins?class_id=1", "/rapports", "/profil", "/parametres",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        if path == "/evaluations":
            assert "Créer une évaluation" in response.get_data(as_text=True)
        if path == "/classes":
            assert "classCreation" in response.get_data(as_text=True)


def test_mobile_navigation_and_touch_controls_are_available(client, login_user):
    login_user(client, "admin23", "admin000")
    page = client.get("/")
    assert b'id="mobileNavBackdrop"' in page.data
    assert b'aria-controls="sidebar"' in page.data
    assert b'aria-expanded="false"' in page.data

    stylesheet = client.get("/static/css/app.css")
    assert stylesheet.status_code == 200
    css = stylesheet.get_data(as_text=True)
    assert "width: 44px; height: 44px" in css
    assert "font-size: 16px" in css
    assert "overscroll-behavior-x: contain" in css


def test_pwa_resources_are_available_without_authentication(client):
    manifest = client.get("/static/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.mimetype == "application/manifest+json"
    assert manifest.json["start_url"] == "/"
    assert manifest.json["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest.json["icons"]} >= {"192x192", "512x512"}
    for size in (192, 512):
        icon = client.get(f"/static/images/ndn-app-icon-{size}.png")
        assert icon.status_code == 200
        assert icon.mimetype == "image/png"

    worker = client.get("/service-worker.js")
    assert worker.status_code == 200
    assert worker.headers["Service-Worker-Allowed"] == "/"
    assert worker.headers["Cache-Control"] == "no-cache"

    health = client.get("/health")
    assert health.status_code == 204
    assert health.headers["Cache-Control"] == "private, no-store"

    offline = client.get("/static/offline.html")
    assert offline.status_code == 200
    assert b"chiffr" in offline.data
    assert b"/static/js/offline.js" in offline.data
    worker_script = worker.get_data(as_text=True)
    assert '"/static/js/offline-store.js"' in worker_script
    assert 'url.pathname.startsWith("/api/")' in worker_script
    assert "ndn-static-v7" in worker_script

    offline_script = client.get("/static/js/offline.js")
    assert offline_script.status_code == 200
    assert "checkServerAndReturn" in offline_script.get_data(as_text=True)


def test_health_check_reports_database_unavailability(client, app, monkeypatch):
    from sqlalchemy.exc import OperationalError

    with app.app_context():
        def fail_query(*args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

        monkeypatch.setattr(db.session, "execute", fail_query)
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json == {"status": "unavailable"}


def test_database_url_normalization_supports_supabase_and_relative_sqlite(tmp_path):
    supabase_url = normalize_database_url(
        "postgres://postgres:secret@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
        tmp_path,
    )
    assert supabase_url.drivername == "postgresql+psycopg"
    assert supabase_url.password == "secret"
    assert supabase_url.query["sslmode"] == "require"

    sqlite_url = normalize_database_url("sqlite:///ndn_school.db", tmp_path)
    assert sqlite_url.database == str(tmp_path / "ndn_school.db")


def test_vercel_without_database_uses_temporary_prototype_database(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = create_app({"TESTING": True})
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:////tmp/ndn-school-prototype.db"
    assert app.config["PROTOTYPE_MODE"] is True
    assert app.config["PERSISTENT_UPLOADS"] is False
    assert app.config["SECRET_KEY"] == "ndn-school-prototype-only-do-not-use-with-real-data"


def test_vercel_with_database_still_requires_a_secret(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"TESTING": True})


def test_vercel_prototype_entrypoint_initializes_demo_data(tmp_path):
    from index import initialize_prototype_database

    prototype_app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'prototype.db'}",
        "SECRET_KEY": "test-secret",
    })
    prototype_app.config["PROTOTYPE_MODE"] = True
    initialize_prototype_database(prototype_app)

    with prototype_app.app_context():
        assert User.query.filter_by(username="admin23").one()
        assert Student.query.count() == 24


def test_offline_snapshot_requires_login_and_never_discloses_sensitive_fields(client, login_user):
    response = client.get("/api/offline-snapshot")
    assert response.status_code == 302

    login_user(client, "admin23", "admin000")
    response = client.get("/api/offline-snapshot")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json["username"] == "admin23"
    assert response.json["students"]
    assert "birth_date" not in response.get_data(as_text=True)
    assert "password" not in response.get_data(as_text=True).lower()
    assert any(
        grade["status"] == "Manquante"
        for evaluation in response.json["evaluations"]
        for grade in evaluation["grades"]
    )


def test_teacher_offline_snapshot_is_limited_to_assigned_classes(client, login_user, app):
    login_user(client, "enseignant", "NDN-Prof-2026!")
    response = client.get("/api/offline-snapshot")
    assert response.status_code == 200
    with app.app_context():
        assigned_class_ids = {
            assignment.class_id
            for assignment in TeachingAssignment.query.filter_by(teacher_id=3).all()
        }
    assert {school_class["id"] for school_class in response.json["classes"]} == assigned_class_ids
    assert all(
        evaluation["class_id"] in assigned_class_ids
        for evaluation in response.json["evaluations"]
    )


def test_password_visibility_control_uses_accessible_icon_button(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b'aria-label="Afficher le mot de passe"' in response.data
    assert b'id="togglePassword"' in response.data
    assert b'type="button"' in response.data
    assert b'<svg class="ui-icon"' in response.data
    assert b">Afficher</button>" not in response.data
    assert b"/static/js/app.js" in response.data


def test_student_creation_creates_an_annual_enrollment(client, login_user, app):
    login_user(client, "admin23", "admin000")
    dashboard = client.get("/")
    assert dashboard.headers["Cache-Control"] == "private, no-store"
    assert "manifest.webmanifest" in dashboard.get_data(as_text=True)
    response = client.post("/eleves", data={
        "first_name": "Test", "last_name": "Élève",
        "matricule": "NDN-TEST-001", "class_id": "1",
        "birth_date": "2012-02-15",
    }, follow_redirects=True)
    assert "son inscription ont été enregistrés." in response.get_data(as_text=True)
    with app.app_context():
        student = Student.query.filter_by(matricule="NDN-TEST-001").one()
        assert student.enrollments[0].school_class.name == "6e A"
        assert student.birth_date.isoformat() == "2012-02-15"


def test_student_birth_date_must_be_between_2009_and_2028(client, login_user, app):
    login_user(client, "admin23", "admin000")
    response = client.post("/eleves", data={
        "first_name": "Test", "last_name": "Date",
        "matricule": "NDN-TEST-DATE", "class_id": "1",
        "birth_date": "2008-12-31",
    }, follow_redirects=True)
    assert "entre 2009 et 2028" in response.get_data(as_text=True)
    with app.app_context():
        assert Student.query.filter_by(matricule="NDN-TEST-DATE").first() is None


def test_student_birth_date_accepts_inclusive_year_boundaries(client, login_user, app):
    login_user(client, "admin23", "admin000")
    for matricule, birth_date in (
        ("NDN-TEST-MIN", "2009-01-01"),
        ("NDN-TEST-MAX", "2028-12-31"),
    ):
        response = client.post("/eleves", data={
            "first_name": "Test", "last_name": "Borne",
            "matricule": matricule, "class_id": "1", "birth_date": birth_date,
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "La date de naissance doit se situer entre 2009 et 2028." not in response.get_data(as_text=True)
    with app.app_context():
        assert Student.query.filter_by(matricule="NDN-TEST-MIN").one().birth_date.isoformat() == "2009-01-01"
        assert Student.query.filter_by(matricule="NDN-TEST-MAX").one().birth_date.isoformat() == "2028-12-31"


def test_demo_catalog_includes_francophone_and_anglophone_secondary_levels(app):
    with app.app_context():
        names = {school_class.name for school_class in SchoolClass.query.all()}
        assert {"6e A", "Tle A", "Form 1", "Form 5", "Lower Sixth", "Upper Sixth"} <= names
        assert SchoolClass.query.filter_by(name="Lower Sixth").one().track == "Anglophone"


def test_admin_can_install_local_school_logo(client, login_user, app):
    from PIL import Image

    login_user(client, "admin23", "admin000")
    image = Image.new("RGB", (32, 32), color="#87ceeb")
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    response = client.post(
        "/parametres",
        data={"school_logo": (image_bytes, "logo.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Le logo de l’établissement a été remplacé." in response.get_data(as_text=True)
    response = client.get("/logo")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert (Path(app.instance_path) / "school-logo.png").is_file()


def test_logo_settings_shows_a_real_preview_and_upload_help(client, login_user):
    login_user(client, "admin23", "admin000")
    response = client.get("/parametres")
    assert response.status_code == 200
    assert b'id="logoPreview"' in response.data
    assert b"ndn-app-icon-192.png" in response.data
    assert b'id="logoFileName"' in response.data


def test_user_can_update_identity_and_password(client, login_user, app):
    login_user(client, "enseignant", "NDN-Prof-2026!")
    response = client.post("/profil", data={
        "first_name": "Marie", "last_name": "Ngono",
        "username": "marie.ngono", "email": "marie.ngono@ndn.local",
        "current_password": "NDN-Prof-2026!", "new_password": "Professeur2028!",
    }, follow_redirects=True)
    assert "Votre identité et vos préférences ont été mises à jour." in response.get_data(as_text=True)
    with app.app_context():
        teacher = User.query.filter_by(username="marie.ngono").one()
        assert teacher.check_password("Professeur2028!")


def test_admin_can_create_class_with_subjects_and_teacher(client, login_user, app):
    login_user(client, "admin23", "admin000")
    response = client.post("/classes", data={
        "name": "4e C",
        "level": "Quatrième",
        "track": "Francophone",
        "subject_ids": ["1", "2"],
        "coefficient_1": "3",
        "coefficient_2": "2",
        "teacher_1": "3",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "La classe 4e C a été créée" in response.get_data(as_text=True)
    with app.app_context():
        school_class = SchoolClass.query.filter_by(name="4e C").one()
        class_subjects = ClassSubject.query.filter_by(class_id=school_class.id).all()
        assert len(class_subjects) == 2
        assert {row.coefficient for row in class_subjects} == {2.0, 3.0}
        assert TeachingAssignment.query.filter_by(
            class_id=school_class.id, subject_id=1, teacher_id=3
        ).one()


def test_admin_can_create_and_assign_subjects(client, login_user, app):
    login_user(client, "admin23", "admin000")
    response = client.post("/matieres", data={
        "action": "create", "name": "Physique-Chimie", "code": "PC",
        "class_id": "", "coefficient": "2",
    }, follow_redirects=True)
    assert "La matière Physique-Chimie a été créée." in response.get_data(as_text=True)
    with app.app_context():
        subject = Subject.query.filter_by(code="PC").one()
        subject_id = subject.id
    response = client.post("/matieres", data={
        "action": "assign", "subject_id": str(subject_id),
        "class_id": "1", "coefficient": "4",
    }, follow_redirects=True)
    assert "Matière et coefficient associés à la classe." in response.get_data(as_text=True)


def test_teacher_can_create_subject_for_an_assigned_class_without_assigning_itself(
    client, login_user, app
):
    login_user(client, "enseignant", "NDN-Prof-2026!")
    assert client.get("/matieres").status_code == 200
    response = client.post("/matieres", data={
        "action": "create", "name": "Arts plastiques", "code": "ART",
        "class_id": "1", "coefficient": "2",
    }, follow_redirects=True)
    assert "La matière Arts plastiques a été créée." in response.get_data(as_text=True)

    with app.app_context():
        subject = Subject.query.filter_by(code="ART").one()
        assert ClassSubject.query.filter_by(
            subject_id=subject.id, class_id=1, year_id=1, coefficient=2
        ).one()
        assert TeachingAssignment.query.filter_by(subject_id=subject.id).count() == 0
        unassigned_class = SchoolClass(name="Classe non attribuée", level="Test")
        db.session.add(unassigned_class)
        db.session.commit()
        unassigned_class_id = unassigned_class.id

    denied = client.post("/matieres", data={
        "action": "assign", "subject_id": "1",
        "class_id": str(unassigned_class_id), "coefficient": "1",
    })
    assert denied.status_code == 403
    assert client.get("/enseignants").status_code == 403


def test_admin_can_create_teacher_and_evaluation(client, login_user, app):
    login_user(client, "admin23", "admin000")
    response = client.post("/enseignants", data={
        "action": "create", "first_name": "Emilie", "last_name": "Talla",
        "username": "etalla", "email": "etalla@ndn.local", "password": "Teacher2026!",
    }, follow_redirects=True)
    assert "Le compte enseignant de Emilie Talla a été créé." in response.get_data(as_text=True)
    with app.app_context():
        teacher = User.query.filter_by(username="etalla").one()
        teacher_id = teacher.id
        assignment = TeachingAssignment.query.filter_by(
            teacher_id=teacher_id, class_id=1, subject_id=1, year_id=1
        ).first()
        if not assignment:
            assignment = TeachingAssignment(
                teacher_id=teacher_id, class_id=1, subject_id=1, year_id=1
            )
            db.session.add(assignment)
            db.session.commit()
    response = client.post("/evaluations", data={
        "title": "Contrôle de géométrie", "class_id": "1", "subject_id": "1",
        "teacher_id": str(teacher_id), "period": "Trimestre 1",
        "assessment_type": "Devoir surveillé", "held_on": "2026-02-01",
        "max_score": "25", "coefficient": "2",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Contrôle de géométrie" in response.get_data(as_text=True)
    with app.app_context():
        evaluation = Evaluation.query.filter_by(title="Contrôle de géométrie").one()
        assert len(evaluation.grades) == 8


def test_calculation_uses_only_validated_scores_and_keeps_missing_incomplete(app):
    with app.app_context():
        enrollment = Enrollment.query.filter_by(class_id=2).first()
        results, average, complete = calculate_student_results(enrollment, "Trimestre 1")
        assert len(results) == 4
        assert average is not None
        assert complete is False
        assert any(result.average is None for result in results)


def test_subject_average_normalizes_barèmes_and_weights_evaluations(app):
    with app.app_context():
        enrollment = Enrollment.query.filter_by(class_id=1).first()
        first = Evaluation.query.filter_by(
            class_id=1, subject_id=1, status="Validée"
        ).one()
        first_grade = Grade.query.filter_by(
            evaluation_id=first.id, enrollment_id=enrollment.id
        ).one()
        second = Evaluation(
            title="Composition sur 25", class_id=1, subject_id=1, year_id=1,
            period="Trimestre 1", assessment_type="Composition",
            held_on=first.held_on, max_score=25, coefficient=2,
            teacher_id=first.teacher_id, status="Validée",
        )
        db.session.add(second)
        db.session.flush()
        db.session.add(Grade(
            evaluation_id=second.id, enrollment_id=enrollment.id, score=15, status="Note"
        ))
        db.session.commit()

        results, _, _ = calculate_student_results(enrollment, "Trimestre 1")
        math_result = next(result for result in results if result.subject == "Mathématiques")
        expected = round((first_grade.score + (15 / 25 * 20 * 2)) / 3, 2)
        assert math_result.average == expected
        assert math_result.coefficient == ClassSubject.query.filter_by(
            class_id=1, subject_id=1, year_id=1
        ).one().coefficient


def test_class_ranking_omits_incomplete_results(app):
    with app.app_context():
        school_class = SchoolClass.query.filter_by(name="5e A").one()
        ranking = class_rankings(school_class.id, 1, "Trimestre 1")
        assert ranking == []


def test_class_averages_are_automatic_and_displayed_across_results_pages(
    client, login_user, app
):
    with app.app_context():
        enrollments = Enrollment.query.filter_by(class_id=1, year_id=1).all()
        complete_averages = [
            average for enrollment in enrollments
            for _, average, complete in [
                calculate_student_results(enrollment, "Trimestre 1")
            ]
            if complete and average is not None
        ]
        expected = round(sum(complete_averages) / len(complete_averages), 2)
        assert calculate_class_average(1, 1, "Trimestre 1") == (
            expected, len(complete_averages)
        )

    login_user(client, "admin23", "admin000")
    students = client.get("/eleves?class_id=1&period=Trimestre%201")
    assert "MOYENNE GÉNÉRALE · Trimestre 1" in students.get_data(as_text=True)
    assert "Complète et validée" in students.get_data(as_text=True)
    classes = client.get("/classes?period=Trimestre%201")
    assert f"{expected:.2f} / 20" in classes.get_data(as_text=True)
    dashboard = client.get("/?period=Trimestre%201")
    assert f"{expected:.2f}" in dashboard.get_data(as_text=True)
    reports = client.get("/rapports?period=Trimestre%201")
    assert f"{expected:.2f} / 20" in reports.get_data(as_text=True)
    assert client.get("/classes?period=semestre").status_code == 400


def test_grade_entry_rejects_score_above_max(client, login_user, app):
    with app.app_context():
        evaluation = Evaluation.query.filter_by(status="Brouillon").first()
        evaluation_id = evaluation.id
        enrollment_id = evaluation.school_class.enrollments[0].id
        class_id, subject_id = evaluation.class_id, evaluation.subject_id
        assignment = TeachingAssignment.query.filter_by(
            class_id=class_id, subject_id=subject_id
        ).first()
        teacher = db.session.get(User, assignment.teacher_id)
        username = teacher.username
    login_user(client, username, "NDN-Prof-2026!")
    response = client.post(f"/evaluation/{evaluation_id}", data={
        f"score_{enrollment_id}": "99", f"status_{enrollment_id}": "Note", "action": "save"
    }, follow_redirects=True)
    assert "doit être comprise" in response.get_data(as_text=True)


def test_grade_submission_validation_and_bulletin_pdf(client, login_user, app):
    with app.app_context():
        draft = Evaluation.query.filter_by(status="Brouillon").first()
        school_class = db.session.get(SchoolClass, draft.class_id)
        submitted = Evaluation.query.filter_by(class_id=school_class.id, status="Soumise").first()
        enrollments = Enrollment.query.filter_by(class_id=school_class.id).order_by(Enrollment.id).all()
        draft_id, submitted_id = draft.id, submitted.id
        enrollment_ids = [item.id for item in enrollments]
        missing_id = next(
            item.id for item in enrollments
            if not Grade.query.filter_by(evaluation_id=submitted_id, enrollment_id=item.id).first()
        )

    login_user(client, "enseignant", "NDN-Prof-2026!")
    grade_data = {
        f"score_{enrollment_id}": "0" if enrollment_id == enrollment_ids[0] else "12"
        for enrollment_id in enrollment_ids
    }
    grade_data.update({f"status_{item}": "Note" for item in enrollment_ids})
    grade_data["action"] = "submit"
    response = client.post(f"/evaluation/{draft_id}", data=grade_data, follow_redirects=True)
    assert "Fiche soumise pour validation." in response.get_data(as_text=True)

    client.post("/logout")
    login_user(client, "direction", "NDN-Direction-2026!")
    response = client.post("/validations", data={
        "evaluation_id": submitted_id, "decision": "valider"
    }, follow_redirects=True)
    assert "notes manquantes" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Evaluation, submitted_id).status == "Soumise"
        db.session.add(Grade(
            evaluation_id=submitted_id, enrollment_id=missing_id,
            score=10, status="Note",
        ))
        db.session.commit()

    for evaluation_id in (draft_id, submitted_id):
        client.post("/validations", data={
            "evaluation_id": evaluation_id, "decision": "valider"
        })
    response = client.get(f"/bulletin/{enrollment_ids[0]}/Trimestre%201")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert ".pdf" in response.headers["Content-Disposition"]

    correction_response = client.post(
        f"/evaluation/{draft_id}?correction=1",
        data={
            **{f"score_{item}": "1" if item == enrollment_ids[0] else "12" for item in enrollment_ids},
            **{f"status_{item}": "Note" for item in enrollment_ids},
            "correction_reason": "Erreur de transcription vérifiée",
            "action": "correct",
        },
        follow_redirects=True,
    )
    assert "Correction enregistrée dans l’historique." in correction_response.get_data(as_text=True)
    with app.app_context():
        history = GradeHistory.query.one()
        assert (history.old_score, history.new_score) == (0, 1)
        assert history.reason == "Erreur de transcription vérifiée"
