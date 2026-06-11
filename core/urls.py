from django.urls import include, path

from schools.views import DailyContentTodayView

urlpatterns = [
    # ── Public / auth ─────────────────────────────────────────
    path('schools/',        include('schools.urls')),
    path('auth/',           include('users.urls')),
    path('notes/',          include('notes.urls')),

    # ── Daily content (all authenticated users) ───────────────
    path('daily-content/today/', DailyContentTodayView.as_view(), name='daily-content-today'),

    # ── School admin endpoints ────────────────────────────────
    # /api/v1/admin/users/         → user management
    # /api/v1/admin/culture/       → school culture upsert
    # /api/v1/admin/daily-content/ → school daily content CRUD
    path('admin/users/',  include('users.admin_urls')),
    path('admin/',        include('schools.admin_urls')),

    # ── Platform owner endpoints ──────────────────────────────
    # /api/v1/platform/schools/  → onboard / manage school tenants
    path('platform/schools/', include('schools.platform_urls')),
]
