import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer,
)
from rest_framework import serializers as drf_serializers

from core.pagination import StandardResultsPagination
from core.permissions import IsAnyAdmin
from schools.models import SchoolClass
from .models import User, UserRole
from .serializers import (
    AdminSetPasswordSerializer,
    BulkStudentCreateSerializer,
    UserAdminDetailSerializer,
    UserAdminListSerializer,
    UserAdminUpdateSerializer,
    UserCreateSerializer,
)

logger = logging.getLogger(__name__)


# ── List + Create ─────────────────────────────────────────────

@extend_schema(tags=['Admin — Users'])
class AdminUserListCreateView(APIView):
    """
    GET  /api/v1/admin/users/  — List users in the admin's school (paginated, filterable).
    POST /api/v1/admin/users/  — Create a new user inside the school.

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    The `school` is automatically set to the requesting admin's school.

    **Creatable roles via POST:** STUDENT, TEACHER, SUB_ADMIN.
    *(MAIN_ADMIN and VISITOR cannot be created via this endpoint.)*

    > Only MAIN_ADMIN can create SUB_ADMIN accounts.

    **GET query params:**
    - `role` — filter by role (STUDENT, TEACHER, SUB_ADMIN, MAIN_ADMIN)
    - `is_active` — filter by status (true / false)
    - `search` — search first name, last name, email, or admission number
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        summary='List school users',
        parameters=[
            OpenApiParameter('role',      description='Filter by role'),
            OpenApiParameter('is_active', description='Filter by is_active (true/false)'),
            OpenApiParameter('search',    description='Search name, email, or admission number'),
        ],
        responses={200: UserAdminListSerializer(many=True)},
    )
    def get(self, request):
        qs = (
            User.objects
            .filter(school=request.user.school)
            .order_by('role', 'first_name', 'last_name')
        )

        role = request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(username__icontains=search)
            )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(UserAdminListSerializer(page, many=True).data)
        return Response(UserAdminListSerializer(qs, many=True).data)

    @extend_schema(
        summary='Create a user in the school',
        request=UserCreateSerializer,
        responses={
            201: UserAdminDetailSerializer,
            400: OpenApiResponse(description='Validation error'),
            403: OpenApiResponse(description='Only MAIN_ADMIN can create SUB_ADMIN accounts'),
        },
    )
    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role = serializer.validated_data['role']
        if role == UserRole.SUB_ADMIN and request.user.role != UserRole.MAIN_ADMIN:
            return Response(
                {'error_code': 'FORBIDDEN', 'detail': 'Only MAIN_ADMIN can create SUB_ADMIN accounts.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Resolve optional student_class_id → SchoolClass instance
        class_id = serializer.validated_data.pop('student_class_id', None)
        student_class = None
        if class_id:
            try:
                student_class = SchoolClass.unscoped.get(id=class_id, school=request.user.school)
            except SchoolClass.DoesNotExist:
                return Response(
                    {'student_class_id': ['Class not found or does not belong to this school.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        user = serializer.save(school=request.user.school, student_class=student_class)
        logger.info('Admin %s created user %s (%s).', request.user.id, user.id, user.role)
        return Response(UserAdminDetailSerializer(user).data, status=status.HTTP_201_CREATED)


# ── Bulk student creation ─────────────────────────────────────

@extend_schema(tags=['Admin — Users'])
class AdminUserBulkCreateView(APIView):
    """
    POST /api/v1/admin/users/bulk/

    Bulk-create multiple STUDENT accounts in a single request.
    Returns a 207 Multi-Status response listing successes and failures so the
    frontend can show a per-row import report.

    **Permission:** MAIN_ADMIN or SUB_ADMIN.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        summary='Bulk-create students',
        request=BulkStudentCreateSerializer,
        responses={
            201: inline_serializer(
                name='BulkStudentCreateResponse',
                fields={
                    'created': UserAdminListSerializer(many=True),
                    'failed': drf_serializers.ListField(child=drf_serializers.DictField()),
                },
            ),
            207: OpenApiResponse(description='Partial success — check `failed` list'),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        serializer = BulkStudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        school = request.user.school
        created, failed = [], []

        for item in serializer.validated_data['students']:
            password = item.pop('password')
            try:
                user = User(
                    role=UserRole.STUDENT,
                    school=school,
                    is_email_verified=True,
                    **item,
                )
                user.set_password(password)
                user.full_clean()
                user.save()
                created.append(user)
                logger.info('Bulk: admin %s created student %s.', request.user.id, user.id)
            except Exception as exc:
                failed.append({'username': item.get('username', ''), 'error': str(exc)})

        http_status = status.HTTP_207_MULTI_STATUS if failed else status.HTTP_201_CREATED
        return Response(
            {
                'created': UserAdminListSerializer(created, many=True).data,
                'failed': failed,
            },
            status=http_status,
        )


# ── User detail / update / deactivate ────────────────────────

@extend_schema(tags=['Admin — Users'])
class AdminUserDetailView(APIView):
    """
    GET    /api/v1/admin/users/{id}/  — Full user detail.
    PATCH  /api/v1/admin/users/{id}/  — Update first_name, last_name, is_active.
    DELETE /api/v1/admin/users/{id}/  — Soft-deactivate (sets is_active=False).

    **Permission:** MAIN_ADMIN or SUB_ADMIN, same school only.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    def _get_user(self, request, pk):
        try:
            return User.objects.select_related('school').get(pk=pk, school=request.user.school)
        except User.DoesNotExist:
            return None

    @extend_schema(
        summary='Get user detail',
        responses={200: UserAdminDetailSerializer, 404: OpenApiResponse(description='Not found')},
    )
    def get(self, request, pk):
        user = self._get_user(request, pk)
        if not user:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'User not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(UserAdminDetailSerializer(user).data)

    @extend_schema(
        summary='Update user (name / active status)',
        request=UserAdminUpdateSerializer,
        responses={
            200: UserAdminDetailSerializer,
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def patch(self, request, pk):
        user = self._get_user(request, pk)
        if not user:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'User not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.role in (UserRole.MAIN_ADMIN, UserRole.SUB_ADMIN) and request.user.role != UserRole.MAIN_ADMIN:
            return Response(
                {'error_code': 'FORBIDDEN', 'detail': 'Only MAIN_ADMIN can modify admin accounts.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UserAdminUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Handle student_class update separately (needs school-scoped lookup)
        class_id = serializer.validated_data.pop('student_class_id', ...)
        serializer.save()

        if class_id is not ...:  # field was explicitly provided
            if class_id:
                try:
                    user.student_class = SchoolClass.unscoped.get(id=class_id, school=request.user.school)
                except SchoolClass.DoesNotExist:
                    return Response(
                        {'student_class_id': ['Class not found or does not belong to this school.']},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                user.student_class = None
            user.save(update_fields=['student_class'])

        return Response(UserAdminDetailSerializer(user).data)

    @extend_schema(
        summary='Deactivate user (soft-delete)',
        responses={204: OpenApiResponse(description='User deactivated'), 404: OpenApiResponse(description='Not found')},
    )
    def delete(self, request, pk):
        user = self._get_user(request, pk)
        if not user:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'User not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.role == UserRole.MAIN_ADMIN:
            return Response(
                {'error_code': 'FORBIDDEN', 'detail': 'MAIN_ADMIN account cannot be deactivated via this endpoint.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )
        user.is_active = False
        user.save(update_fields=['is_active'])
        logger.info('Admin %s deactivated user %s.', request.user.id, user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Admin set password ────────────────────────────────────────

@extend_schema(tags=['Admin — Users'])
class AdminUserSetPasswordView(APIView):
    """
    POST /api/v1/admin/users/{id}/set-password/

    Admin sets a user's password directly — no old-password check required.
    Useful for resetting a student's forgotten password.

    **Permission:** MAIN_ADMIN or SUB_ADMIN, same school only.
    > Sub-admin cannot reset another admin's password.
    """
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        summary='Admin: set user password',
        request=AdminSetPasswordSerializer,
        responses={
            204: OpenApiResponse(description='Password updated'),
            400: OpenApiResponse(description='Validation error'),
            403: OpenApiResponse(description='Permission denied'),
            404: OpenApiResponse(description='User not found'),
        },
    )
    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk, school=request.user.school)
        except User.DoesNotExist:
            return Response(
                {'error_code': 'NOT_FOUND', 'detail': 'User not found.', 'status_code': 404},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.role in (UserRole.MAIN_ADMIN, UserRole.SUB_ADMIN) and request.user.role != UserRole.MAIN_ADMIN:
            return Response(
                {'error_code': 'FORBIDDEN', 'detail': 'Only MAIN_ADMIN can reset admin passwords.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AdminSetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        logger.info('Admin %s reset password for user %s.', request.user.id, user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
