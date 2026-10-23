from datetime import date

from app import db
from app.models import (
    ClassSubject, Enrollment, Evaluation, Grade, SchoolClass, SchoolYear, Student,
    Subject, TeachingAssignment, User,
)


def seed_demo_data():
    if User.query.first():
        admin = User.query.filter_by(username="admin23").first()
        legacy_admin = User.query.filter_by(username="admin").first()
        if admin is None and legacy_admin and legacy_admin.role == "admin":
            legacy_admin.username = "admin23"
            admin = legacy_admin
        if admin and admin.check_password("NDN-Admin-2026!"):
            admin.set_password("admin000")
        ensure_demo_class_catalog()
        db.session.commit()
        return
    admin = User(username="admin23", email="admin@ndn.local", first_name="Aline",
                 last_name="Mballa", role="admin")
    admin.set_password("admin000")
    head = User(username="direction", email="direction@ndn.local", first_name="Jean",
                last_name="Fouda", role="direction")
    head.set_password("NDN-Direction-2026!")
    teacher = User(username="enseignant", email="enseignant@ndn.local",
                   first_name="Marie", last_name="Ngono", role="enseignant")
    teacher.set_password("NDN-Prof-2026!")
    db.session.add_all([admin, head, teacher])

    year = SchoolYear(label="2025–2026", start_date=date(2025, 9, 8),
                      end_date=date(2026, 6, 30), active=True)
    classes = [
        SchoolClass(name="6e A", level="Sixième", track="Francophone"),
        SchoolClass(name="5e A", level="Cinquième", track="Francophone"),
        SchoolClass(name="Form 1", level="Form 1", track="Anglophone"),
    ]
    subjects = [
        Subject(code="MATH", name="Mathématiques"),
        Subject(code="FR", name="Français"),
        Subject(code="ANG", name="Anglais"),
        Subject(code="SVT", name="Sciences de la Vie et de la Terre"),
    ]
    db.session.add_all([year, *classes, *subjects])
    db.session.flush()

    for school_class in classes:
        for index, subject in enumerate(subjects):
            db.session.add(ClassSubject(
                class_id=school_class.id, subject_id=subject.id, year_id=year.id,
                coefficient=[4, 3, 2, 2][index],
            ))
            db.session.add(TeachingAssignment(
                teacher_id=teacher.id, class_id=school_class.id, subject_id=subject.id,
                year_id=year.id,
            ))

    names = [
        ("Amina", "Abena"), ("Paul", "Atangana"), ("Sarah", "Biloa"),
        ("David", "Ebong"), ("Grace", "Etoundi"), ("Samuel", "Fouda"),
        ("Esther", "Kamdem"), ("Luc", "Kengne"), ("Ruth", "Manga"),
        ("Daniel", "Mekongo"), ("Chantal", "Mimbe"), ("Joel", "Momo"),
        ("Nadia", "Mvondo"), ("Eric", "Nana"), ("Prisca", "Ndongo"),
        ("Kevin", "Ngassa"), ("Alice", "Ngono"), ("Marc", "Noumbissi"),
        ("Deborah", "Onana"), ("Fabrice", "Tchoumi"), ("Ines", "Yondo"),
        ("Junior", "Zibi"), ("Clara", "Mbarga"), ("Emmanuel", "Simo"),
    ]
    enrollments = []
    for idx, (first, last) in enumerate(names):
        student = Student(
            matricule=f"NDN-{2026}-{idx + 1:03d}", first_name=first, last_name=last,
            birth_date=date(2012 + idx % 3, 2 + idx % 10, 5 + idx % 20),
            birth_place="Douala",
        )
        db.session.add(student)
        db.session.flush()
        enrollment = Enrollment(
            student_id=student.id, class_id=classes[idx // 8].id, year_id=year.id
        )
        db.session.add(enrollment)
        enrollments.append(enrollment)
    db.session.flush()

    evaluations = []
    for class_index, school_class in enumerate(classes):
        for subject_index, subject in enumerate(subjects):
            evaluation = Evaluation(
                title=f"Évaluation séquentielle {subject_index + 1}",
                class_id=school_class.id, subject_id=subject.id, year_id=year.id,
                period="Trimestre 1", assessment_type="Devoir surveillé",
                held_on=date(2025, 11, 10 + subject_index), max_score=20,
                coefficient=1, teacher_id=teacher.id,
                status=(
                    "Validée" if class_index == 0 or subject_index < 2
                    else "Brouillon" if subject_index == 2
                    else "Soumise"
                ),
            )
            db.session.add(evaluation)
            evaluations.append((evaluation, class_index, subject_index))
    db.session.flush()

    for evaluation, class_index, subject_index in evaluations:
        class_students = enrollments[class_index * 8:(class_index + 1) * 8]
        for student_index, enrollment in enumerate(class_students):
            if subject_index == 3 and student_index == 7:
                continue
            db.session.add(Grade(
                evaluation_id=evaluation.id, enrollment_id=enrollment.id,
                score=round(9 + ((student_index * 3 + subject_index * 2 + class_index) % 11), 1),
                status="Note",
            ))
    db.session.commit()
    ensure_demo_class_catalog()
    db.session.commit()


def ensure_demo_class_catalog():
    year = SchoolYear.query.filter_by(active=True).first()
    if not year:
        return
    teacher = User.query.filter_by(role="enseignant", active=True).first()
    class_levels = {
        "6e B": ("Sixième", "Francophone"),
        "5e B": ("Cinquième", "Francophone"),
        "4e A": ("Quatrième", "Francophone"),
        "4e B": ("Quatrième", "Francophone"),
        "3e A": ("Troisième", "Francophone"),
        "3e B": ("Troisième", "Francophone"),
        "2nde A": ("Seconde", "Francophone"),
        "1ère A": ("Première", "Francophone"),
        "Tle A": ("Terminale", "Francophone"),
        "Form 2": ("Form 2", "Anglophone"),
        "Form 3": ("Form 3", "Anglophone"),
        "Form 4": ("Form 4", "Anglophone"),
        "Form 5": ("Form 5", "Anglophone"),
        "Lower Sixth": ("Lower Sixth", "Anglophone"),
        "Upper Sixth": ("Upper Sixth", "Anglophone"),
    }
    subjects = Subject.query.filter_by(active=True).all()
    for name, (level, track) in class_levels.items():
        school_class = SchoolClass.query.filter_by(name=name).first()
        if not school_class:
            school_class = SchoolClass(name=name, level=level, track=track)
            db.session.add(school_class)
            db.session.flush()
        for index, subject in enumerate(subjects):
            class_subject = ClassSubject.query.filter_by(
                class_id=school_class.id, subject_id=subject.id, year_id=year.id
            ).first()
            if not class_subject:
                db.session.add(ClassSubject(
                    class_id=school_class.id, subject_id=subject.id,
                    year_id=year.id, coefficient=[4, 3, 2, 2][index % 4],
                ))
            if teacher and not TeachingAssignment.query.filter_by(
                teacher_id=teacher.id, class_id=school_class.id,
                subject_id=subject.id, year_id=year.id,
            ).first():
                db.session.add(TeachingAssignment(
                    teacher_id=teacher.id, class_id=school_class.id,
                    subject_id=subject.id, year_id=year.id,
                ))
