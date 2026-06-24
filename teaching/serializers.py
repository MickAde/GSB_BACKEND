from rest_framework import serializers

from .models import (
    LessonDocument,
    LessonDocumentStatus,
    LessonDocumentVersion,
    LessonPlan,
    LessonPlanComment,
)


# ── LessonDocument serializers ────────────────────────────────────────────────

class LessonDocumentListSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)
    class_name   = serializers.SerializerMethodField()

    class Meta:
        model  = LessonDocument
        fields = [
            'id', 'doc_type', 'generation_mode', 'subject', 'topic', 'subtopic',
            'class_level', 'term', 'week', 'title', 'board_summary',
            'status', 'distributed_to_class',
            'teacher_name', 'class_name', 'created_at', 'updated_at',
        ]

    def get_class_name(self, obj):
        return getattr(obj.teacher.student_class, 'name', None)


class LessonDocumentDetailSerializer(serializers.ModelSerializer):
    teacher_name     = serializers.CharField(source='teacher.full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True, default=None)
    class_name       = serializers.SerializerMethodField()
    version_count    = serializers.SerializerMethodField()

    class Meta:
        model  = LessonDocument
        fields = [
            'id', 'doc_type', 'generation_mode',
            'subject', 'topic', 'subtopic', 'class_level', 'term', 'week',
            'additional_context',
            'title', 'content_markdown', 'board_summary',
            'diagnostic_cards', 'resource_cards',
            'status', 'ai_task_id', 'generation_error',
            'approved_by_name', 'approval_timestamp', 'verification_hash', 'admin_comments',
            'distributed_to_class', 'distributed_at',
            'teacher_name', 'class_name', 'version_count',
            'created_at', 'updated_at',
        ]

    def get_class_name(self, obj):
        return getattr(obj.teacher.student_class, 'name', None)

    def get_version_count(self, obj):
        return obj.versions.count()


class CreateLessonDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LessonDocument
        fields = [
            'doc_type', 'generation_mode',
            'subject', 'topic', 'subtopic', 'class_level',
            'term', 'week', 'additional_context',
        ]

    def validate_term(self, value):
        if value not in (1, 2, 3):
            raise serializers.ValidationError('Term must be 1, 2, or 3.')
        return value

    def validate_week(self, value):
        if not (1 <= value <= 12):
            raise serializers.ValidationError('Week must be between 1 and 12.')
        return value


class UpdateLessonDocumentSerializer(serializers.ModelSerializer):
    """Teacher saves edits — only content fields, not status."""
    class Meta:
        model  = LessonDocument
        fields = ['title', 'content_markdown', 'board_summary', 'additional_context']
        extra_kwargs = {f: {'required': False} for f in fields}


class RegenerateSectionSerializer(serializers.Serializer):
    section_heading = serializers.CharField(max_length=300)
    instruction     = serializers.CharField(required=False, allow_blank=True, default='')


# ── Version serializers ───────────────────────────────────────────────────────

class LessonDocumentVersionSerializer(serializers.ModelSerializer):
    saved_by_name = serializers.CharField(source='saved_by.full_name', read_only=True, default=None)

    class Meta:
        model  = LessonDocumentVersion
        fields = ['id', 'version_number', 'content_markdown', 'board_summary',
                  'saved_by_name', 'change_note', 'created_at']


# ── Admin review serializers ──────────────────────────────────────────────────

class AdminReviewLessonDocSerializer(serializers.Serializer):
    action  = serializers.ChoiceField(choices=['approve', 'request_revision'])
    comment = serializers.CharField(required=False, allow_blank=True, default='')


# ── Legacy LessonPlan serializers (kept for backward compat) ──────────────────

class LessonPlanCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)

    class Meta:
        model  = LessonPlanComment
        fields = ['id', 'author_name', 'body', 'created_at']


class LessonPlanListSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)

    class Meta:
        model  = LessonPlan
        fields = ['id', 'title', 'subject', 'topic', 'status', 'teacher_name', 'created_at', 'updated_at']


class LessonPlanDetailSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)
    comments     = LessonPlanCommentSerializer(many=True, read_only=True)

    class Meta:
        model  = LessonPlan
        fields = [
            'id', 'title', 'subject', 'topic', 'subtopic', 'duration_minutes',
            'objective', 'materials_needed', 'introduction', 'main_content',
            'activities', 'assessment', 'homework', 'status', 'ai_suggestions',
            'teacher_name', 'comments', 'created_at', 'updated_at',
        ]


class CreateLessonPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LessonPlan
        fields = ['title', 'subject', 'topic', 'subtopic', 'duration_minutes',
                  'objective', 'materials_needed', 'introduction', 'main_content',
                  'activities', 'assessment', 'homework']

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('Title is required.')
        return value.strip()


class UpdateLessonPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LessonPlan
        fields = ['title', 'subject', 'topic', 'subtopic', 'duration_minutes',
                  'objective', 'materials_needed', 'introduction', 'main_content',
                  'activities', 'assessment', 'homework']
        extra_kwargs = {f: {'required': False} for f in fields}


class AdminReviewSerializer(serializers.Serializer):
    action  = serializers.ChoiceField(choices=['approve', 'request_revision'])
    comment = serializers.CharField(required=False, allow_blank=True, default='')
