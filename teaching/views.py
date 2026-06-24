import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAnyAdmin, IsTeacher, IsStudent
from .models import (
    LessonDocument,
    LessonDocumentStatus,
    LessonDocumentVersion,
    LessonPlan,
    LessonPlanComment,
    LessonPlanStatus,
)
from .serializers import (
    AdminReviewLessonDocSerializer,
    AdminReviewSerializer,
    CreateLessonDocumentSerializer,
    CreateLessonPlanSerializer,
    LessonDocumentDetailSerializer,
    LessonDocumentListSerializer,
    LessonDocumentVersionSerializer,
    LessonPlanCommentSerializer,
    LessonPlanDetailSerializer,
    LessonPlanListSerializer,
    RegenerateSectionSerializer,
    UpdateLessonDocumentSerializer,
    UpdateLessonPlanSerializer,
)

logger = logging.getLogger(__name__)

# ── Editable states ───────────────────────────────────────────────────────────
EDITABLE_STATUSES = {LessonDocumentStatus.DRAFT, LessonDocumentStatus.REVISION_NEEDED}
SUBMITTABLE_STATUSES = {LessonDocumentStatus.DRAFT, LessonDocumentStatus.REVISION_NEEDED}
REVIEWABLE_STATUSES = {LessonDocumentStatus.SUBMITTED, LessonDocumentStatus.UNDER_REVIEW}


# ── Teacher: lesson document list / create ────────────────────────────────────

class LessonDocListCreateView(APIView):
    """GET/POST /api/v1/lesson-docs/"""

    def get_permissions(self):
        return [IsTeacher()]

    def get(self, request):
        qs = LessonDocument.objects.filter(teacher=request.user)
        doc_type = request.query_params.get('doc_type')
        status_  = request.query_params.get('status')
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        if status_:
            qs = qs.filter(status=status_)
        return Response(LessonDocumentListSerializer(qs, many=True).data)

    def post(self, request):
        ser = CreateLessonDocumentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        generation_mode = ser.validated_data.get('generation_mode', 'ai')

        doc = ser.save(
            teacher=request.user,
            school=request.user.school,
            status=LessonDocumentStatus.GENERATING if generation_mode == 'ai' else LessonDocumentStatus.DRAFT,
        )

        if generation_mode == 'ai':
            from .tasks import generate_lesson_document as gen_task
            task = gen_task.delay(str(doc.id))
            doc.ai_task_id = task.id
            doc.save(update_fields=['ai_task_id'])

        return Response(LessonDocumentDetailSerializer(doc).data, status=status.HTTP_201_CREATED)


# ── Teacher: lesson document detail ──────────────────────────────────────────

class LessonDocDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/lesson-docs/<id>/"""

    def get_permissions(self):
        return [IsTeacher()]

    def _own_doc(self, request, pk):
        try:
            return LessonDocument.objects.get(pk=pk, teacher=request.user)
        except LessonDocument.DoesNotExist:
            return None

    def get(self, request, pk):
        doc = self._own_doc(request, pk)
        if not doc:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonDocumentDetailSerializer(doc).data)

    def patch(self, request, pk):
        doc = self._own_doc(request, pk)
        if not doc:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.status not in EDITABLE_STATUSES:
            return Response(
                {'detail': f'Cannot edit a document with status "{doc.status}".'},
                status=status.HTTP_409_CONFLICT,
            )

        old_markdown = doc.content_markdown
        ser = UpdateLessonDocumentSerializer(doc, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()

        # Snapshot version if markdown changed
        if 'content_markdown' in request.data and request.data['content_markdown'] != old_markdown:
            last_version = doc.versions.first()
            next_number  = (last_version.version_number + 1) if last_version else 1
            LessonDocumentVersion.objects.create(
                document=doc,
                version_number=next_number,
                content_markdown=old_markdown,
                board_summary=doc.board_summary,
                saved_by=request.user,
            )

        doc.refresh_from_db()
        return Response(LessonDocumentDetailSerializer(doc).data)

    def delete(self, request, pk):
        doc = self._own_doc(request, pk)
        if not doc:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.status not in (LessonDocumentStatus.DRAFT, LessonDocumentStatus.REVISION_NEEDED):
            return Response(
                {'detail': 'Only DRAFT or REVISION_NEEDED documents can be deleted.'},
                status=status.HTTP_409_CONFLICT,
            )
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Teacher: submit for review ────────────────────────────────────────────────

class LessonDocSubmitView(APIView):
    """POST /api/v1/lesson-docs/<id>/submit/"""

    def get_permissions(self):
        return [IsTeacher()]

    def post(self, request, pk):
        try:
            doc = LessonDocument.objects.get(pk=pk, teacher=request.user)
        except LessonDocument.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if doc.status not in SUBMITTABLE_STATUSES:
            return Response(
                {'detail': f'Cannot submit a document with status "{doc.status}".'},
                status=status.HTTP_409_CONFLICT,
            )
        if not doc.content_markdown.strip():
            return Response(
                {'detail': 'Generate or write content before submitting.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc.status = LessonDocumentStatus.SUBMITTED
        doc.save(update_fields=['status', 'updated_at'])
        return Response(LessonDocumentDetailSerializer(doc).data)


# ── Teacher: regenerate section ───────────────────────────────────────────────

class LessonDocRegenerateSectionView(APIView):
    """POST /api/v1/lesson-docs/<id>/regenerate-section/"""

    def get_permissions(self):
        return [IsTeacher()]

    def post(self, request, pk):
        try:
            doc = LessonDocument.objects.select_related('school').get(pk=pk, teacher=request.user)
        except LessonDocument.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if doc.status not in EDITABLE_STATUSES:
            return Response(
                {'detail': 'Document must be in DRAFT or REVISION_NEEDED status.'},
                status=status.HTTP_409_CONFLICT,
            )

        ser = RegenerateSectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        section_heading = ser.validated_data['section_heading']
        instruction     = ser.validated_data['instruction']

        curriculum_type = getattr(doc.school, 'curriculum_type', 'nerdc')

        try:
            from ai_app.integrations import regenerate_lesson_section
            new_content = regenerate_lesson_section(
                full_markdown=doc.content_markdown,
                section_heading=section_heading,
                curriculum_type=curriculum_type,
                subject=doc.subject,
                topic=doc.topic,
                class_level=doc.class_level,
                instruction=instruction,
            )

            # Snapshot current version before replacing
            last_version = doc.versions.first()
            next_number  = (last_version.version_number + 1) if last_version else 1
            LessonDocumentVersion.objects.create(
                document=doc,
                version_number=next_number,
                content_markdown=doc.content_markdown,
                board_summary=doc.board_summary,
                saved_by=request.user,
                change_note=f'Regenerated section: {section_heading}',
            )

            # Splice the new section into the full markdown
            updated_markdown = _replace_section(doc.content_markdown, section_heading, new_content)
            doc.content_markdown = updated_markdown
            doc.save(update_fields=['content_markdown', 'updated_at'])

            return Response({
                'section_heading': section_heading,
                'new_content': new_content,
                'content_markdown': updated_markdown,
            })

        except Exception as exc:
            logger.exception('Section regeneration failed for doc %s: %s', pk, exc)
            return Response(
                {'detail': 'Section regeneration failed. Please try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


# ── Teacher: version history ──────────────────────────────────────────────────

class LessonDocVersionsView(APIView):
    """GET /api/v1/lesson-docs/<id>/versions/"""

    def get_permissions(self):
        return [IsTeacher()]

    def get(self, request, pk):
        try:
            doc = LessonDocument.objects.get(pk=pk, teacher=request.user)
        except LessonDocument.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        versions = doc.versions.all()
        return Response(LessonDocumentVersionSerializer(versions, many=True).data)


# ── Student: distributed lesson notes ────────────────────────────────────────

class DistributedLessonDocsView(APIView):
    """GET /api/v1/lesson-docs/distributed/ — lesson notes pushed to the student's class."""

    def get_permissions(self):
        return [IsStudent()]

    def get(self, request):
        student_class = getattr(request.user, 'student_class', None)
        if not student_class:
            return Response([])

        # Find all teachers in the same class who have distributed lesson notes
        qs = LessonDocument.objects.filter(
            school=request.user.school,
            doc_type='note',
            distributed_to_class=True,
            teacher__student_class=student_class,
        ).select_related('teacher')

        subject = request.query_params.get('subject')
        if subject:
            qs = qs.filter(subject=subject)

        return Response(LessonDocumentListSerializer(qs, many=True).data)


# ── Admin: lesson document review queue ──────────────────────────────────────

