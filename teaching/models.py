import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TenantBoundModel, TimeStampedModel


class LessonDocumentType(models.TextChoices):
    PLAN = 'plan', 'Lesson Plan'
    NOTE = 'note', 'Lesson Note'


class GenerationMode(models.TextChoices):
    AI     = 'ai',     'AI Generated'
    UPLOAD = 'upload', 'Upload & Analyze'
    MANUAL = 'manual', 'Manually Written'


class LessonDocumentStatus(models.TextChoices):
    DRAFT           = 'draft',           'Draft'
    GENERATING      = 'generating',      'Generating'
    SUBMITTED       = 'submitted',       'Submitted for Review'
    UNDER_REVIEW    = 'under_review',    'Under Review'
    REVISION_NEEDED = 'revision_needed', 'Revision Needed'
    APPROVED        = 'approved',        'Approved'
    DISTRIBUTED     = 'distributed',     'Distributed to Class'


class LessonDocument(TenantBoundModel):
    """
    AI-first lesson document. Covers both Lesson Plans and Lesson Notes.

    Status flow:
      DRAFT / GENERATING → SUBMITTED → UNDER_REVIEW → APPROVED | REVISION_NEEDED
      REVISION_NEEDED → (teacher edits) → SUBMITTED
      APPROVED (notes only) → DISTRIBUTED
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_docs',
    )

    doc_type        = models.CharField(max_length=10, choices=LessonDocumentType.choices, db_index=True)
    generation_mode = models.CharField(max_length=10, choices=GenerationMode.choices, default=GenerationMode.AI)

    # Minimal context the teacher provides
    subject            = models.CharField(max_length=100, db_index=True)
    topic              = models.CharField(max_length=200)
    subtopic           = models.CharField(max_length=200, blank=True)
    class_level        = models.CharField(max_length=50)
    term               = models.PositiveSmallIntegerField(default=1)
    week               = models.PositiveSmallIntegerField(default=1)
    additional_context = models.TextField(blank=True)

    # AI-generated body
    title            = models.CharField(max_length=300, blank=True)
    content_markdown = models.TextField(blank=True)
    board_summary    = models.TextField(blank=True)

    # AI analysis cards (JSONB on Postgres)
    diagnostic_cards = models.JSONField(default=list)
    resource_cards   = models.JSONField(default=list)

    # Combined OCR text from all uploaded files (generation_mode='upload')
    raw_ocr_text  = models.TextField(blank=True)

    # Async generation state
    status           = models.CharField(
        max_length=20,
        choices=LessonDocumentStatus.choices,
        default=LessonDocumentStatus.DRAFT,
        db_index=True,
    )
    ai_task_id       = models.CharField(max_length=255, blank=True)
    generation_error = models.TextField(blank=True)

    # Admin approval
    approved_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_lesson_docs',
    )
    approval_timestamp = models.DateTimeField(null=True, blank=True)
    verification_hash  = models.CharField(max_length=64, blank=True)
    admin_comments     = models.TextField(blank=True)

    # Distribution (lesson notes only — pushed read-only to student class on approval)
    distributed_to_class = models.BooleanField(default=False)
    distributed_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'teaching_lessondocument'
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['teacher', 'status'],   name='idx_ldoc_teacher_status'),
            models.Index(fields=['school',  'status'],   name='idx_ldoc_school_status'),
            models.Index(fields=['school',  'doc_type'], name='idx_ldoc_school_type'),
        ]

    def __str__(self):
        return f'[{self.doc_type.upper()}] {self.title or self.topic} [{self.status}]'

    def stamp_approval(self, approver):
        payload = f'{self.id}:{self.teacher_id}:{self.content_markdown[:200]}'
        self.verification_hash  = hashlib.sha256(payload.encode()).hexdigest()
        self.approved_by        = approver
        self.approval_timestamp = timezone.now()
        self.status             = LessonDocumentStatus.APPROVED

    def distribute(self):
        self.distributed_to_class = True
        self.distributed_at       = timezone.now()
        self.status               = LessonDocumentStatus.DISTRIBUTED


class LessonDocumentVersion(TimeStampedModel):
    """
    Markdown snapshot for full-diff version history.
    A new version is saved each time the teacher saves edits.
    """
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document         = models.ForeignKey(LessonDocument, on_delete=models.CASCADE, related_name='versions')
    version_number   = models.PositiveIntegerField()
    content_markdown = models.TextField()
    board_summary    = models.TextField(blank=True)
    saved_by         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    change_note      = models.TextField(blank=True)

    class Meta:
        db_table        = 'teaching_lessondocumentversion'
        ordering        = ['-version_number']
        unique_together = [['document', 'version_number']]

    def __str__(self):
        return f'v{self.version_number} — {self.document}'


class LessonDocumentFile(TimeStampedModel):
    """
    One uploaded source file for a lesson document created via the 'upload' mode.
    Multiple files are allowed; each is OCR'd and their text is concatenated.
    """
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        LessonDocument,
        on_delete=models.CASCADE,
        related_name='uploaded_files',
    )
    file  = models.FileField(upload_to='lesson_docs/uploads/')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'teaching_lessondocumentfile'
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'{self.file.name} (doc {self.document_id})'


# ── Legacy models (kept for data continuity) ──────────────────────────────────

class LessonPlanStatus(models.TextChoices):
    DRAFT           = 'DRAFT',            'Draft'
    SUBMITTED       = 'SUBMITTED',        'Submitted for Review'
    UNDER_REVIEW    = 'UNDER_REVIEW',     'Under Review'
    REVISION_NEEDED = 'REVISION_NEEDED',  'Revision Needed'
    APPROVED        = 'APPROVED',         'Approved'


class LessonPlan(TenantBoundModel):
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_plans')
    title            = models.CharField(max_length=255)
    subject          = models.CharField(max_length=100, blank=True, db_index=True)
    topic            = models.CharField(max_length=100, blank=True)
    subtopic         = models.CharField(max_length=100, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    objective        = models.TextField(blank=True)
    materials_needed = models.TextField(blank=True)
    introduction     = models.TextField(blank=True)
    main_content     = models.TextField(blank=True)
    activities       = models.TextField(blank=True)
    assessment       = models.TextField(blank=True)
    homework         = models.TextField(blank=True)
    status           = models.CharField(max_length=20, choices=LessonPlanStatus.choices, default=LessonPlanStatus.DRAFT, db_index=True)
    ai_suggestions   = models.TextField(blank=True)

    class Meta:
        db_table = 'teaching_lessonplan'
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['teacher', 'status'], name='idx_plan_teacher_status'),
            models.Index(fields=['school',  'status'], name='idx_plan_school_status'),
        ]

    def __str__(self):
        return f'{self.title} [{self.status}]'


class LessonPlanComment(TimeStampedModel):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson_plan = models.ForeignKey(LessonPlan, on_delete=models.CASCADE, related_name='comments')
    author      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_plan_comments')
    body        = models.TextField()

    class Meta:
        db_table = 'teaching_lessonplancomment'
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author} on {self.lesson_plan}'
