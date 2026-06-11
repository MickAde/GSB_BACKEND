from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form     = UserChangeForm
    add_form = UserCreationForm

    list_display = ('email', 'username', 'role', 'school', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'school')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    readonly_fields = ('id', 'date_joined', 'last_login')

    fieldsets = (
        (None, {'fields': ('id', 'email', 'username', 'password')}),
        ('Profile', {'fields': ('first_name', 'last_name', 'role', 'school')}),
        ('Visitor', {'fields': ('trial_expires_at',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'role', 'school', 'password1', 'password2'),
        }),
    )
