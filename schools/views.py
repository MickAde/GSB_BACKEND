from datetime import date

from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from django.db.models import Q
from .models import DailyContent, School, SchoolClass, SchoolCulture, Subject
from .serializers import (
    DailyContentTodaySerializer,
    SchoolCultureSerializer,
    SchoolDetailSerializer,
    SchoolPublicSerializer,
    SubjectListSerializer,
)


# ── Active schools list (public) ──────────────────────────────

@extend_schema(
    tags=['Schools'],
    summary='List active schools',
    description=(
        'Public endpoint — no authentication required. '
        'Returns all schools currently onboarded and active on the platform. '
        'Used to populate the School Selection Page before login.'
    ),
    responses={200: SchoolPublicSerializer(many=True)},
    examples=[
        OpenApiExample(
            'Example response',
            value=[
                {'id': '99999999-1111-2222-3333-444444444444', 'name': 'Prestige Academy', 'slug': 'prestige-academy', 'logo_url': 'https://...'},
            ],
            response_only=True,
        )
    ],
)
class ActiveSchoolListView(ListAPIView):
    """GET /api/v1/schools/active/"""
    serializer_class = SchoolPublicSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return School.objects.filter(is_active=True).order_by('name')


# ── School public detail ──────────────────────────────────────

@extend_schema(
    tags=['Schools'],
    summary='Get school public detail',
    description=(
        'Public endpoint — no authentication required. '
        'Returns publicly safe school info: name, address, contact details.'
    ),
    responses={
        200: SchoolDetailSerializer,
        404: OpenApiResponse(description='School not found or inactive'),
    },
)
class SchoolDetailView(RetrieveAPIView):
    """GET /api/v1/schools/{pk}/"""
    serializer_class = SchoolDetailSerializer
    permission_classes = [AllowAny]
    queryset = School.objects.filter(is_active=True)


# ── School culture (authenticated school member) ──────────────

@extend_schema(
    tags=['Schools'],
    summary='Get school culture profile',
    description=(
        'Returns the school\'s philosophy, mission, vision, and values. '
        'Used to personalise AI-generated content. '
        '**Authentication required — must be a member of this school.**'
    ),
    responses={
        200: SchoolCultureSerializer,
        404: OpenApiResponse(description='School not found or no culture configured'),
    },
)
class SchoolCultureView(RetrieveAPIView):
    """GET /api/v1/schools/{pk}/culture/"""
    serializer_class = SchoolCultureSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        pk = self.kwargs['pk']
        # Only expose culture for the user's own school
        if str(self.request.user.school_id) != str(pk):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You can only access your own school\'s culture profile.')
        try:
            return SchoolCulture.objects.get(school_id=pk)
        except SchoolCulture.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Culture profile not yet configured for this school.')


# ── Daily content (today) ─────────────────────────────────────

_ROLE_TO_CONTENT_TYPE = {
    'STUDENT':    'STUDENT_QUOTE',
    'TEACHER':    'TEACHER_TIP',
    'MAIN_ADMIN': 'ADMIN_INSIGHT',
    'SUB_ADMIN':  'ADMIN_INSIGHT',
    'VISITOR':    'STUDENT_QUOTE',
}


@extend_schema(
    tags=['Daily Content'],
    summary='Get today\'s daily content for the current user',
    description=(
        'Returns the daily content item relevant to the authenticated user\'s role for today.\n\n'
        '- STUDENT / VISITOR → `STUDENT_QUOTE`\n'
        '- TEACHER → `TEACHER_TIP`\n'
        '- MAIN_ADMIN / SUB_ADMIN → `ADMIN_INSIGHT`\n\n'
        'School-specific content takes priority over platform-wide content. '
        'Returns 404 if no content has been generated for today.'
    ),
    responses={
        200: DailyContentTodaySerializer,
        404: OpenApiResponse(description='No content available for today'),
    },
)
class DailyContentTodayView(APIView):
    """GET /api/v1/daily-content/today/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content_type = _ROLE_TO_CONTENT_TYPE.get(request.user.role, 'STUDENT_QUOTE')
        today = date.today()

        # Prefer school-specific content; fall back to platform-wide (school=None)
        content = None
        if request.user.school_id:
            content = DailyContent.objects.filter(
                school=request.user.school_id,
                content_type=content_type,
                display_date=today,
            ).first()

        if not content:
            content = DailyContent.objects.filter(
                school__isnull=True,
                content_type=content_type,
                display_date=today,
            ).first()

        if not content:
            return Response(None, status=status.HTTP_200_OK)

        return Response(DailyContentTodaySerializer(content).data)


# ── Subjects (authenticated) ──────────────────────────────────

@extend_schema(
    tags=['Schools'],
    summary='List subjects available for a class',
    description=(
        'Returns subjects the authenticated user can see.\n\n'
        'Pass `?class_id=<uuid>` to get subjects for a specific class '
        '(general subjects + class-specific subjects). '
        'Without `class_id`, all school subjects are returned (useful for admin/teacher views).'
    ),
    responses={200: SubjectListSerializer(many=True)},
)
class SubjectListView(APIView):
    """GET /api/v1/schools/subjects/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        if not school_id:
            return Response([])

        class_id = request.query_params.get('class_id')
        qs = Subject.unscoped.filter(school_id=school_id)

        if class_id:
            # Return general subjects OR subjects assigned to this specific class
            qs = qs.filter(Q(is_general=True) | Q(classes__id=class_id)).distinct()

        return Response(SubjectListSerializer(qs.order_by('name'), many=True).data)
