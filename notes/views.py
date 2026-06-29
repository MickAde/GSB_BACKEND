import logging
import uuid as uuid_lib

from django.db import transaction
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView, DestroyAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from drf_spectacular.utils import (
    extend_schema, extend_schema_view,
    OpenApiResponse, OpenApiParameter, inline_serializer,
)
from rest_framework import serializers as drf_serializers

from core.pagination import StandardResultsPagination
from core.permissions import IsAnyAdmin, IsStudent, IsTeacher, IsVisitor
from .models import NoteConformityReport, NoteStatus, NoteType, NoteUpload
from .serializers import (
    BulkUploadResponseSerializer,
    ConfirmOCRSerializer,
    ConformityReportCreateSerializer,
    ConformityReportSerializer,
    ConformityReportStatusSerializer,
    NoteDetailSerializer,
    NoteListSerializer,
    NoteStatusSerializer,
    NoteUpdateSerializer,
    NoteUploadRequestSerializer,
    SchoolNoteListSerializer,
)

logger = logging.getLogger(__name__)


class AIRateThrottle(UserRateThrottle):
    scope = 'ai_generation'


# ── Shared upload helper ──────────────────────────────────────

def _store_file(user, file_obj) -> str:
    """Uploads file to Supabase Storage (prod) or local media (dev). Returns URL."""
    from django.conf import settings

    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
        from core.storage import storage
        school_prefix = str(user.school_id) if user.school_id else 'visitors'
        path = f'{school_prefix}/{uuid_lib.uuid4()}-{file_obj.name}'
        file_data = file_obj.read()
        return storage.upload(settings.SUPABASE_NOTES_BUCKET, path, file_data)

    from django.core.files.storage import default_storage
    saved_path = default_storage.save(f'notes/{uuid_lib.uuid4()}-{file_obj.name}', file_obj)
    return default_storage.url(saved_path)


def _dispatch_ocr(note_id) -> str:
    from .tasks import run_ocr_pipeline
    result = run_ocr_pipeline.apply_async(args=[str(note_id)], queue='celery_ocr')
    return result.id


def _dispatch_ai(note_id, task_id: str | None = None) -> str:
    from ai_app.tasks import run_ai_summary
    kwargs = {'args': [str(note_id)], 'queue': 'celery_ai'}
    if task_id:
        kwargs['task_id'] = task_id
    result = run_ai_summary.apply_async(**kwargs)
    return result.id


def _safe_dispatch_ai(note_id: str, task_id: str) -> None:
    """
    Dispatches the AI summary task after the DB transaction commits.

    In production (real Celery workers) apply_async() returns instantly and the
    202 is already on its way to the client.  In dev (TASK_ALWAYS_EAGER=True)
    Celery runs the task synchronously, which would block the response for 60 s+.
    We avoid that by running the eager call in a daemon thread so the HTTP
    response is returned immediately and the frontend can start polling.
    """
    from django.conf import settings

    def _run():
        try:
            _dispatch_ai(note_id, task_id)
        except Exception as exc:
            logger.error('AI dispatch failed for note %s: %s', note_id, exc)
            from .models import NoteUpload, NoteStatus
            NoteUpload.unscoped.filter(pk=note_id).update(
                status=NoteStatus.FAILED,
                error_message=f'AI summary could not start: {exc}',
            )

    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        import threading
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()


# ── 1. Single file upload ─────────────────────────────────────

