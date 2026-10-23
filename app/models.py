from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class SchoolYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(20), unique=True, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)


class SchoolClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    level = db.Column(db.String(40), nullable=False)
    track = db.Column(db.String(40), default="Francophone", nullable=False)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(30), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False, index=True)
    birth_date = db.Column(db.Date)
    birth_place = db.Column(db.String(100))
    nationality = db.Column(db.String(50), default="Camerounaise", nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    year_id = db.Column(db.Integer, db.ForeignKey("school_year.id"), nullable=False)
    enrolled_on = db.Column(db.Date, default=date.today, nullable=False)
    status = db.Column(db.String(20), default="Inscrit", nullable=False)
    student = db.relationship("Student", backref="enrollments")
    school_class = db.relationship("SchoolClass", backref="enrollments")
    school_year = db.relationship("SchoolYear")
    __table_args__ = (
        db.UniqueConstraint("student_id", "year_id", name="uq_student_year"),
        db.Index("ix_enrollment_class_year", "class_id", "year_id"),
    )


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)


class ClassSubject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    year_id = db.Column(db.Integer, db.ForeignKey("school_year.id"), nullable=False)
    coefficient = db.Column(db.Float, nullable=False)
    school_class = db.relationship("SchoolClass")
    subject = db.relationship("Subject")
    school_year = db.relationship("SchoolYear")
    __table_args__ = (
        db.UniqueConstraint("class_id", "subject_id", "year_id", name="uq_class_subject_year"),
    )


class TeachingAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    year_id = db.Column(db.Integer, db.ForeignKey("school_year.id"), nullable=False)
    school_class = db.relationship("SchoolClass")
    subject = db.relationship("Subject")
    __table_args__ = (
        db.UniqueConstraint(
            "teacher_id", "class_id", "subject_id", "year_id", name="uq_teacher_assignment"
        ),
    )


class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    year_id = db.Column(db.Integer, db.ForeignKey("school_year.id"), nullable=False)
    period = db.Column(db.String(40), nullable=False)
    assessment_type = db.Column(db.String(40), nullable=False)
    held_on = db.Column(db.Date, nullable=False, default=date.today)
    max_score = db.Column(db.Float, nullable=False)
    coefficient = db.Column(db.Float, nullable=False, default=1)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Brouillon")
    submitted_at = db.Column(db.DateTime)
    validated_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    validated_at = db.Column(db.DateTime)
    refusal_reason = db.Column(db.String(300))
    school_class = db.relationship("SchoolClass")
    subject = db.relationship("Subject")
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    validator = db.relationship("User", foreign_keys=[validated_by])
    grades = db.relationship("Grade", back_populates="evaluation", cascade="all, delete-orphan")
    __table_args__ = (
        db.Index("ix_evaluation_class_period", "class_id", "period", "status"),
    )


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluation.id"), nullable=False)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("enrollment.id"), nullable=False)
    score = db.Column(db.Float)
    status = db.Column(db.String(20), nullable=False, default="Manquante")
    observation = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    evaluation = db.relationship("Evaluation", back_populates="grades")
    enrollment = db.relationship("Enrollment")
    __table_args__ = (
        db.UniqueConstraint("evaluation_id", "enrollment_id", name="uq_grade_evaluation_student"),
    )


class GradeHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grade.id"), nullable=False)
    grade = db.relationship("Grade")
    changed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    old_score = db.Column(db.Float)
    new_score = db.Column(db.Float)
    old_status = db.Column(db.String(20), nullable=False)
    new_status = db.Column(db.String(20), nullable=False)
    old_observation = db.Column(db.String(200))
    new_observation = db.Column(db.String(200))
    reason = db.Column(db.String(300), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    actor = db.relationship("User", foreign_keys=[changed_by])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
