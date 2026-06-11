from django.contrib import admin
from .models import NoteUpload, NoteConformityReport


@admin.register(NoteUpload)
class NoteUploadAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'owner', 'school', 'note_type', 'status', 'created_at')
    list_filter = ('status', 'note_type', 'subject')
    search_fields = ('file_name', 'owner__email', 'owner__username', 'subject')
    readonly_fields = ('id', 'ocr_task_id', 'ai_task_id', 'created_at', 'updated_at')
    raw_id_fields = ('owner', 'school')


@admin.register(NoteConformityReport)
class NoteConformityReportAdmin(admin.ModelAdmin):
    list_display = ('student_note', 'teacher_note', 'conformity_percentage', 'generated_at')
    readonly_fields = ('id', 'generated_at')
