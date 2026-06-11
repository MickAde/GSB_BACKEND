from django import forms
from django.contrib.auth.forms import (
    UserChangeForm as BaseUserChangeForm,
    UserCreationForm as BaseUserCreationForm,
)

from .models import User


class UserChangeForm(BaseUserChangeForm):
    """
    Custom change form for the admin User model.

    Django's built-in UserChangeForm uses UsernameField (which calls len() on
    the value) for the username field. Our username is null=True, so Django's
    ModelForm sets empty_value=None for it. UsernameField.to_python then calls
    len(None) and raises TypeError for any user who has no username
    (teachers, admins, visitors). We replace it with a plain CharField that
    handles None correctly.
    """
    username = forms.CharField(
        max_length=150,
        required=False,
        label='Admission number',
        help_text='Required for STUDENT role only. Leave blank for all other roles.',
    )
    email = forms.EmailField(
        required=False,
        label='Email address',
        help_text='Required for TEACHER, SUB_ADMIN, MAIN_ADMIN, and VISITOR roles.',
    )

    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = '__all__'

    def clean_username(self):
        value = self.cleaned_data.get('username')
        return value.strip() if value and value.strip() else None

    def clean_email(self):
        value = self.cleaned_data.get('email')
        return value.strip() if value and value.strip() else None


class UserCreationForm(BaseUserCreationForm):
    """
    Custom creation form — same null-safe handling for username and email.
    """
    username = forms.CharField(
        max_length=150,
        required=False,
        label='Admission number',
        help_text='Required for STUDENT role only.',
    )
    email = forms.EmailField(
        required=False,
        label='Email address',
        help_text='Required for all roles except STUDENT.',
    )

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ('email', 'username', 'role', 'school')

    def clean_username(self):
        value = self.cleaned_data.get('username')
        return value.strip() if value and value.strip() else None

    def clean_email(self):
        value = self.cleaned_data.get('email')
        return value.strip() if value and value.strip() else None
