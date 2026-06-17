from django.contrib import admin
from .models import LessonPlan, LessonPlanComment


class LessonPlanCommentInline(admin.TabularInline):
    model = LessonPlanComment
    extra = 0
    readonly_fields = ('author', 'created_at')


@admin.register(LessonPlan)
class LessonPlanAdmin(admin.ModelAdmin):
    list_display  = ('title', 'teacher', 'subject', 'status', 'created_at')
    list_filter   = ('status', 'subject')
    search_fields = ('title', 'teacher__email', 'teacher__username')
    inlines       = [LessonPlanCommentInline]
    readonly_fields = ('created_at', 'updated_at')