class AdminLessonDocListView(APIView):
    """GET /api/v1/admin/lesson-docs/"""

    def get_permissions(self):
        return [IsAnyAdmin()]

    def get(self, request):
        qs = LessonDocument.objects.exclude(
            status__in=[LessonDocumentStatus.DRAFT, LessonDocumentStatus.GENERATING]
        ).select_related('teacher')

        doc_type = request.query_params.get('doc_type')
        status_  = request.query_params.get('status')
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        if status_:
            qs = qs.filter(status=status_)

        return Response(LessonDocumentListSerializer(qs, many=True).data)


class AdminLessonDocDetailView(APIView):
    """GET /api/v1/admin/lesson-docs/<id>/"""

    def get_permissions(self):
        return [IsAnyAdmin()]

    def get(self, request, pk):
        try:
            doc = LessonDocument.objects.select_related('teacher').get(pk=pk)
        except LessonDocument.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonDocumentDetailSerializer(doc).data)


class AdminLessonDocReviewView(APIView):
    """POST /api/v1/admin/lesson-docs/<id>/review/"""

    def get_permissions(self):
        return [IsAnyAdmin()]

    def post(self, request, pk):
        try:
            doc = LessonDocument.objects.get(pk=pk)
        except LessonDocument.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if doc.status not in REVIEWABLE_STATUSES:
            return Response(
                {'detail': f'Cannot review a document with status "{doc.status}".'},
                status=status.HTTP_409_CONFLICT,
            )

        ser = AdminReviewLessonDocSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        action  = ser.validated_data['action']
        comment = ser.validated_data.get('comment', '').strip()

        if action == 'approve':
            doc.stamp_approval(request.user)
            if comment:
                doc.admin_comments = comment
            doc.save(update_fields=[
                'status', 'approved_by', 'approval_timestamp',
                'verification_hash', 'admin_comments', 'updated_at',
            ])

            # Auto-distribute lesson notes to the teacher's class
            if doc.doc_type == 'note':
                doc.distribute()
                doc.save(update_fields=['distributed_to_class', 'distributed_at', 'status', 'updated_at'])

        else:  # request_revision
            doc.status        = LessonDocumentStatus.REVISION_NEEDED
            doc.admin_comments = comment
            doc.save(update_fields=['status', 'admin_comments', 'updated_at'])

        doc.refresh_from_db()
        return Response(LessonDocumentDetailSerializer(doc).data)


# ── Helper ────────────────────────────────────────────────────────────────────

def _replace_section(full_markdown: str, section_heading: str, new_content: str) -> str:
    """
    Replace the content under `section_heading` in `full_markdown` with `new_content`.
    Finds the heading line, replaces everything until the next same-or-higher level heading.
    """
    lines = full_markdown.splitlines(keepends=True)
    heading_level = len(section_heading) - len(section_heading.lstrip('#'))
    start_idx = None

    for i, line in enumerate(lines):
        if line.strip() == section_heading.strip():
            start_idx = i
            break

    if start_idx is None:
        # Heading not found — append the new content
        return full_markdown.rstrip() + '\n\n' + new_content

    # Find the end of this section (next heading of same or higher level)
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            if level <= heading_level:
                end_idx = i
                break

    before = ''.join(lines[:start_idx])
    after  = ''.join(lines[end_idx:])
    return before + new_content.rstrip() + '\n\n' + after


# ── Legacy LessonPlan views (kept for backward compat) ────────────────────────

class LessonPlanListCreateView(APIView):
    """GET/POST /api/v1/lesson-plans/"""

    def get_permissions(self):
        return [IsTeacher()]

    def get(self, request):
        plans = LessonPlan.objects.filter(teacher=request.user)
        status_filter = request.query_params.get('status')
        if status_filter:
            plans = plans.filter(status=status_filter)
        return Response(LessonPlanListSerializer(plans, many=True).data)

    def post(self, request):
        ser = CreateLessonPlanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        plan = ser.save(teacher=request.user, school=request.user.school)
        return Response(LessonPlanDetailSerializer(plan).data, status=status.HTTP_201_CREATED)


