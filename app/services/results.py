from collections import defaultdict
from dataclasses import dataclass

from app.models import ClassSubject, Enrollment, Evaluation, Grade, Student


@dataclass
class SubjectResult:
    subject: str
    average: float | None
    coefficient: float
    weighted_points: float | None
    complete: bool


def class_enrollments(class_id, year_id):
    return (
        Enrollment.query.filter_by(class_id=class_id, year_id=year_id, status="Inscrit")
        .join(Student, Enrollment.student_id == Student.id)
        .order_by(Student.last_name, Student.first_name)
        .all()
    )


def calculate_student_results(enrollment, period, require_validated=True):
    class_subjects = ClassSubject.query.filter_by(
        class_id=enrollment.class_id, year_id=enrollment.year_id
    ).all()
    output = []
    for class_subject in class_subjects:
        query = Evaluation.query.filter_by(
            class_id=enrollment.class_id,
            subject_id=class_subject.subject_id,
            year_id=enrollment.year_id,
            period=period,
        )
        if require_validated:
            query = query.filter_by(status="Validée")
        evaluations = query.all()
        weighted_score = 0.0
        total_weight = 0.0
        complete = bool(evaluations)
        for evaluation in evaluations:
            grade = Grade.query.filter_by(
                evaluation_id=evaluation.id, enrollment_id=enrollment.id
            ).first()
            if not grade or grade.status == "Manquante":
                complete = False
                continue
            if grade.status == "Dispensé":
                continue
            if grade.status == "Absent" or grade.score is None:
                continue
            weighted_score += (grade.score / evaluation.max_score) * 20 * evaluation.coefficient
            total_weight += evaluation.coefficient
        average = round(weighted_score / total_weight, 2) if total_weight else None
        output.append(
            SubjectResult(
                class_subject.subject.name,
                average,
                class_subject.coefficient,
                round(average * class_subject.coefficient, 2) if average is not None else None,
                complete,
            )
        )
    overall_weight = sum(item.coefficient for item in output if item.average is not None)
    overall = (
        round(sum(item.weighted_points for item in output if item.weighted_points is not None) / overall_weight, 2)
        if overall_weight
        else None
    )
    complete = bool(output) and all(item.complete and item.average is not None for item in output)
    return output, overall, complete


def calculate_class_average(class_id, year_id, period):
    averages = []
    for enrollment in class_enrollments(class_id, year_id):
        _, average, complete = calculate_student_results(enrollment, period)
        if complete and average is not None:
            averages.append(average)
    return (
        round(sum(averages) / len(averages), 2) if averages else None,
        len(averages),
    )


def class_rankings(class_id, year_id, period):
    rankings = []
    for enrollment in class_enrollments(class_id, year_id):
        _, average, complete = calculate_student_results(enrollment, period)
        if complete and average is not None:
            rankings.append((enrollment, average))
    rankings.sort(key=lambda row: (-row[1], row[0].student.last_name, row[0].student.first_name))
    return [(position, enrollment, average) for position, (enrollment, average) in enumerate(rankings, 1)]
