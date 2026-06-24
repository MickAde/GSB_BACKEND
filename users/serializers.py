from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers

from .models import CreatableUserRole, EmailVerificationToken, User, UserRole


# ── Auth serializers ──────────────────────────────────────────

_LOGINABLE_ROLES = [
    (r, label) for r, label in UserRole.choices
    if r != UserRole.PLATFORM_ADMIN
]

class LoginSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=_LOGINABLE_ROLES)
    identifier = serializers.CharField(
        help_text='Email for TEACHER/ADMIN/VISITOR. Admission number for STUDENT.',
    )
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    school_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class VisitorRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'password')

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(
            role=UserRole.VISITOR,
            trial_expires_at=timezone.now() + timedelta(weeks=1),
            is_email_verified=False,
            **validated_data,
        )
        user.set_password(password)
        user.full_clean()
        user.save()
        # Create the email verification token (24-hour expiry)
        EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        return user


# ── Profile serializers ───────────────────────────────────────

class MeSerializer(serializers.ModelSerializer):
    """Own profile — readable + updatable fields for GET /auth/me/ and PATCH /auth/me/."""
    full_name               = serializers.CharField(read_only=True)
    school_name             = serializers.CharField(source='school.name',         read_only=True, default=None)
    student_class_id        = serializers.UUIDField(source='student_class.id',   read_only=True, allow_null=True)
    student_class_name      = serializers.CharField(source='student_class.name', read_only=True, allow_null=True)
    is_visitor_trial_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'role',
            'first_name', 'last_name', 'full_name',
            'avatar_url',
            'school', 'school_name',
            'student_class_id', 'student_class_name',
            'is_email_verified',
            'trial_expires_at', 'is_visitor_trial_active',
            'date_joined',
        )
        read_only_fields = (
            'id', 'email', 'username', 'role',
            'avatar_url',
            'school', 'school_name',
            'student_class_id', 'student_class_name',
            'is_email_verified',
            'trial_expires_at', 'is_visitor_trial_active',
            'date_joined',
        )


# ── Password management ───────────────────────────────────────

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({'uid': 'Invalid reset link.'})

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'token': 'Reset link has expired or is invalid.'})

        attrs['user'] = user
        return attrs


# ── Email verification ────────────────────────────────────────

class EmailVerifySerializer(serializers.Serializer):
    token = serializers.UUIDField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


# ── Admin — user management ───────────────────────────────────

class UserCreateSerializer(serializers.Serializer):
    """School admin creates a new user inside their school."""
    role             = serializers.ChoiceField(choices=CreatableUserRole.choices)
    first_name       = serializers.CharField(max_length=150)
    last_name        = serializers.CharField(max_length=150, required=False, default='')
    password         = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    email            = serializers.EmailField(required=False, allow_null=True, default=None)
    username         = serializers.CharField(max_length=150, required=False, allow_null=True, default=None)
    student_class_id = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value or None

    def validate_username(self, value):
        if value and User.objects.filter(username=value).exists():
            raise serializers.ValidationError('A user with this admission number already exists.')
        return value or None

    def validate(self, attrs):
        role = attrs['role']
        if role == UserRole.STUDENT:
            if not attrs.get('username'):
                raise serializers.ValidationError({'username': 'Admission number is required for STUDENT.'})
            attrs['email'] = None
        else:
            if not attrs.get('email'):
                raise serializers.ValidationError({'email': 'Email is required for TEACHER and SUB_ADMIN.'})
            attrs['username'] = None
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(is_email_verified=True, **validated_data)
        user.set_password(password)
        user.full_clean()
        user.save()
        return user


class BulkStudentItemSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150, required=False, default='')
    username   = serializers.CharField(max_length=150, help_text='Admission number / student ID.')
    password   = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})


class BulkStudentCreateSerializer(serializers.Serializer):
    """Bulk-create students inside the admin's school."""
    students = BulkStudentItemSerializer(many=True)

    def validate_students(self, value):
        if not value:
            raise serializers.ValidationError('At least one student is required.')
        return value


class UserAdminListSerializer(serializers.ModelSerializer):
    """Compact user card for the admin users list page."""
    full_name          = serializers.CharField(read_only=True)
    student_class_id   = serializers.UUIDField(source='student_class.id',   read_only=True, allow_null=True)
    student_class_name = serializers.CharField(source='student_class.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = (
            'id', 'role', 'first_name', 'last_name', 'full_name',
            'email', 'username', 'avatar_url', 'is_active', 'date_joined',
            'student_class_id', 'student_class_name',
        )
        read_only_fields = fields


class UserAdminDetailSerializer(serializers.ModelSerializer):
    """Full user detail for the admin user detail / edit page."""
    full_name          = serializers.CharField(read_only=True)
    school_name        = serializers.CharField(source='school.name', read_only=True, default=None)
    student_class_id   = serializers.UUIDField(source='student_class.id',   read_only=True, allow_null=True)
    student_class_name = serializers.CharField(source='student_class.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = (
            'id', 'role', 'first_name', 'last_name', 'full_name',
            'email', 'username', 'avatar_url',
            'school', 'school_name',
            'student_class_id', 'student_class_name',
            'is_active', 'is_email_verified',
            'trial_expires_at', 'date_joined',
        )
        read_only_fields = fields


class UserAdminUpdateSerializer(serializers.ModelSerializer):
    """Allowed fields an admin can update on a user."""
    student_class_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'is_active', 'student_class_id')


class AdminSetPasswordSerializer(serializers.Serializer):
    """Admin sets a user's password directly (no old-password required)."""
    new_password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


# Legacy alias — used by the Django admin and earlier views
class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    school_name = serializers.CharField(source='school.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'role',
            'first_name', 'last_name', 'full_name',
            'avatar_url',
            'school', 'school_name', 'date_joined',
        )
        read_only_fields = ('id', 'role', 'school', 'date_joined', 'avatar_url')
