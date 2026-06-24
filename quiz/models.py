import uuid
from django.db import models
from django.conf import settings
from core.models import TenantBoundModel, TimeStampedModel

DIFFICULTY_ORDER = {'easy': 1, 'moderate': 2, 'difficult': 3}


class QuizDifficulty(models.TextChoices):
    EASY      = 'easy',      'Easy'
    MODERATE  = 'moderate',  'Moderate'
    DIFFICULT = 'difficult', 'Difficult'


class QuizStatus(models.TextChoices):
    GENERATING = 'GENERATING', 'Generating'
    READY      = 'READY',      'Ready'
    FAILED     = 'FAILED',     'Failed'


class QuestionType(models.TextChoices):
    MCQ = 'MCQ', 'Multiple Choice'
    TF  = 'TF',  'True / False'


class Quiz(TenantBoundModel):
    """
    A set of AI-generated questions derived from a single student note.

    Status flow: GENERATING → READY | FAILED
    """
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quizzes',
    )
    note          = models.ForeignKey(
        'notes.NoteUpload',
        on_delete=models.CASCADE,
        related_name='quizzes',
    )
    title         = models.CharField(max_length=255)
    difficulty    = models.CharField(
        max_length=10,
        choices=QuizDifficulty.choices,
        default=QuizDifficulty.MODERATE,
        db_index=True,
    )
    num_questions = models.PositiveSmallIntegerField(default=10)
    status        = models.CharField(
        max_length=15,
        choices=QuizStatus.choices,
        default=QuizStatus.GENERATING,
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    ai_task_id    = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'quiz_quiz'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status'], name='idx_quiz_owner_status'),
        ]

    def __str__(self):
        return f'{self.title} [{self.difficulty}] [{self.status}]'


class QuizQuestion(TimeStampedModel):
    """
    A single question within a quiz. Scoped to the quiz (not directly tenant-bound).
    """
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz          = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    order         = models.PositiveSmallIntegerField(default=0)
    question_type = models.CharField(
        max_length=3,
        choices=QuestionType.choices,
        default=QuestionType.MCQ,
    )
    question_text = models.TextField()
    option_a      = models.CharField(max_length=512)
    option_b      = models.CharField(max_length=512)
    option_c      = models.CharField(max_length=512, blank=True)  # empty for TF
    option_d      = models.CharField(max_length=512, blank=True)  # empty for TF
    correct       = models.CharField(max_length=1)                # 'A', 'B', 'C', or 'D'
    explanation   = models.TextField(blank=True)

    class Meta:
        db_table = 'quiz_question'
        ordering = ['order']

    def __str__(self):
        return f'Q{self.order}: {self.question_text[:60]}'


class QuizAttempt(TenantBoundModel):
    """
    A student's completed attempt at a quiz.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz         = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    score        = models.PositiveSmallIntegerField(default=0)   # raw correct count
    total        = models.PositiveSmallIntegerField(default=0)   # total questions
    percentage   = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    time_taken_s = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quiz_attempt'
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['student', 'completed_at'], name='idx_attempt_student_date'),
        ]

    def __str__(self):
        return f'{self.student} — {self.quiz.title} — {self.percentage}%'


class QuizAttemptAnswer(models.Model):
    """
    The student's answer for one question within an attempt.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt    = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question   = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='attempt_answers')
    chosen     = models.CharField(max_length=1, blank=True)  # blank = skipped
    is_correct = models.BooleanField(default=False)

    class Meta:
        db_table = 'quiz_attempt_answer'

    def __str__(self):
        return f'Ans {self.chosen or "—"} ({"✓" if self.is_correct else "✗"})'


class TeacherSubjectThreshold(TenantBoundModel):
    """
    Teacher-defined minimum quiz requirements for a subject.
    Students cannot generate quizzes below these minimums for notes in this subject.
    """
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_thresholds',
    )
    subject        = models.CharField(max_length=100, db_index=True)
    min_questions  = models.PositiveSmallIntegerField(default=5)
    min_difficulty = models.CharField(
        max_length=10,
        choices=QuizDifficulty.choices,
        default=QuizDifficulty.EASY,
    )

    class Meta:
        db_table       = 'quiz_teacher_threshold'
        unique_together = [['school', 'teacher', 'subject']]

    def __str__(self):
        return f'{self.teacher} – {self.subject} (≥{self.min_questions}q, ≥{self.min_difficulty})'


class StudentQuizPreferences(TimeStampedModel):
    """
    A student's saved default quiz settings (global, not per-subject).
    Validated against teacher thresholds at quiz creation time.
    """
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student       = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_preferences',
    )
    school        = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='+',
    )
    num_questions = models.PositiveSmallIntegerField(default=10)
    difficulty    = models.CharField(
        max_length=10,
        choices=QuizDifficulty.choices,
        default=QuizDifficulty.MODERATE,
    )

    class Meta:
        db_table = 'quiz_student_preferences'

    def __str__(self):
        return f'{self.student} – {self.num_questions}q, {self.difficulty}'
