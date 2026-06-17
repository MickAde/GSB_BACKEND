import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from core.permissions import IsAnyAdmin, IsTeacher
from .models import LessonPlan, LessonPlanComment, LessonPlanStatus
from .serializers import (
    AdminReviewSerializer,
    CreateLessonPlanSerializer,
    LessonPlanDetailSerializer,
    LessonPlanListSerializer,
    UpdateLessonPlanSerializer,
)

logger = logging.getLogger(__name__)


# ── Teacher views ─────────────────────────────────────────────

class LessonPlanListCreateView(APIView):
    """GET/POST /api/v1/lesson-plans/"""

    def get_permissions(self):
        return [IsTeacher()]

    @extend_schema(responses={200: LessonPlanListSerializer(many=True)})
    def get(self, request):
        plans = LessonPlan.objects.filter(teacher=request.user)
        status_filter = request.query_params.get('status')
        if status_filter:
            plans = plans.filter(status=status_filter)
        return Response(LessonPlanListSerializer(plans, many=True).data)

    @extend_schema(request=CreateLessonPlanSerializer, responses={201: LessonPlanDetailSerializer})
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

    @extend_schema(responses={200: LessonPlanDetailSerializer})
    def get(self, request, pk):
        plan = self._get_own_plan(request, pk)
        if not plan:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonPlanDetailSerializer(plan).data)

    @extend_schema(request=UpdateLessonPlanSerializer, responses={200: LessonPlanDetailSerializer})
    def patch(self, request, pk):
        plan = self._get_own_plan(request, pk)
        if not plan:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        if plan.status not in (LessonPlanStatus.DRAFT, LessonPlanStatus.REVISION_NEEDED):
            return Response(
                {'detail': 'Only DRAFT or REVISION_NEEDED plans can be edited.'},
                status=status.HTTP_409_CONFLICT,
            )
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
            return Response(
                {'detail': 'Only DRAFT plans can be deleted.'},
                status=status.HTTP_409_CONFLICT,
            )
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmitLessonPlanView(APIView):
    """POST /api/v1/lesson-plans/<id>/submit/"""

    def get_permissions(self):
        return [IsTeacher()]

    def post(self, request, pk):
        try:
            plan = LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)

        if plan.status not in (LessonPlanStatus.DRAFT, LessonPlanStatus.REVISION_NEEDED):
            return Response(
                {'detail': 'Only DRAFT or REVISION_NEEDED plans can be submitted.'},
                status=status.HTTP_409_CONFLICT,
            )

        plan.status = LessonPlanStatus.SUBMITTED
        plan.save(update_fields=['status', 'updated_at'])
        return Response(LessonPlanDetailSerializer(plan).data)


class AIAssistView(APIView):
    """POST /api/v1/lesson-plans/<id>/ai-assist/ — synchronous AI suggestions."""

    def get_permissions(self):
        return [IsTeacher()]

    def post(self, request, pk):
        try:
            plan = LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)

        plan_text = _format_plan_for_ai(plan)
        if not plan_text.strip():
            return Response(
                {'detail': 'Add some content to your lesson plan before requesting AI suggestions.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from ai_app.integrations import generate_lesson_suggestions

            subject_context = ''
            if plan.subject:
                subject_context = f'Subject: {plan.subject}'
                if plan.topic:
                    subject_context += f' | Topic: {plan.topic}'

            result = generate_lesson_suggestions(
                plan_text=plan_text,
                subject_context=subject_context,
            )

            plan.ai_suggestions = result.suggestions
            plan.save(update_fields=['ai_suggestions', 'updated_at'])

            return Response({'ai_suggestions': result.suggestions})

        except Exception as exc:
            logger.exception('AI assist failed for lesson plan %s: %s', pk, exc)
            return Response(
                {'detail': 'AI suggestions failed. Please try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class LessonPlanCommentsView(APIView):
    """GET /api/v1/lesson-plans/<id>/comments/"""

    def get_permissions(self):
        return [IsTeacher()]

    def get(self, request, pk):
        try:
            plan = LessonPlan.objects.get(pk=pk, teacher=request.user)
        except LessonPlan.DoesNotExist:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        from .serializers import LessonPlanCommentSerializer
        return Response(LessonPlanCommentSerializer(plan.comments.all(), many=True).data)


# ── Admin views ───────────────────────────────────────────────

class AdminLessonPlanListView(APIView):
    """GET /api/v1/admin/lesson-plans/ — admin review queue."""

    def get_permissions(self):
        return [IsAnyAdmin()]

    def get(self, request):
        plans = LessonPlan.objects.exclude(status=LessonPlanStatus.DRAFT).select_related('teacher')
        status_filter = request.query_params.get('status')
        if status_filter:
            plans = plans.filter(status=status_filter)
        return Response(LessonPlanListSerializer(plans, many=True).data)


class AdminLessonPlanReviewView(APIView):
    """GET/PATCH /api/v1/admin/lesson-plans/<id>/review/"""

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
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LessonPlanDetailSerializer(plan).data)

    @extend_schema(request=AdminReviewSerializer)
    def patch(self, request, pk):
        plan = self._get_plan(request, pk)
        if not plan:
            return Response({'detail': 'Lesson plan not found.'}, status=status.HTTP_404_NOT_FOUND)

        if plan.status not in (LessonPlanStatus.SUBMITTED, LessonPlanStatus.UNDER_REVIEW):
            return Response(
                {'detail': 'Only SUBMITTED or UNDER_REVIEW plans can be reviewed.'},
                status=status.HTTP_409_CONFLICT,
            )

        ser = AdminReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        action  = ser.validated_data['action']
        comment = ser.validated_data.get('comment', '').strip()

        new_status = (
            LessonPlanStatus.APPROVED
            if action == 'approve'
            else LessonPlanStatus.REVISION_NEEDED
        )
        plan.status = new_status
        plan.save(update_fields=['status', 'updated_at'])

        if comment:
            LessonPlanComment.objects.create(
                lesson_plan=plan,
                author=request.user,
                body=comment,
            )

        plan.refresh_from_db()
        return Response(LessonPlanDetailSerializer(plan).data)


# ── Helper ────────────────────────────────────────────────────

def _format_plan_for_ai(plan: LessonPlan) -> str:
    sections = [
        ('Title', plan.title),
        ('Subject', plan.subject),
        ('Topic', plan.topic),
        ('Duration', f'{plan.duration_minutes} minutes' if plan.duration_minutes else ''),
        ('Objective', plan.objective),
        ('Materials Needed', plan.materials_needed),
        ('Introduction', plan.introduction),
        ('Main Content', plan.main_content),
        ('Activities', plan.activities),
        ('Assessment', plan.assessment),
        ('Homework', plan.homework),
    ]
    return '\n\n'.join(f'**{label}**\n{value}' for label, value in sections if value.strip())
