from django.contrib import admin
from .models import School, SchoolCulture, DailyContent


class SchoolCultureInline(admin.StackedInline):
    model = SchoolCulture
    extra = 0


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'onboarding_date')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'contact_email')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SchoolCultureInline]
    readonly_fields = ('id', 'onboarding_date', 'created_at', 'updated_at')


@admin.register(DailyContent)
class DailyContentAdmin(admin.ModelAdmin):
    list_display = ('content_type', 'school', 'display_date', 'author')
    list_filter = ('content_type', 'display_date')
    search_fields = ('body', 'author')
    date_hierarchy = 'display_date'
