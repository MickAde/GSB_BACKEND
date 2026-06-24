from rest_framework import serializers
from .models import (
    DIFFICULTY_ORDER,
    Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion,
    StudentQuizPreferences, TeacherSubjectThreshold,
)


# ── Question serializers ──────────────────────────────────────

class QuizQuestionSerializer(serializers.ModelSerializer):
    """Questions without answers — used when serving the quiz to a student."""
    class Meta:
        model = QuizQuestion
        fields = ['id', 'order', 'question_type', 'question_text',
                  'option_a', 'option_b', 'option_c', 'option_d']


class QuizQuestionWithAnswerSerializer(serializers.ModelSerializer):
    """Questions including correct answer and explanation — used in results."""
    class Meta:
        model = QuizQuestion
        fields = ['id', 'order', 'question_type', 'question_text',
                  'option_a', 'option_b', 'option_c', 'option_d',
                  'correct', 'explanation']


# ── Quiz serializers ──────────────────────────────────────────

class QuizListSerializer(serializers.ModelSerializer):
    attempt_count = serializers.SerializerMethodField()
    subject       = serializers.CharField(source='note.subject', read_only=True)
    note_name     = serializers.CharField(source='note.file_name', read_only=True)

    class Meta:
        model = Quiz
        fields = ['id', 'title', 'difficulty', 'num_questions', 'status',
                  'subject', 'note_name', 'attempt_count', 'created_at']

    def get_attempt_count(self, obj):
        return obj.attempts.count()


class QuizDetailSerializer(serializers.ModelSerializer):
    questions     = QuizQuestionSerializer(many=True, read_only=True)
    attempt_count = serializers.SerializerMethodField()
    subject       = serializers.CharField(source='note.subject', read_only=True)
    note_name     = serializers.CharField(source='note.file_name', read_only=True)

    class Meta:
        model = Quiz
        fields = ['id', 'title', 'difficulty', 'num_questions', 'status',
                  'error_message', 'subject', 'note_name', 'attempt_count',
                  'questions', 'created_at']

    def get_attempt_count(self, obj):
        return obj.attempts.count()


class QuizStatusSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = ['id', 'status', 'error_message', 'question_count']

    def get_question_count(self, obj):
        if obj.status == 'READY':
            return obj.questions.count()
        return 0


class CreateQuizSerializer(serializers.Serializer):
    note_id       = serializers.UUIDField()
    difficulty    = serializers.ChoiceField(choices=['easy', 'moderate', 'difficult'], default='moderate')
    num_questions = serializers.IntegerField(min_value=1, max_value=50, default=10)

    def validate_note_id(self, value):
        from notes.models import NoteUpload, NoteStatus
        try:
            note = NoteUpload.objects.get(pk=value)
        except NoteUpload.DoesNotExist:
            raise serializers.ValidationError('Note not found.')
        if note.status != NoteStatus.READY:
            raise serializers.ValidationError('Note must be READY before generating a quiz.')
        if not note.raw_ocr_text.strip():
            raise serializers.ValidationError('Note has no text content.')
        self.context['note'] = note
        return value

    def validate(self, data):
        note = self.context.get('note')
        request = self.context.get('request')
        if not (note and request and getattr(request, 'user', None) and request.user.school):
            return data  # Visitors have no school — skip threshold check

        subject = note.subject
        if not subject:
            return data

        thresholds = list(TeacherSubjectThreshold.objects.filter(
            school=request.user.school,
            subject__iexact=subject,
        ))
        if not thresholds:
            return data

        max_min_q    = max(t.min_questions for t in thresholds)
        max_min_diff = max(
            (t.min_difficulty for t in thresholds),
            key=lambda d: DIFFICULTY_ORDER.get(d, 0),
        )

        errors = {}
        if data.get('num_questions', 10) < max_min_q:
            errors['num_questions'] = (
                f'Your teacher requires at least {max_min_q} questions for {subject}. '
                f'Update your Quiz Settings or choose a higher count.'
            )
        if DIFFICULTY_ORDER.get(data.get('difficulty', 'moderate'), 0) < DIFFICULTY_ORDER.get(max_min_diff, 0):
            errors['difficulty'] = (
                f'Your teacher requires at least {max_min_diff} difficulty for {subject}. '
                f'Update your Quiz Settings or choose a higher difficulty.'
            )
        if errors:
            raise serializers.ValidationError(errors)
        return data


class TeacherSubjectThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TeacherSubjectThreshold
        fields = ['id', 'subject', 'min_questions', 'min_difficulty', 'updated_at']
        read_only_fields = ['id', 'updated_at']

    def validate_min_questions(self, value):
        if value < 1:
            raise serializers.ValidationError('Must be at least 1.')
        if value > 50:
            raise serializers.ValidationError('Cannot exceed 50.')
        return value


class StudentQuizPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StudentQuizPreferences
        fields = ['id', 'num_questions', 'difficulty', 'updated_at']
        read_only_fields = ['id', 'updated_at']

    def validate_num_questions(self, value):
        if value < 1:
            raise serializers.ValidationError('Must be at least 1.')
        if value > 50:
            raise serializers.ValidationError('Cannot exceed 50.')
        return value


class SubjectLimitsSerializer(serializers.Serializer):
    subject       = serializers.CharField()
    min_questions = serializers.IntegerField()
    min_difficulty = serializers.CharField()


# ── Attempt serializers ───────────────────────────────────────

class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    chosen      = serializers.CharField(max_length=1, allow_blank=True, default='')


class SubmitAttemptSerializer(serializers.Serializer):
    answers      = SubmitAnswerSerializer(many=True)
    time_taken_s = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    def validate_answers(self, value):
        if not value:
            raise serializers.ValidationError('At least one answer is required.')
        return value


class AttemptAnswerResultSerializer(serializers.ModelSerializer):
    question = QuizQuestionWithAnswerSerializer(read_only=True)

    class Meta:
        model = QuizAttemptAnswer
        fields = ['question', 'chosen', 'is_correct']


class AttemptResultSerializer(serializers.ModelSerializer):
    answers       = AttemptAnswerResultSerializer(many=True, read_only=True)
    quiz_title    = serializers.CharField(source='quiz.title', read_only=True)
    quiz_difficulty = serializers.CharField(source='quiz.difficulty', read_only=True)

    class Meta:
        model = QuizAttempt
        fields = ['id', 'quiz_title', 'quiz_difficulty', 'score', 'total',
                  'percentage', 'time_taken_s', 'completed_at', 'answers']
