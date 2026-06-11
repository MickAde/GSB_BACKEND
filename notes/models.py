import uuid
from django.db import models
from django.conf import settings
from core.models import TenantBoundModel


class NoteStatus(models.TextChoices):
    PENDING_OCR         = 'PENDING_OCR',                'Pending OCR'
    AWAITING_APPROVAL   = 'AWAITING_STUDENT_APPROVAL',  'Awaiting Student Approval'
    PROCESSING_AI       = 'PROCESSING_AI',              'Processing AI'
    READY               = 'READY',                      'Ready'
    FAILED              = 'FAILED',                     'Failed'


class NoteType(models.TextChoices):
    PDF     = 'pdf',   'PDF'
    IMAGE   = 'image', 'Image'
    VOICE   = 'voice', 'Voice Note'
    TEXT    = 'text',  'Typed Text'


class NoteUpload(TenantBoundModel):
    """
    Anchor record for the note → OCR → AI summary pipeline.

    Status flow:
      PENDING_OCR → AWAITING_STUDENT_APPROVAL → PROCESSING_AI → READY
                                                              ↓
                                                           FAILED
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes',
    )

    # Storage
    file_url = models.CharField(max_length=1024, help_text='S3/R2 URI')
    file_name = models.CharField(max_length=255)
    note_type = models.CharField(max_length=10, choices=NoteType.choices)
    file_size_bytes = models.PositiveIntegerField(default=0)

    # Subject hierarchy: Subject → Topic → Subtopic
    subject = models.CharField(max_length=100, blank=True, db_index=True)
    topic = models.CharField(max_length=100, blank=True)
    subtopic = models.CharField(max_length=100, blank=True)

    # Pipeline output
    raw_ocr_text = models.TextField(blank=True)
    ai_summary_paragraph = models.TextField(blank=True)
    ai_bullet_points = models.JSONField(default=list)
    ai_key_points = models.JSONField(default=list)

    status = models.CharField(
        max_length=30,
        choices=NoteStatus.choices,
        default=NoteStatus.PENDING_OCR,
        db_index=True,
    )
    error_message = models.TextField(blank=True)

    # Celery task tracking
    ocr_task_id = models.CharField(max_length=255, blank=True)
    ai_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'notes_noteupload'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status'], name='idx_note_owner_status'),
            models.Index(fields=['school', 'subject'],  name='idx_note_school_subject'),
        ]

    def __str__(self):
        return f'{self.file_name} [{self.status}]'


class ConformityStatus(models.TextChoices):
    PENDING    = 'PENDING',    'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    DONE       = 'DONE',       'Done'
    FAILED     = 'FAILED',     'Failed'


class NoteConformityReport(TenantBoundModel):
    """
    AI-generated comparison of student notes vs. teacher-uploaded material.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_note = models.ForeignKey(
        NoteUpload,
        on_delete=models.CASCADE,
        related_name='conformity_reports_as_student',
    )
    teacher_note = models.ForeignKey(
        NoteUpload,
        on_delete=models.CASCADE,
        related_name='conformity_reports_as_teacher',
    )
    conformity_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    similarity_analysis = models.TextField(blank=True)
    status = models.CharField(
        max_length=15,
        choices=ConformityStatus.choices,
        default=ConformityStatus.PENDING,
        db_index=True,
    )
    ai_task_id = models.CharField(max_length=255, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notes_conformityreport'

    def __str__(self):
        return f'Conformity {self.conformity_percentage}% [{self.status}] — {self.student_note}'
