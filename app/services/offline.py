from app.models import (
    ClassSubject,
    Enrollment,
    Evaluation,
    SchoolClass,
    SchoolYear,
    TeachingAssignment,
)


def build_offline_snapshot(user):
    year = SchoolYear.query.filter_by(active=True).first()
    if year is None:
        return {"username": user.username, "role": user.role, "year": None,
                "classes": [], "students": [], "evaluations": []}

    assignments = []
    if user.role == "enseignant":
        assignments = TeachingAssignment.query.filter_by(
            teacher_id=user.id, year_id=year.id
        ).all()
        class_ids = {assignment.class_id for assignment in assignments}
        subject_ids = {assignment.subject_id for assignment in assignments}
    else:
        class_ids = {school_class.id for school_class in SchoolClass.query.order_by(
            SchoolClass.name
        ).all()}
        subject_ids = None

    if not class_ids:
        return {"username": user.username, "role": user.role, "year": year.label,
                "classes": [], "students": [], "evaluations": []}

    classes = SchoolClass.query.filter(SchoolClass.id.in_(class_ids)).order_by(
        SchoolClass.name
    ).all()
    enrollments = Enrollment.query.filter(
        Enrollment.year_id == year.id,
        Enrollment.class_id.in_(class_ids),
        Enrollment.status == "Inscrit",
    ).order_by(Enrollment.class_id, Enrollment.id).all()
    enrollments_by_class = {}
    for enrollment in enrollments:
        enrollments_by_class.setdefault(enrollment.class_id, []).append(enrollment)
    students = [{
        "enrollment_id": enrollment.id,
        "class_id": enrollment.class_id,
        "class_name": enrollment.school_class.name,
        "matricule": enrollment.student.matricule,
        "name": enrollment.student.full_name,
    } for enrollment in enrollments]

    evaluation_query = Evaluation.query.filter(
        Evaluation.year_id == year.id,
        Evaluation.class_id.in_(class_ids),
    )
    if user.role == "enseignant":
        evaluation_query = evaluation_query.filter(
            Evaluation.teacher_id == user.id,
            Evaluation.subject_id.in_(subject_ids),
        )
    evaluations = evaluation_query.order_by(
        Evaluation.held_on.desc(), Evaluation.id
    ).all()
    evaluation_data = []
    for evaluation in evaluations:
        grades_by_enrollment = {
            grade.enrollment_id: grade for grade in evaluation.grades
        }
        grade_rows = []
        for enrollment in enrollments_by_class.get(evaluation.class_id, []):
            grade = grades_by_enrollment.get(enrollment.id)
            grade_rows.append({
                "enrollment_id": enrollment.id,
                "score": grade.score if grade else None,
                "status": grade.status if grade else "Manquante",
            })
        evaluation_data.append({
            "id": evaluation.id,
            "title": evaluation.title,
            "class_id": evaluation.class_id,
            "class_name": evaluation.school_class.name,
            "subject": evaluation.subject.name,
            "period": evaluation.period,
            "date": evaluation.held_on.isoformat(),
            "max_score": evaluation.max_score,
            "status": evaluation.status,
            "grades": grade_rows,
        })

    subject_query = ClassSubject.query.filter(
        ClassSubject.year_id == year.id,
        ClassSubject.class_id.in_(class_ids),
    )
    if subject_ids is not None:
        subject_query = subject_query.filter(ClassSubject.subject_id.in_(subject_ids))
    subjects = [{
        "class_id": item.class_id,
        "class_name": item.school_class.name,
        "name": item.subject.name,
        "coefficient": item.coefficient,
    } for item in subject_query.order_by(ClassSubject.class_id, ClassSubject.id).all()]

    return {
        "username": user.username,
        "role": user.role,
        "year": year.label,
        "classes": [{"id": item.id, "name": item.name, "level": item.level,
                     "track": item.track} for item in classes],
        "subjects": subjects,
        "students": students,
        "evaluations": evaluation_data,
    }
