import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from core.storage import storage

from drf_spectacular.utils import (
    OpenApiExample, OpenApiResponse, extend_schema, inline_serializer,
)

from .models import EmailVerificationToken, User, UserRole
from .serializers import (
    ChangePasswordSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ResendVerificationSerializer,
    VisitorRegistrationSerializer,
)
from .tokens import get_tokens_for_user

logger = logging.getLogger(__name__)

_TOKEN_RESPONSE = inline_serializer(
    name='TokenPair',
    fields={
        'access': drf_serializers.CharField(),
        'refresh': drf_serializers.CharField(),
    },
)


class AuthRateThrottle(AnonRateThrottle):
    rate = '5/minute'
    scope = 'auth'


# ── Login ─────────────────────────────────────────────────────

@extend_schema(tags=['Auth'])
class LoginView(APIView):
    """
    POST /api/v1/auth/login/

    Dual-vector authentication:
    - **STUDENT** → identifies via `username` (admission number), no email required
    - **TEACHER / *_ADMIN / VISITOR** → identifies via `email`

    On success, returns an access token (15 min) and a refresh token (7 days).
    Both tokens embed `role` and `school_id` in their payload.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary='Login (all roles)',
        request=LoginSerializer,
        responses={
            200: _TOKEN_RESPONSE,
            401: OpenApiResponse(description='Invalid credentials'),
            403: OpenApiResponse(description='Account disabled or role mismatch'),
        },
        examples=[
            OpenApiExample(
                'Student login',
                value={'role': 'STUDENT', 'identifier': 'ADM1029', 'password': 'secret', 'school_id': '99999999-1111-2222-3333-444444444444'},
                request_only=True,
            ),
            OpenApiExample(
                'Teacher login',
                value={'role': 'TEACHER', 'identifier': 'teacher@school.com', 'password': 'secret', 'school_id': '99999999-1111-2222-3333-444444444444'},
                request_only=True,
            ),
            OpenApiExample(
                'Visitor login',
                value={'role': 'VISITOR', 'identifier': 'visitor@email.com', 'password': 'secret'},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role       = serializer.validated_data['role']
        identifier = serializer.validated_data['identifier']
        password   = serializer.validated_data['password']
        school_id  = serializer.validated_data.get('school_id')

        # All school-bound roles must provide school_id up front
        if role != UserRole.VISITOR and not school_id:
            return Response(
                {
                    'error_code': 'SCHOOL_REQUIRED',
                    'detail': 'school_id is required. Select a school before logging in.',
                    'status_code': 400,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role == UserRole.STUDENT:
            user = authenticate(request, username=identifier, password=password)
        else:
            user = authenticate(request, email=identifier, password=password)

        if user is None:
            return Response(
                {'error_code': 'INVALID_CREDENTIALS', 'detail': 'Invalid credentials.', 'status_code': 401},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {'error_code': 'ACCOUNT_DISABLED', 'detail': 'This account has been deactivated.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.role == UserRole.PLATFORM_ADMIN:
            return Response(
                {
                    'error_code': 'PLATFORM_ADMIN_FORBIDDEN',
                    'detail': 'Platform admin accounts must use the Django admin panel at /admin/.',
                    'status_code': 403,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.role != role:
            return Response(
                {'error_code': 'ROLE_MISMATCH', 'detail': 'The selected role does not match this account.', 'status_code': 403},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Confirm the user actually belongs to the school they selected
        if role != UserRole.VISITOR and str(user.school_id) != str(school_id):
            return Response(
                {
                    'error_code': 'WRONG_SCHOOL',
                    'detail': 'This account does not belong to the selected school.',
                    'status_code': 403,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Visitors must verify email before accessing the platform
        if user.role == UserRole.VISITOR and not user.is_email_verified:
            return Response(
                {
                    'error_code': 'EMAIL_NOT_VERIFIED',
                    'detail': 'Please verify your email address before logging in.',
                    'status_code': 403,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)
        logger.info('User %s (%s) logged in.', user.id, user.role)
        return Response(tokens, status=status.HTTP_200_OK)


# ── Register Visitor ──────────────────────────────────────────

@extend_schema(tags=['Auth'])
class RegisterVisitorView(APIView):
    """
    POST /api/v1/auth/register/visitor/

    Creates a Visitor account with a **1-week free trial**.
    Sends an email verification link — the visitor must verify before logging in.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary='Register as Visitor',
        request=VisitorRegistrationSerializer,
        responses={
            201: inline_serializer(
                name='RegisterVisitorResponse',
                fields={'detail': drf_serializers.CharField()},
            ),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        serializer = VisitorRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        _send_verification_email(user, request)
        return Response(
            {'detail': 'Account created. Please check your email to verify your address.'},
            status=status.HTTP_201_CREATED,
        )


# ── Logout ────────────────────────────────────────────────────

@extend_schema(tags=['Auth'])
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/

    Blacklists the refresh token — the access token will naturally expire
    within 15 minutes (its configured lifetime).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Logout (blacklist refresh token)',
        request=inline_serializer(
            name='LogoutRequest',
            fields={'refresh': drf_serializers.CharField()},
        ),
        responses={
            204: OpenApiResponse(description='Logged out successfully'),
            400: OpenApiResponse(description='Missing or invalid refresh token'),
        },
    )
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error_code': 'MISSING_TOKEN', 'detail': 'Refresh token is required.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as exc:
            return Response(
                {'error_code': 'INVALID_TOKEN', 'detail': str(exc), 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Me (own profile) ──────────────────────────────────────────

@extend_schema(tags=['Auth'])
class MeView(APIView):
    """
    GET  /api/v1/auth/me/  — Return the authenticated user's own profile.
    PATCH /api/v1/auth/me/ — Update first_name / last_name.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Get own profile',
        responses={200: MeSerializer},
    )
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(
        summary='Update own profile (first/last name)',
        request=MeSerializer,
        responses={
            200: MeSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(request.user).data)


# ── Change password (authenticated) ──────────────────────────

@extend_schema(tags=['Auth'])
class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/password/change/

    Authenticated user changes their own password.
    Requires the current password for verification.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Change own password',
        request=ChangePasswordSerializer,
        responses={
            204: OpenApiResponse(description='Password changed'),
            400: OpenApiResponse(description='Validation error or wrong old password'),
        },
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'error_code': 'WRONG_PASSWORD', 'detail': 'Current password is incorrect.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        logger.info('User %s changed their password.', request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Password reset (unauthenticated) ──────────────────────────

@extend_schema(tags=['Auth'])
class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password/reset/

    Request a password-reset email. Always returns 200 regardless of whether the
    email is registered — prevents user enumeration.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary='Request password reset email',
        request=PasswordResetRequestSerializer,
        responses={200: inline_serializer(
            name='PasswordResetRequestResponse',
            fields={'detail': drf_serializers.CharField()},
        )},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email, is_active=True)
            _send_password_reset_email(user, request)
        except User.DoesNotExist:
            pass  # Intentional: do not reveal whether email exists

        return Response(
            {'detail': 'If an account with that email exists, a reset link has been sent.'},
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=['Auth'])
class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password/reset/confirm/

    Confirm a password reset using the `uid` + `token` from the reset email.
    The token is single-use — it becomes invalid once the password is changed.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Confirm password reset',
        request=PasswordResetConfirmSerializer,
        responses={
            204: OpenApiResponse(description='Password reset successfully'),
            400: OpenApiResponse(description='Invalid or expired reset link'),
        },
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        logger.info('User %s reset their password via email link.', user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Email verification ────────────────────────────────────────

@extend_schema(tags=['Auth'])
class EmailVerifyView(APIView):
    """
    POST /api/v1/auth/verify-email/

    Verify a Visitor's email address using the UUID token from the verification email.
    The token is single-use and expires after 24 hours.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Verify email address',
        request=EmailVerifySerializer,
        responses={
            200: inline_serializer(
                name='EmailVerifyResponse',
                fields={
                    'detail': drf_serializers.CharField(),
                    'access': drf_serializers.CharField(),
                    'refresh': drf_serializers.CharField(),
                },
            ),
            400: OpenApiResponse(description='Invalid or expired token'),
        },
    )
    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data['token']
        try:
            evt = EmailVerificationToken.objects.select_related('user').get(token=token_value)
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {'error_code': 'INVALID_TOKEN', 'detail': 'Verification token is invalid.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not evt.is_valid():
            evt.delete()
            return Response(
                {'error_code': 'TOKEN_EXPIRED', 'detail': 'Verification token has expired. Please request a new one.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = evt.user
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        evt.delete()

        tokens = get_tokens_for_user(user)
        logger.info('User %s verified their email.', user.id)
        return Response({'detail': 'Email verified successfully.', **tokens}, status=status.HTTP_200_OK)


@extend_schema(tags=['Auth'])
class ResendVerificationView(APIView):
    """
    POST /api/v1/auth/resend-verification/

    Re-send the email verification link for a Visitor account.
    Always returns 200 to prevent email enumeration.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary='Resend email verification',
        request=ResendVerificationSerializer,
        responses={200: inline_serializer(
            name='ResendVerificationResponse',
            fields={'detail': drf_serializers.CharField()},
        )},
    )
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email, role=UserRole.VISITOR, is_email_verified=False)
            # Replace the old token with a fresh one
            EmailVerificationToken.objects.filter(user=user).delete()
            EmailVerificationToken.objects.create(
                user=user,
                expires_at=timezone.now() + timedelta(hours=24),
            )
            _send_verification_email(user, request)
        except User.DoesNotExist:
            pass  # Intentional: do not reveal whether email exists

        return Response(
            {'detail': 'If an unverified account with that email exists, a new verification link has been sent.'},
            status=status.HTTP_200_OK,
        )


# ── Avatar upload ─────────────────────────────────────────────

@extend_schema(tags=['Auth'])
class AvatarView(APIView):
    """
    POST   /api/v1/auth/me/avatar/  — Upload or replace profile picture.
    DELETE /api/v1/auth/me/avatar/  — Remove profile picture.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    _MAX_SIZE = 5 * 1024 * 1024  # 5 MB
    _ALLOWED_TYPES = {
        'image/jpeg': 'jpg',
        'image/png':  'png',
        'image/webp': 'webp',
        'image/gif':  'gif',
    }

    @extend_schema(
        summary='Upload or replace profile picture',
        request=inline_serializer(
            name='AvatarUploadRequest',
            fields={'avatar': drf_serializers.ImageField()},
        ),
        responses={
            200: inline_serializer(
                name='AvatarUploadResponse',
                fields={'avatar_url': drf_serializers.URLField()},
            ),
            400: OpenApiResponse(description='Missing file, wrong type, or file too large'),
        },
    )
    def post(self, request):
        file_obj = request.FILES.get('avatar')
        if not file_obj:
            return Response(
                {'error_code': 'MISSING_FILE', 'detail': 'No file provided. Send the image as multipart field "avatar".', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = file_obj.content_type or ''
        ext = self._ALLOWED_TYPES.get(content_type)
        if not ext:
            return Response(
                {'error_code': 'INVALID_FILE_TYPE', 'detail': f'Unsupported file type "{content_type}". Allowed: JPEG, PNG, WebP, GIF.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if file_obj.size > self._MAX_SIZE:
            return Response(
                {'error_code': 'FILE_TOO_LARGE', 'detail': 'Avatar must be 5 MB or smaller.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete the old avatar if it used a different extension
        user = request.user
        if user.avatar_url:
            old_path = _avatar_path_from_url(user.avatar_url, settings.SUPABASE_AVATARS_BUCKET)
            if old_path:
                try:
                    storage.delete(settings.SUPABASE_AVATARS_BUCKET, [old_path])
                except Exception:
                    pass  # Best-effort; proceed with the new upload

        new_path = f'avatars/{user.id}.{ext}'
        url = storage.upload(
            settings.SUPABASE_AVATARS_BUCKET,
            new_path,
            file_obj.read(),
            content_type,
            upsert=True,
        )

        user.avatar_url = url
        user.save(update_fields=['avatar_url'])
        logger.info('User %s uploaded a new avatar.', user.id)
        return Response({'avatar_url': url}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Remove profile picture',
        responses={
            204: OpenApiResponse(description='Avatar removed'),
            400: OpenApiResponse(description='No avatar to remove'),
        },
    )
    def delete(self, request):
        user = request.user
        if not user.avatar_url:
            return Response(
                {'error_code': 'NO_AVATAR', 'detail': 'This account has no profile picture to remove.', 'status_code': 400},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_path = _avatar_path_from_url(user.avatar_url, settings.SUPABASE_AVATARS_BUCKET)
        if old_path:
            try:
                storage.delete(settings.SUPABASE_AVATARS_BUCKET, [old_path])
            except Exception:
                pass  # Best-effort

        user.avatar_url = None
        user.save(update_fields=['avatar_url'])
        logger.info('User %s removed their avatar.', user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _avatar_path_from_url(url: str, bucket: str) -> str | None:
    """Extract the storage path from a Supabase public URL."""
    marker = f'/object/public/{bucket}/'
    if marker in url:
        return url.split(marker, 1)[1]
    return None


# ── Email helpers ─────────────────────────────────────────────

def _send_verification_email(user: User, request) -> None:
    from django.conf import settings
    try:
        evt = user.email_verification_token
    except EmailVerificationToken.DoesNotExist:
        return

    verify_url = f'{settings.FRONTEND_URL}/verify-email?token={evt.token}'
    send_mail(
        subject='Verify your Genius Study Buddy account',
        message=(
            f'Hi {user.first_name or "there"},\n\n'
            f'Click the link below to verify your email address:\n{verify_url}\n\n'
            f'This link expires in 24 hours.\n\nThe GSB Team'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def _send_password_reset_email(user: User, request) -> None:
    from django.conf import settings
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f'{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}'
    send_mail(
        subject='Reset your Genius Study Buddy password',
        message=(
            f'Hi {user.first_name or "there"},\n\n'
            f'Click the link below to reset your password:\n{reset_url}\n\n'
            f'This link expires in 3 days. If you did not request this, ignore this email.\n\nThe GSB Team'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
