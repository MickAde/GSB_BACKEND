from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AvatarView,
    ChangePasswordView,
    EmailVerifyView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterVisitorView,
    ResendVerificationView,
)

# Override simplejwt's default tag so this appears under "Auth" in Swagger UI.
_TokenRefreshView = extend_schema(tags=['Auth'])(TokenRefreshView)

urlpatterns = [
    # ── Authentication ────────────────────────────────────────
    path('login/',             LoginView.as_view(),            name='auth-login'),
    path('token/refresh/',     _TokenRefreshView.as_view(),    name='auth-token-refresh'),
    path('register/visitor/',  RegisterVisitorView.as_view(),  name='auth-register-visitor'),
    path('logout/',            LogoutView.as_view(),           name='auth-logout'),

    # ── Own profile ───────────────────────────────────────────
    path('me/',                MeView.as_view(),               name='auth-me'),
    path('me/avatar/',         AvatarView.as_view(),           name='auth-me-avatar'),

    # ── Password management ───────────────────────────────────
    path('password/change/',          ChangePasswordView.as_view(),        name='auth-password-change'),
    path('password/reset/',           PasswordResetRequestView.as_view(),  name='auth-password-reset'),
    path('password/reset/confirm/',   PasswordResetConfirmView.as_view(),  name='auth-password-reset-confirm'),

    # ── Email verification ────────────────────────────────────
    path('verify-email/',             EmailVerifyView.as_view(),           name='auth-verify-email'),
    path('resend-verification/',      ResendVerificationView.as_view(),    name='auth-resend-verification'),
]
