import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from .managers import UserManager


class UserRole(models.TextChoices):
    STUDENT        = 'STUDENT',         'Student'
    TEACHER        = 'TEACHER',         'Teacher'
    SUB_ADMIN      = 'SUB_ADMIN',       'Sub Admin'
    MAIN_ADMIN     = 'MAIN_ADMIN',      'Main Admin'
    VISITOR        = 'VISITOR',         'Visitor'
    PLATFORM_ADMIN = 'PLATFORM_ADMIN',  'Platform Admin'


class CreatableUserRole(models.TextChoices):
    """Roles that a school admin may assign when creating a new user account."""
    STUDENT   = 'STUDENT',   'Student'
    TEACHER   = 'TEACHER',   'Teacher'
    SUB_ADMIN = 'SUB_ADMIN', 'Sub Admin'


class User(AbstractBaseUser, PermissionsMixin):
    """
    Single user table for all roles. Auth strategy differs by role:
      - STUDENT   : authenticates via username (admission number), no email required
      - TEACHER   : authenticates via email
      - *_ADMIN   : authenticates via email
      - VISITOR   : authenticates via email, school=None

    school=None is valid only for VISITOR and platform superusers.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    school = models.ForeignKey(
        'schools.School',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        db_index=True,
    )

    role = models.CharField(max_length=20, choices=UserRole.choices, db_index=True)

    # Students use username; teachers/admins/visitors use email.
    # Both are nullable at the DB level — clean() enforces the constraint.
    username = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Admission number / student ID. Used only for STUDENT role.',
    )
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    avatar_url = models.URLField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    # Visitor-specific
    trial_expires_at = models.DateTimeField(null=True, blank=True)

    # Email verification — default True so existing admin/school accounts are unaffected.
    # RegisterVisitorView sets this to False on creation; verified via /auth/verify-email/.
    is_email_verified = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['role']

    class Meta:
        db_table = 'users_user'
        indexes = [
            models.Index(fields=['school', 'role'], name='idx_user_school_role'),
        ]

    def __str__(self):
        return self.email or self.username or str(self.id)

    def clean(self):
        if self.role == UserRole.PLATFORM_ADMIN:
            # Platform admin is a Django superuser — no school association required.
            return
        if self.role == UserRole.STUDENT:
            if not self.username:
                raise ValidationError({'username': 'Students must have a username (admission number).'})
            if self.email:
                raise ValidationError({'email': 'Students must not have an email address.'})
            if not self.school_id:
                raise ValidationError({'school': 'Students must belong to a school.'})
        elif self.role == UserRole.VISITOR:
            if not self.email:
                raise ValidationError({'email': 'Visitors must have an email address.'})
        else:
            # TEACHER, SUB_ADMIN, MAIN_ADMIN
            if not self.email:
                raise ValidationError({'email': 'Teachers and admins must have an email address.'})
            if not self.school_id:
                raise ValidationError({'school': 'Teachers and admins must belong to a school.'})

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.__str__()

    @property
    def is_visitor_trial_active(self):
        if self.role != UserRole.VISITOR or not self.trial_expires_at:
            return False
        from django.utils import timezone
        return timezone.now() < self.trial_expires_at


class EmailVerificationToken(models.Model):
    """
    Single-use token for verifying a Visitor's email address.
    Created alongside the visitor account; invalidated on first use or after 24 h.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='email_verification_token',
    )
    token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'users_emailverificationtoken'

    def is_valid(self):
        from django.utils import timezone
        return timezone.now() < self.expires_at
