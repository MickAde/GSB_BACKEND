from rest_framework import serializers
from .models import LessonPlan, LessonPlanComment, LessonPlanStatus


class LessonPlanCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)

    class Meta:
        model = LessonPlanComment
        fields = ['id', 'author_name', 'body', 'created_at']


class LessonPlanListSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)

    class Meta:
        model = LessonPlan
        fields = ['id', 'title', 'subject', 'topic', 'status',
                  'teacher_name', 'created_at', 'updated_at']


class LessonPlanDetailSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)
    comments     = LessonPlanCommentSerializer(many=True, read_only=True)

    class Meta:
        model = LessonPlan
        fields = [
            'id', 'title', 'subject', 'topic', 'subtopic',
            'duration_minutes', 'objective', 'materials_needed',
            'introduction', 'main_content', 'activities',
            'assessment', 'homework', 'status', 'ai_suggestions',
            'teacher_name', 'comments', 'created_at', 'updated_at',
        ]


class CreateLessonPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonPlan
        fields = [
            'title', 'subject', 'topic', 'subtopic', 'duration_minutes',
            'objective', 'materials_needed', 'introduction', 'main_content',
            'activities', 'assessment', 'homework',
        ]

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('Title is required.')
        return value.strip()


class UpdateLessonPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonPlan
        fields = [
            'title', 'subject', 'topic', 'subtopic', 'duration_minutes',
            'objective', 'materials_needed', 'introduction', 'main_content',
            'activities', 'assessment', 'homework',
        ]
        extra_kwargs = {f: {'required': False} for f in fields}


class AdminReviewSerializer(serializers.Serializer):
    action  = serializers.ChoiceField(choices=['approve', 'request_revision'])
    comment = serializers.CharField(required=False, allow_blank=True, default='')
