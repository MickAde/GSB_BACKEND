import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import OpenApiResponse, extend_schema

from core.permissions import IsPlatformOwner
from .models import School
from .serializers import (
    SchoolAdminSerializer,
    SchoolCreateSerializer,
    SchoolUpdateSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(tags=['Platform — Schools'])
class PlatformSchoolListCreateView(APIView):
    """
    GET  /api/v1/platform/schools/  — List all schools (active + inactive).
    POST /api/v1/platform/schools/  — Create (onboard) a new school tenant.

    **Permission:** Platform owner only (`is_staff=True`).
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    @extend_schema(
        summary='List all schools',
        responses={200: SchoolAdminSerializer(many=True)},
    )
    def get(self, request):
        schools = School.objects.all().order_by('name')
        return Response(SchoolAdminSerializer(schools, many=True).data)

    @extend_schema(
        summary='Onboard a new school',
        request=SchoolCreateSerializer,
        responses={
            201: SchoolAdminSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        serializer = SchoolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = serializer.save()
        logger.info('Platform owner %s created school "%s" (%s).', request.user.id, school.name, school.id)
        return Response(SchoolAdminSerializer(school).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Platform — Schools'])
class PlatformSchoolDetailView(APIView):
    """
    GET    /api/v1/platform/schools/{id}/  — Full school detail.
    PATCH  /api/v1/platform/schools/{id}/  — Update any school field.
    DELETE /api/v1/platform/schools/{id}/  — Soft-deactivate (sets is_active=False).

    **Permission:** Platform owner only (`is_staff=True`).

    > DELETE is a soft-delete: it sets `is_active=False` which triggers the
    > PostgreSQL RLS policy to deny all data access for that tenant.
    > Hard deletion is intentionally not supported here — use the database directly.
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def _get_school(self, pk):
        try:
            return School.objects.get(pk=pk)
        except School.DoesNotExist:
            return None

    @extend_schema(
        summary='Get school detail',
        responses={200: SchoolAdminSerializer, 404: OpenApiResponse(description='Not found')},
    )
    def get(self, request, pk):
        school = self._get_school(pk)
        if not school:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'School not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SchoolAdminSerializer(school).data)

    @extend_schema(
        summary='Update school',
        request=SchoolUpdateSerializer,
        responses={200: SchoolAdminSerializer, 400: OpenApiResponse(description='Validation error'), 404: OpenApiResponse(description='Not found')},
    )
    def patch(self, request, pk):
        school = self._get_school(pk)
        if not school:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'School not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SchoolUpdateSerializer(school, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info('Platform owner %s updated school %s.', request.user.id, school.id)
        return Response(SchoolAdminSerializer(school).data)

    @extend_schema(
        summary='Deactivate school (soft-delete)',
        responses={204: OpenApiResponse(description='School deactivated'), 404: OpenApiResponse(description='Not found')},
    )
    def delete(self, request, pk):
        school = self._get_school(pk)
        if not school:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'School not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        school.is_active = False
        school.save(update_fields=['is_active', 'updated_at'])
        logger.info('Platform owner %s deactivated school %s.', request.user.id, school.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