@extend_schema(tags=['Notes'])
class NoteUploadView(APIView):
    """
    POST /api/v1/notes/upload/

    Uploads a single note file (PDF, image, voice, or typed text).
    File is stored in Supabase Storage and the OCR pipeline is triggered asynchronously.

    **Allowed roles:** STUDENT, TEACHER
    *(Visitors are not permitted — they have no school association.)*

    Returns 202 Accepted — poll `GET /api/v1/notes/{id}/status/` for progress.

    **Status flow:**
    `PENDING_OCR` → `AWAITING_STUDENT_APPROVAL` → `PROCESSING_AI` → `READY`

    > Typed text notes (`note_type=text`) skip OCR and go straight to
    > `AWAITING_STUDENT_APPROVAL`.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Visitors are excluded: NoteUpload.school is non-nullable (TenantBoundModel),
        # and Visitor accounts have school=None.
        return [(IsStudent | IsTeacher)()]

    @extend_schema(
        summary='Upload a single note',
        request={'multipart/form-data': NoteUploadRequestSerializer},
        responses={
            202: inline_serializer(
                name='UploadAccepted',
                fields={
                    'note_id': drf_serializers.UUIDField(),
                    'task_id': drf_serializers.CharField(),
                    'status':  drf_serializers.CharField(),
                },
            ),
            400: OpenApiResponse(description='Validation error (file too large, wrong type)'),
        },
    )
    def post(self, request):
        data = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        data['file'] = request.FILES.get('file')
        serializer = NoteUploadRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        file_obj  = data['file']
        note_type = data['note_type']

        file_url = _store_file(request.user, file_obj)

        note = NoteUpload.objects.create(
            owner        = request.user,
            school       = request.user.school,
            file_url     = file_url,
            file_name    = file_obj.name,
            note_type    = note_type,
            file_size_bytes = file_obj.size,
            subject      = data.get('subject', ''),
            topic        = data.get('topic', ''),
            subtopic     = data.get('subtopic', ''),
            status       = NoteStatus.PENDING_OCR,
        )

        # Typed notes skip OCR — go straight to AWAITING_APPROVAL
        if note_type == NoteType.TEXT:
            note.raw_ocr_text = ''
            note.status = NoteStatus.AWAITING_APPROVAL
            note.save(update_fields=['raw_ocr_text', 'status'])
            task_id = ''
        else:
            try:
                task_id = _dispatch_ocr(note.id)
                note.ocr_task_id = task_id
                note.save(update_fields=['ocr_task_id'])
            except Exception as exc:
                logger.error('Could not dispatch OCR task for note %s: %s', note.id, exc)
                task_id = ''

        return Response(
            {'note_id': str(note.id), 'task_id': task_id, 'status': note.status},
            status=status.HTTP_202_ACCEPTED,
        )


# ── 2. Bulk upload ────────────────────────────────────────────

@extend_schema(tags=['Notes'])
class NoteBulkUploadView(APIView):
    """
    POST /api/v1/notes/upload/bulk/

    Upload multiple files in a single request. Each file is processed independently.
    Returns a 207 Multi-Status response with a summary of successes and failures.

    **Allowed roles:** STUDENT, TEACHER
    *(Visitors are not permitted — they have no school association.)*
    """
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        # Visitors are excluded: NoteUpload.school is non-nullable (TenantBoundModel).
        return [(IsStudent | IsTeacher)()]

    @extend_schema(
        summary='Upload multiple notes at once',
        request={
            'multipart/form-data': inline_serializer(
                name='BulkUploadForm',
                fields={
                    'files':     drf_serializers.ListField(child=drf_serializers.FileField()),
                    'note_type': drf_serializers.ChoiceField(choices=NoteType.choices),
                    'subject':   drf_serializers.CharField(required=False),
                    'topic':     drf_serializers.CharField(required=False),
                    'subtopic':  drf_serializers.CharField(required=False),
                },
            )
        },
        responses={
            207: BulkUploadResponseSerializer,
            400: OpenApiResponse(description='No files provided'),
        },
    )
    def post(self, request):
        files     = request.FILES.getlist('files')
        note_type = request.data.get('note_type', 'image')
        subject   = request.data.get('subject', '')
        topic     = request.data.get('topic', '')
        subtopic  = request.data.get('subtopic', '')

        if not files:
            return Response(
                {'error_code': 'NO_FILES', 'detail': 'No files provided.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded = []
        failed   = []

        for file_obj in files:
            try:
                serializer = NoteUploadRequestSerializer(
                    data={'file': file_obj, 'note_type': note_type,
                          'subject': subject, 'topic': topic, 'subtopic': subtopic}
                )
                if not serializer.is_valid():
                    failed.append({'filename': file_obj.name, 'error': str(serializer.errors)})
                    continue

                file_url = _store_file(request.user, file_obj)

                note = NoteUpload.objects.create(
                    owner           = request.user,
                    school          = request.user.school,
                    file_url        = file_url,
                    file_name       = file_obj.name,
                    note_type       = note_type,
                    file_size_bytes = file_obj.size,
                    subject         = subject,
                    topic           = topic,
                    subtopic        = subtopic,
                    status          = NoteStatus.PENDING_OCR if note_type != NoteType.TEXT else NoteStatus.AWAITING_APPROVAL,
                )

                if note_type != NoteType.TEXT:
                    task_id = _dispatch_ocr(note.id)
                    note.ocr_task_id = task_id
                    note.save(update_fields=['ocr_task_id'])

                uploaded.append(note)

            except Exception as exc:
                logger.exception('Bulk upload failed for file %s: %s', file_obj.name, exc)
                failed.append({'filename': file_obj.name, 'error': str(exc)})

        response_status = status.HTTP_207_MULTI_STATUS if failed else status.HTTP_202_ACCEPTED
        return Response(
            {
                'uploaded': NoteListSerializer(uploaded, many=True).data,
                'failed':   failed,
            },
            status=response_status,
        )


# ── 3. Note list ──────────────────────────────────────────────

@extend_schema(
    tags=['Notes'],
    summary='List my notes',
    description='Returns all notes owned by the authenticated user. Supports filtering and search.',
    parameters=[
        OpenApiParameter('status',   description='Filter by status (PENDING_OCR, AWAITING_STUDENT_APPROVAL, PROCESSING_AI, READY, FAILED)'),
        OpenApiParameter('subject',  description='Filter by subject'),
        OpenApiParameter('search',   description='Search in file_name, subject, topic'),
        OpenApiParameter('ordering', description='Order by created_at or -created_at'),
    ],
)
class NoteListView(ListAPIView):
    """GET /api/v1/notes/"""
    serializer_class = NoteListSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'note_type', 'subject']
    search_fields    = ['file_name', 'subject', 'topic', 'subtopic']
    ordering_fields  = ['created_at', 'updated_at', 'subject']
    ordering         = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return NoteUpload.objects.none()
        return NoteUpload.objects.filter(owner=self.request.user)


# ── 4. Note detail ────────────────────────────────────────────

@extend_schema(
    tags=['Notes'],
    summary='Get full note detail',
    description='Returns the complete note record including raw OCR text and AI summaries.',
    responses={200: NoteDetailSerializer, 404: OpenApiResponse(description='Not found')},
)
class NoteDetailView(RetrieveAPIView):
    """GET /api/v1/notes/{pk}/"""
    serializer_class = NoteDetailSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return NoteUpload.objects.none()
        return NoteUpload.objects.filter(owner=self.request.user)


# ── 5. Status polling ─────────────────────────────────────────

@extend_schema(
    tags=['Notes'],
    summary='Poll note processing status',
    description=(
        'Lightweight endpoint for the frontend to poll until status is READY or FAILED. '
        'Cheaper than fetching the full detail every time.'
    ),
    responses={200: NoteStatusSerializer, 404: OpenApiResponse(description='Not found')},
)
class NoteStatusView(RetrieveAPIView):
    """GET /api/v1/notes/{pk}/status/"""
    serializer_class = NoteStatusSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return NoteUpload.objects.none()
        return NoteUpload.objects.filter(owner=self.request.user)


# ── 6. Confirm OCR ────────────────────────────────────────────

@extend_schema(tags=['Notes'])
class NoteConfirmOCRView(APIView):
    """
    POST /api/v1/notes/{pk}/confirm-ocr/

    Student has reviewed the extracted OCR text, corrected any errors, and confirms it.
    This saves the corrected text and triggers the Claude AI summarisation pipeline.

    The note **must** be in `AWAITING_STUDENT_APPROVAL` state.
    """
    throttle_classes = [AIRateThrottle]

    @extend_schema(
        summary='Confirm OCR text and trigger AI summary',
        request=ConfirmOCRSerializer,
        responses={
            202: inline_serializer(
                name='ConfirmAccepted',
                fields={
                    'note_id': drf_serializers.UUIDField(),
                    'task_id': drf_serializers.CharField(),
                    'status':  drf_serializers.CharField(),
                },
            ),
            404: OpenApiResponse(description='Note not found'),
            409: OpenApiResponse(description='Note is not awaiting approval'),
        },
    )
    def post(self, request, pk):
        try:
            note = NoteUpload.objects.get(pk=pk, owner=request.user)
        except NoteUpload.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Note not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )

        retryable = {NoteStatus.AWAITING_APPROVAL, NoteStatus.FAILED}
        if note.status not in retryable:
            return Response(
                {
                    'error_code': 'INVALID_STATE',
                    'detail': f'Cannot confirm OCR — note is currently in "{note.status}" state.',
                    'status_code': 409,
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = ConfirmOCRSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Pre-generate the task ID so it can be saved atomically with the status
        # change and returned in the response, without a second save outside the
        # transaction.
        task_id = str(uuid_lib.uuid4())

        with transaction.atomic():
            note.raw_ocr_text = serializer.validated_data['confirmed_text']
            note.status       = NoteStatus.PROCESSING_AI
            note.ai_task_id   = task_id
            note.save(update_fields=['raw_ocr_text', 'status', 'ai_task_id', 'updated_at'])
            # Dispatch only after the transaction commits so the worker never reads
            # a note that is still mid-transition.
            transaction.on_commit(lambda: _safe_dispatch_ai(str(note.id), task_id))

        return Response(
            {'note_id': str(note.id), 'task_id': task_id, 'status': NoteStatus.PROCESSING_AI},
            status=status.HTTP_202_ACCEPTED,
        )


# ── 7. Update metadata ────────────────────────────────────────

@extend_schema(tags=['Notes'])
class NoteUpdateView(APIView):
    """
    PATCH /api/v1/notes/{pk}/

    Update subject, topic, or subtopic on an existing note.
    """

    @extend_schema(
        summary='Update note metadata (subject/topic/subtopic)',
        request=NoteUpdateSerializer,
        responses={200: NoteListSerializer},
    )
    def patch(self, request, pk):
        try:
            note = NoteUpload.objects.get(pk=pk, owner=request.user)
        except NoteUpload.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Note not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = NoteUpdateSerializer(note, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(NoteListSerializer(note).data)


# ── 8. Delete note ────────────────────────────────────────────

@extend_schema(
    tags=['Notes'],
    summary='Delete a note',
    responses={
        204: OpenApiResponse(description='Deleted'),
        404: OpenApiResponse(description='Not found'),
    },
)
class NoteDeleteView(DestroyAPIView):
    """DELETE /api/v1/notes/{pk}/"""

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return NoteUpload.objects.none()
        return NoteUpload.objects.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        # Attempt to remove the file from storage
        if instance.file_url:
            try:
                _delete_from_storage(instance.file_url)
            except Exception as exc:
                logger.warning('Could not delete file from storage for note %s: %s', instance.id, exc)
        instance.delete()


def _delete_from_storage(file_url: str):
    from django.conf import settings
    if settings.SUPABASE_URL and file_url.startswith('http'):
        from core.storage import storage
        # Extract the path after the bucket name
        parts = file_url.split(f'/{settings.SUPABASE_NOTES_BUCKET}/')
        if len(parts) == 2:
            storage.delete(settings.SUPABASE_NOTES_BUCKET, [parts[1]])


# ── 9. Browse school notes (teacher / admin) ─────────────────

@extend_schema(tags=['Notes'])
class SchoolNoteListView(APIView):
    """
    GET /api/v1/notes/school/

    Paginated list of all notes in the school.  Needed by teachers before
    creating a conformity report — they can browse student notes, filter by
    owner or subject, and pick the note they want to assess.

    **Allowed roles:** TEACHER, MAIN_ADMIN, SUB_ADMIN
    """

    def get_permissions(self):
        return [(IsTeacher | IsAnyAdmin)()]

    @extend_schema(
        summary='Browse all school notes (teacher / admin)',
        parameters=[
            OpenApiParameter('owner',     description='Filter by owner UUID'),
            OpenApiParameter('subject',   description='Filter by subject (case-insensitive contains)'),
            OpenApiParameter('status',    description='Filter by pipeline status'),
            OpenApiParameter('note_type', description='Filter by note type (pdf / image / voice / text)'),
            OpenApiParameter('search',    description='Search file_name, subject, topic'),
        ],
        responses={200: SchoolNoteListSerializer(many=True)},
    )
    def get(self, request):
        from django.db.models import Q
        qs = NoteUpload.objects.select_related('owner').order_by('-created_at')

        owner = request.query_params.get('owner', '').strip()
        if owner:
            qs = qs.filter(owner_id=owner)

        subject = request.query_params.get('subject', '').strip()
        if subject:
            qs = qs.filter(subject__icontains=subject)

        note_status = request.query_params.get('status', '').strip()
        if note_status:
            qs = qs.filter(status=note_status)

        note_type = request.query_params.get('note_type', '').strip()
        if note_type:
            qs = qs.filter(note_type=note_type)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(file_name__icontains=search)
                | Q(subject__icontains=search)
                | Q(topic__icontains=search)
            )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(SchoolNoteListSerializer(page, many=True).data)
        return Response(SchoolNoteListSerializer(qs, many=True).data)


# ── 10. Replace note file ────────────────────────────────────

@extend_schema(tags=['Notes'])
class NoteReplaceView(APIView):
    """
    POST /api/v1/notes/{pk}/replace/

    Replace the uploaded file on an existing note.  The old file is removed
    from storage and all pipeline output (OCR text, AI summaries) is cleared.
    The processing pipeline restarts from the beginning.

    **Allowed roles:** STUDENT, TEACHER (owner only)

    Returns 202 Accepted — poll `GET /api/v1/notes/{id}/status/` for progress.
    """
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        return [(IsStudent | IsTeacher)()]

    @extend_schema(
        summary='Replace note file and restart pipeline',
        request={'multipart/form-data': NoteUploadRequestSerializer},
        responses={
            202: inline_serializer(
                name='ReplaceAccepted',
                fields={
                    'note_id': drf_serializers.UUIDField(),
                    'task_id': drf_serializers.CharField(),
                    'status':  drf_serializers.CharField(),
                },
            ),
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='Note not found'),
        },
    )
    def post(self, request, pk):
        try:
            note = NoteUpload.objects.get(pk=pk, owner=request.user)
        except NoteUpload.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Note not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        data['file'] = request.FILES.get('file')
        serializer = NoteUploadRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        data      = serializer.validated_data
        file_obj  = data['file']
        note_type = data['note_type']

        if note.file_url:
            try:
                _delete_from_storage(note.file_url)
            except Exception as exc:
                logger.warning('Could not delete old file for note %s: %s', note.id, exc)

        file_url = _store_file(request.user, file_obj)

        # Clear all pipeline output
        note.file_url             = file_url
        note.file_name            = file_obj.name
        note.note_type            = note_type
        note.file_size_bytes      = file_obj.size
        note.subject              = data.get('subject', note.subject)
        note.topic                = data.get('topic', note.topic)
        note.subtopic             = data.get('subtopic', note.subtopic)
        note.raw_ocr_text         = ''
        note.ai_summary_paragraph = ''
        note.ai_bullet_points     = []
        note.ai_key_points        = []
        note.error_message        = ''
        note.ocr_task_id          = ''
        note.ai_task_id           = ''

        update_fields = [
            'file_url', 'file_name', 'note_type', 'file_size_bytes',
            'subject', 'topic', 'subtopic',
            'raw_ocr_text', 'ai_summary_paragraph', 'ai_bullet_points', 'ai_key_points',
            'error_message', 'ocr_task_id', 'ai_task_id', 'status', 'updated_at',
        ]

        if note_type == NoteType.TEXT:
            note.status = NoteStatus.AWAITING_APPROVAL
            note.save(update_fields=update_fields)
            task_id = ''
        else:
            note.status = NoteStatus.PENDING_OCR
            note.save(update_fields=update_fields)
            try:
                task_id = _dispatch_ocr(note.id)
                note.ocr_task_id = task_id
                note.save(update_fields=['ocr_task_id'])
            except Exception as exc:
                logger.error('Could not dispatch OCR task for note %s: %s', note.id, exc)
                task_id = ''

        logger.info('User %s replaced file on note %s.', request.user.id, note.id)
        return Response(
            {'note_id': str(note.id), 'task_id': task_id, 'status': note.status},
            status=status.HTTP_202_ACCEPTED,
        )


# ── 11. Conformity reports ────────────────────────────────────

@extend_schema(tags=['Notes — Conformity'])
class NoteConformityListCreateView(APIView):
    """
    GET  /api/v1/notes/conformity/  — List conformity reports.
    POST /api/v1/notes/conformity/  — Create a new conformity report.

    **Allowed roles (GET):**  TEACHER (their own reports), MAIN_ADMIN / SUB_ADMIN (all school reports)
    **Allowed roles (POST):** TEACHER only — they are the assessor.

    Creating a report dispatches an async AI task.
    Poll `GET /api/v1/notes/conformity/{id}/status/` until `status` is `DONE` or `FAILED`.
    """

    def get_permissions(self):
        return [(IsTeacher | IsAnyAdmin)()]

    @extend_schema(
        summary='List conformity reports',
        responses={200: ConformityReportSerializer(many=True)},
    )
    def get(self, request):
        from users.models import UserRole
        qs = NoteConformityReport.objects.select_related(
            'student_note__owner', 'teacher_note'
        ).order_by('-generated_at')

        if request.user.role == UserRole.TEACHER:
            qs = qs.filter(teacher_note__owner=request.user)

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(ConformityReportSerializer(page, many=True).data)
        return Response(ConformityReportSerializer(qs, many=True).data)

    @extend_schema(
        summary='Create a conformity report (async)',
        request=ConformityReportCreateSerializer,
        responses={
            202: inline_serializer(
                name='ConformityCreateAccepted',
                fields={
                    'report_id': drf_serializers.UUIDField(),
                    'task_id':   drf_serializers.CharField(),
                    'status':    drf_serializers.CharField(),
                },
            ),
            403: OpenApiResponse(description='Only TEACHER can create conformity reports'),
            404: OpenApiResponse(description='Note not found or not READY'),
            409: OpenApiResponse(description='Note is not in READY state'),
        },
    )
    def post(self, request):
        from users.models import UserRole
        if request.user.role != UserRole.TEACHER:
            return Response(
                {'error_code': 'FORBIDDEN', 'detail': 'Only teachers can create conformity reports.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ConformityReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student_note_id = serializer.validated_data['student_note_id']
        teacher_note_id = serializer.validated_data['teacher_note_id']

        # Student note must exist in the school and be READY
        try:
            student_note = NoteUpload.objects.get(pk=student_note_id)
        except NoteUpload.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Student note not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        if student_note.status != NoteStatus.READY:
            return Response(
                {'error_code': 'INVALID_STATE', 'detail': 'Student note must be in READY state.', 'status_code': 409},
                status=status.HTTP_409_CONFLICT,
            )

        # Teacher note must belong to the requesting teacher and be READY
        try:
            teacher_note = NoteUpload.objects.get(pk=teacher_note_id, owner=request.user)
        except NoteUpload.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Teacher note not found or does not belong to you.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        if teacher_note.status != NoteStatus.READY:
            return Response(
                {'error_code': 'INVALID_STATE', 'detail': 'Teacher note must be in READY state.', 'status_code': 409},
                status=status.HTTP_409_CONFLICT,
            )

        report = NoteConformityReport.objects.create(
            school=request.user.school,
            student_note=student_note,
            teacher_note=teacher_note,
        )

        from ai_app.tasks import run_conformity_analysis
        celery_result = run_conformity_analysis.apply_async(args=[str(report.id)], queue='celery_ai')
        report.ai_task_id = celery_result.id
        report.save(update_fields=['ai_task_id'])

        logger.info('Teacher %s created conformity report %s.', request.user.id, report.id)
        return Response(
            {'report_id': str(report.id), 'task_id': celery_result.id, 'status': report.status},
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(tags=['Notes — Conformity'])
class NoteConformityDetailView(APIView):
    """
    GET /api/v1/notes/conformity/{pk}/

    Full conformity report — conformity percentage, similarity analysis, and current status.

    **Allowed roles:** TEACHER (reports they created), MAIN_ADMIN, SUB_ADMIN
    """

    def get_permissions(self):
        return [(IsTeacher | IsAnyAdmin)()]

    @extend_schema(
        summary='Get conformity report detail',
        responses={
            200: ConformityReportSerializer,
            404: OpenApiResponse(description='Not found'),
        },
    )
    def get(self, request, pk):
        from users.models import UserRole
        qs = NoteConformityReport.objects.select_related('student_note__owner', 'teacher_note')
        if request.user.role == UserRole.TEACHER:
            qs = qs.filter(teacher_note__owner=request.user)
        try:
            report = qs.get(pk=pk)
        except NoteConformityReport.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Conformity report not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ConformityReportSerializer(report).data)


@extend_schema(tags=['Notes — Conformity'])
class NoteConformityStatusView(APIView):
    """
    GET /api/v1/notes/conformity/{pk}/status/

    Poll the AI generation status of a conformity report.
    Returns status plus `conformity_percentage` when DONE.

    **Allowed roles:** TEACHER (reports they created), MAIN_ADMIN, SUB_ADMIN
    """

    def get_permissions(self):
        return [(IsTeacher | IsAnyAdmin)()]

    @extend_schema(
        summary='Poll conformity report status',
        responses={
            200: ConformityReportStatusSerializer,
            404: OpenApiResponse(description='Not found'),
        },
    )
    def get(self, request, pk):
        from users.models import UserRole
        qs = NoteConformityReport.objects.all()
        if request.user.role == UserRole.TEACHER:
            qs = qs.filter(teacher_note__owner=request.user)
        try:
            report = qs.get(pk=pk)
        except NoteConformityReport.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Conformity report not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ConformityReportStatusSerializer(report).data)
