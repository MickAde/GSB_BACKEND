from django.contrib import admin
from .models import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion


class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 0
    fields = ('order', 'question_type', 'question_text', 'correct')
    readonly_fields = ('order',)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display  = ('title', 'owner', 'difficulty', 'num_questions', 'status', 'created_at')
    list_filter   = ('status', 'difficulty')
    search_fields = ('title', 'owner__email', 'owner__username')
    inlines       = [QuizQuestionInline]
    readonly_fields = ('ai_task_id',)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display  = ('student', 'quiz', 'score', 'total', 'percentage', 'completed_at')
    list_filter   = ('quiz__difficulty',)
    search_fields = ('student__email', 'student__username', 'quiz__title')
