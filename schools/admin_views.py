import logging

from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

from core.permissions import IsAnyAdmin
from .models import DailyContent, SchoolClass, SchoolCulture
from .serializers import (
    DailyContentSerializer,
    DailyContentUpdateSerializer,
    DailyContentWriteSerializer,
    SchoolAdminSerializer,
    SchoolAdminSelfUpdateSerializer,
    SchoolClassSerializer,
    SchoolCultureSerializer,
    SchoolCultureWriteSerializer,
)

logger = logging.getLogger(__name__)


# ── Own school info ───────────────────────────────────────────

@extend_schema(tags=['Admin — School'])
class AdminSchoolView(APIView):
    """
    GET   /api/v1/admin/school/  — Return the admin's own school info.
    PATCH /api/v1/admin/school/  — Update the school's public info (name, logo, address, contacts).

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    School is inferred from the requesting admin's JWT.

    > `slug` and `is_active` can only be changed by a platform owner
    > via `PATCH /api/v1/platform/schools/{id}/`.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        summary='Get own school info',
        responses={200: SchoolAdminSerializer},
    )
    def get(self, request):
        return Response(SchoolAdminSerializer(request.user.school).data)

    @extend_schema(
        summary='Update own school info (name, logo, address, contacts)',
        request=SchoolAdminSelfUpdateSerializer,
        responses={
            200: SchoolAdminSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def patch(self, request):
        school = request.user.school
        serializer = SchoolAdminSelfUpdateSerializer(school, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info('Admin %s updated school %s info.', request.user.id, school.id)
        return Response(SchoolAdminSerializer(school).data)


# ── School culture ────────────────────────────────────────────

@extend_schema(tags=['Admin — Culture'])
class AdminCultureView(APIView):
    """
    GET /api/v1/admin/culture/  — Return the school's culture profile.
    PUT /api/v1/admin/culture/  — Create or fully update the culture profile (upsert).

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    School is inferred from the requesting admin's JWT.

    GET returns an empty-field culture object if none has been set up yet,
    so the frontend can always render the edit form.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        summary='Get school culture profile',
        responses={200: SchoolCultureSerializer},
    )
    def get(self, request):
        culture, _ = SchoolCulture.objects.get_or_create(school=request.user.school)
        return Response(SchoolCultureSerializer(culture).data)

    @extend_schema(
        summary='Upsert school culture profile',
        request=SchoolCultureWriteSerializer,
        responses={
            200: SchoolCultureSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def put(self, request):
        culture, _ = SchoolCulture.objects.get_or_create(school=request.user.school)
        serializer = SchoolCultureWriteSerializer(culture, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info('Admin %s updated culture for school %s.', request.user.id, request.user.school_id)
        return Response(SchoolCultureSerializer(serializer.instance).data)


# ── Daily content ─────────────────────────────────────────────

@extend_schema(tags=['Admin — Classes'])
class AdminClassListCreateView(APIView):
    """
    GET  /api/v1/admin/classes/  — List all classes in the school.
    POST /api/v1/admin/classes/  — Create a new class.

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(summary='List school classes', responses={200: SchoolClassSerializer(many=True)})
    def get(self, request):
        qs = SchoolClass.unscoped.filter(school=request.user.school).order_by('name')
        return Response(SchoolClassSerializer(qs, many=True).data)

    @extend_schema(
        summary='Create a class',
        request=SchoolClassSerializer,
        responses={
            201: SchoolClassSerializer,
            400: OpenApiResponse(description='Validation error'),
            409: OpenApiResponse(description='Class name already exists'),
        },
    )
    def post(self, request):
        serializer = SchoolClassSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            school_class = serializer.save(school=request.user.school)
        except IntegrityError:
            return Response(
                {'name': [f'A class named "{request.data.get("name")}" already exists in this school.']},
                status=status.HTTP_409_CONFLICT,
            )
        logger.info('Admin %s created class %s.', request.user.id, school_class.id)
        return Response(SchoolClassSerializer(school_class).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Admin — Classes'])
class AdminClassDetailView(APIView):
    """
    PATCH  /api/v1/admin/classes/{id}/  — Rename a class.
    DELETE /api/v1/admin/classes/{id}/  — Delete a class (unassigns all members).

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    def _get_class(self, request, pk):
        try:
            return SchoolClass.unscoped.get(pk=pk, school=request.user.school)
        except SchoolClass.DoesNotExist:
            return None

    @extend_schema(
        summary='Rename a class',
        request=SchoolClassSerializer,
        responses={200: SchoolClassSerializer, 404: OpenApiResponse(description='Not found')},
    )
    def patch(self, request, pk):
        school_class = self._get_class(request, pk)
        if not school_class:
            return Response({'error_code': 'NOT_FOUND', 'detail': 'Class not found.', 'status_code': 404}, status=status.HTTP_404_NOT_FOUND)
        serializer = SchoolClassSerializer(school_class, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SchoolClassSerializer(school_class).data)

    @extend_schema(
        summary='Delete a class',
        responses={204: OpenApiResponse(description='Deleted'), 404: OpenApiResponse(description='Not found')},
    )
    def delete(self, request, pk):
        school_class = self._get_class(request, pk)
        if not school_class:
            return Response({'error_code': 'NOT_FOUND', 'detail': 'Class not found.', 'status_code': 404}, status=status.HTTP_404_NOT_FOUND)
        school_class.delete()
        logger.info('Admin %s deleted class %s.', request.user.id, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['Admin — Daily Content'])
class AdminDailyContentListCreateView(APIView):
    """
    GET  /api/v1/admin/daily-content/  — List daily content for this school.
    POST /api/v1/admin/daily-content/  — Create a new daily content entry.

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    The `school` is automatically set to the requesting admin's school.

    `unique_together (school, content_type, display_date)` means only one entry per
    type per day. A duplicate POST returns 409 Conflict.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        summary='List school daily content',
        parameters=[
            OpenApiParameter('content_type', description='Filter by STUDENT_QUOTE / TEACHER_TIP / ADMIN_INSIGHT'),
            OpenApiParameter('display_date', description='Filter by date (YYYY-MM-DD)'),
        ],
        responses={200: DailyContentSerializer(many=True)},
    )
    def get(self, request):
        qs = DailyContent.objects.filter(school=request.user.school).order_by('-display_date', 'content_type')

        content_type = request.query_params.get('content_type')
        if content_type:
            qs = qs.filter(content_type=content_type)

        display_date = request.query_params.get('display_date')
        if display_date:
            qs = qs.filter(display_date=display_date)

        return Response(DailyContentSerializer(qs, many=True).data)

    @extend_schema(
        summary='Create daily content entry',
        request=DailyContentWriteSerializer,
        responses={
            201: DailyContentSerializer,
            400: OpenApiResponse(description='Validation error'),
            409: OpenApiResponse(description='Entry already exists for this type and date'),
        },
    )
    def post(self, request):
        serializer = DailyContentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            content = serializer.save(school=request.user.school)
        except IntegrityError:
            return Response(
                {
                    'error_code': 'DUPLICATE_ENTRY',
                    'detail': (
                        f'A {serializer.validated_data.get("content_type")} entry already exists '
                        f'for {serializer.validated_data.get("display_date")}.'
                    ),
                    'status_code': 409,
                },
                status=status.HTTP_409_CONFLICT,
            )
        logger.info('Admin %s created daily content %s.', request.user.id, content.id)
        return Response(DailyContentSerializer(content).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Admin — Daily Content'])
class AdminDailyContentDetailView(APIView):
    """
    PATCH  /api/v1/admin/daily-content/{id}/  — Update body or author of an entry.
    DELETE /api/v1/admin/daily-content/{id}/  — Delete a daily content entry.

    **Permission:** MAIN_ADMIN or SUB_ADMIN, same school only.

    > Only `body` and `author` are updatable via PATCH.
    > `content_type` and `display_date` are identity fields — create a new entry if you need
    > a different type or date.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    def _get_content(self, request, pk):
        try:
            return DailyContent.objects.get(pk=pk, school=request.user.school)
        except DailyContent.DoesNotExist:
            return None

    @extend_schema(
        summary='Update daily content (body / author only)',
        request=DailyContentUpdateSerializer,
        responses={
            200: DailyContentSerializer,
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def patch(self, request, pk):
        content = self._get_content(request, pk)
        if not content:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Daily content not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DailyContentUpdateSerializer(content, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(DailyContentSerializer(content).data)

    @extend_schema(
        summary='Delete daily content',
        responses={
            204: OpenApiResponse(description='Deleted'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def delete(self, request, pk):
        content = self._get_content(request, pk)
        if not content:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'Daily content not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        content.delete()
        logger.info('Admin %s deleted daily content %s.', request.user.id, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
