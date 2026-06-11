from rest_framework import serializers
from .models import DailyContent, School, SchoolCulture


# ── Public serializers ────────────────────────────────────────

class SchoolPublicSerializer(serializers.ModelSerializer):
    """Minimal school data for the public school selection page."""
    class Meta:
        model = School
        fields = ('id', 'name', 'slug', 'logo_url')


class SchoolDetailSerializer(serializers.ModelSerializer):
    """Public detail view — safe fields only, no is_active or internal timestamps."""
    class Meta:
        model = School
        fields = ('id', 'name', 'slug', 'logo_url', 'address', 'contact_email', 'contact_phone')


# ── Culture serializers ───────────────────────────────────────

class SchoolCultureSerializer(serializers.ModelSerializer):
    """Read-only culture view — served to authenticated school members."""
    class Meta:
        model = SchoolCulture
        exclude = ('school',)


class SchoolCultureWriteSerializer(serializers.ModelSerializer):
    """Write serializer for school admin to upsert their culture profile."""
    founder_quotes = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
        help_text='Array of {quote: "...", author: "..."} objects.',
    )

    class Meta:
        model = SchoolCulture
        exclude = ('school', 'updated_at')


# ── Platform owner serializers ────────────────────────────────

class SchoolAdminSerializer(serializers.ModelSerializer):
    """Full school detail for platform owner and school admins."""
    class Meta:
        model = School
        fields = '__all__'
        read_only_fields = ('id', 'onboarding_date', 'created_at', 'updated_at')


class SchoolCreateSerializer(serializers.ModelSerializer):
    """Platform owner creates a new school (tenant)."""
    class Meta:
        model = School
        fields = ('name', 'slug', 'logo_url', 'address', 'contact_email', 'contact_phone')

    def validate_slug(self, value):
        if School.objects.filter(slug=value).exists():
            raise serializers.ValidationError('A school with this slug already exists.')
        return value


class SchoolUpdateSerializer(serializers.ModelSerializer):
    """Platform owner updates school fields (all optional — PATCH semantics)."""
    class Meta:
        model = School
        fields = ('name', 'slug', 'logo_url', 'address', 'contact_email', 'contact_phone', 'is_active')


class SchoolAdminSelfUpdateSerializer(serializers.ModelSerializer):
    """School admin updates their own school's public info — slug and is_active are platform-owner only."""
    class Meta:
        model = School
        fields = ('name', 'logo_url', 'address', 'contact_email', 'contact_phone')


# ── Daily content serializers ─────────────────────────────────

class DailyContentSerializer(serializers.ModelSerializer):
    """Full daily content record — used by admin CRUD endpoints."""
    class Meta:
        model = DailyContent
        fields = ('id', 'school', 'content_type', 'body', 'author', 'display_date', 'created_at')
        read_only_fields = ('id', 'school', 'created_at')


class DailyContentWriteSerializer(serializers.ModelSerializer):
    """Create daily content — school is injected by the view."""
    class Meta:
        model = DailyContent
        fields = ('content_type', 'body', 'author', 'display_date')


class DailyContentUpdateSerializer(serializers.ModelSerializer):
    """PATCH daily content — only body/author are mutable (content_type/display_date are identity fields)."""
    class Meta:
        model = DailyContent
        fields = ('body', 'author')


class DailyContentTodaySerializer(serializers.ModelSerializer):
    """Lightweight response for the /daily-content/today/ endpoint."""
    class Meta:
        model = DailyContent
        fields = ('id', 'content_type', 'body', 'author', 'display_date')
