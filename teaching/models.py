import uuid
from django.db import models
from django.conf import settings
from core.models import TenantBoundModel, TimeStampedModel


class LessonPlanStatus(models.TextChoices):
    DRAFT           = 'DRAFT',            'Draft'
    SUBMITTED       = 'SUBMITTED',        'Submitted for Review'
    UNDER_REVIEW    = 'UNDER_REVIEW',     'Under Review'
    REVISION_NEEDED = 'REVISION_NEEDED',  'Revision Needed'
    APPROVED        = 'APPROVED',         'Approved'


class LessonPlan(TenantBoundModel):
    """
    A teacher-authored lesson plan with an admin approval workflow.

    Status flow: DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED | REVISION_NEEDED
    REVISION_NEEDED → (teacher edits) → SUBMITTED again.
    """
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher          = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_plans',
    )
    title            = models.CharField(max_length=255)
    subject          = models.CharField(max_length=100, blank=True, db_index=True)
    topic            = models.CharField(max_length=100, blank=True)
    subtopic         = models.CharField(max_length=100, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)

    # Lesson plan sections
    objective        = models.TextField(blank=True)
    materials_needed = models.TextField(blank=True)
    introduction     = models.TextField(blank=True)
    main_content     = models.TextField(blank=True)
    activities       = models.TextField(blank=True)
    assessment       = models.TextField(blank=True)
    homework         = models.TextField(blank=True)

    status           = models.CharField(
        max_length=20,
        choices=LessonPlanStatus.choices,
        default=LessonPlanStatus.DRAFT,
        db_index=True,
    )
    ai_suggestions   = models.TextField(blank=True)

    class Meta:
        db_table = 'teaching_lessonplan'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['teacher', 'status'], name='idx_plan_teacher_status'),
            models.Index(fields=['school', 'status'],  name='idx_plan_school_status'),
        ]

    def __str__(self):
        return f'{self.title} [{self.status}]'


class LessonPlanComment(TimeStampedModel):
    """
    Admin comment on a submitted lesson plan (feedback or approval note).
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson_plan = models.ForeignKey(LessonPlan, on_delete=models.CASCADE, related_name='comments')
    author      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_plan_comments',
    )
    body        = models.TextField()

    class Meta:
        db_table = 'teaching_lessonplancomment'
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author} on {self.lesson_plan}'
