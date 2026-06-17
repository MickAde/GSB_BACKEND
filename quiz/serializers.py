from rest_framework import serializers
from .models import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion


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
    num_questions = serializers.IntegerField(min_value=5, max_value=20, default=10)

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