class LessonPlanDetailView(APIView):
    """GET/PATCH /api/v1/lesson-plans/<id>/"""

    def get_permissions(self):
        return [IsTeacher()]

    def _get_own_plan(self, request, pk):
        try:
            return LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return None

    def get(self, request, pk):
        plan = self._get_own_plan(request, pk)
        if not plan:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonPlanDetailSerializer(plan).data)

    def patch(self, request, pk):
        plan = self._get_own_plan(request, pk)
        if not plan:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        if plan.status not in (LessonPlanStatus.DRAFT, LessonPlanStatus.REVISION_NEEDED):
            return Response({'detail': 'Only DRAFT or REVISION_NEEDED plans can be edited.'}, status=status.HTTP_409_CONFLICT)
        ser = UpdateLessonPlanSerializer(plan, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        plan.refresh_from_db()
        return Response(LessonPlanDetailSerializer(plan).data)

    def delete(self, request, pk):
        plan = self._get_own_plan(request, pk)
        if not plan:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        if plan.status != LessonPlanStatus.DRAFT:
            return Response({'detail': 'Only DRAFT plans can be deleted.'}, status=status.HTTP_409_CONFLICT)
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmitLessonPlanView(APIView):
    def get_permissions(self):
        return [IsTeacher()]

    def post(self, request, pk):
        try:
            plan = LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if plan.status not in (LessonPlanStatus.DRAFT, LessonPlanStatus.REVISION_NEEDED):
            return Response({'detail': 'Cannot submit.'}, status=status.HTTP_409_CONFLICT)
        plan.status = LessonPlanStatus.SUBMITTED
        plan.save(update_fields=['status', 'updated_at'])
        return Response(LessonPlanDetailSerializer(plan).data)


class AIAssistView(APIView):
    def get_permissions(self):
        return [IsTeacher()]

    def post(self, request, pk):
        try:
            plan = LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        plan_text = _format_plan_for_ai(plan)
        if not plan_text.strip():
            return Response({'detail': 'Add content first.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from ai_app.integrations import generate_lesson_suggestions
            result = generate_lesson_suggestions(
                plan_text=plan_text,
                subject_context=f'Subject: {plan.subject} | Topic: {plan.topic}' if plan.subject else '',
            )
            plan.ai_suggestions = result.suggestions
            plan.save(update_fields=['ai_suggestions', 'updated_at'])
            return Response({'ai_suggestions': result.suggestions})
        except Exception as exc:
            logger.exception('AI assist failed: %s', exc)
            return Response({'detail': 'AI suggestions failed.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class LessonPlanCommentsView(APIView):
    def get_permissions(self):
        return [IsTeacher()]

    def get(self, request, pk):
        try:
            plan = LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonPlanCommentSerializer(plan.comments.all(), many=True).data)


class AdminLessonPlanListView(APIView):
    def get_permissions(self):
        return [IsAnyAdmin()]

    def get(self, request):
        plans = LessonPlan.objects.exclude(status=LessonPlanStatus.DRAFT).select_related('teacher')
        status_filter = request.query_params.get('status')
        if status_filter:
            plans = plans.filter(status=status_filter)
        return Response(LessonPlanListSerializer(plans, many=True).data)


class AdminLessonPlanReviewView(APIView):
    def get_permissions(self):
        return [IsAnyAdmin()]

    def _get_plan(self, request, pk):
        try:
            return LessonPlan.objects.get(pk=pk)
        except LessonPlan.DoesNotExist:
            return None

    def get(self, request, pk):
        plan = self._get_plan(request, pk)
        if not plan:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonPlanDetailSerializer(plan).data)

    def patch(self, request, pk):
        plan = self._get_plan(request, pk)
        if not plan:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if plan.status not in (LessonPlanStatus.SUBMITTED, LessonPlanStatus.UNDER_REVIEW):
            return Response({'detail': 'Cannot review.'}, status=status.HTTP_409_CONFLICT)
        ser = AdminReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action  = ser.validated_data['action']
        comment = ser.validated_data.get('comment', '').strip()
        plan.status = LessonPlanStatus.APPROVED if action == 'approve' else LessonPlanStatus.REVISION_NEEDED
        plan.save(update_fields=['status', 'updated_at'])
        if comment:
            LessonPlanComment.objects.create(lesson_plan=plan, author=request.user, body=comment)
        plan.refresh_from_db()
        return Response(LessonPlanDetailSerializer(plan).data)


def _format_plan_for_ai(plan: LessonPlan) -> str:
    sections = [
        ('Title', plan.title), ('Subject', plan.subject), ('Topic', plan.topic),
        ('Objective', plan.objective), ('Introduction', plan.introduction),
        ('Main Content', plan.main_content), ('Assessment', plan.assessment),
    ]
    return '\n\n'.join(f'**{label}**\n{value}' for label, value in sections if value.strip())
