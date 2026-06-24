from django.urls import include, path

from schools.views import DailyContentTodayView
from teaching.urls import admin_urlpatterns as teaching_admin_urlpatterns
from teaching.views import AdminLessonPlanListView, AdminLessonPlanReviewView

urlpatterns = [
    # ── Public / auth ─────────────────────────────────────────
    path('schools/',        include('schools.urls')),
    path('auth/',           include('users.urls')),
    path('notes/',          include('notes.urls')),

    # ── Quiz & performance ────────────────────────────────────
    path('quiz/',           include('quiz.urls')),

    # ── Teaching (lesson docs + legacy lesson plans) ──────────
    path('',                include('teaching.urls')),

    # ── Daily content (all authenticated users) ───────────────
    path('daily-content/today/', DailyContentTodayView.as_view(), name='daily-content-today'),

    # ── School admin endpoints ────────────────────────────────
    path('admin/users/',          include('users.admin_urls')),
    path('admin/',                include('schools.admin_urls')),
    path('admin/',                include((teaching_admin_urlpatterns, 'teaching-admin'))),
    # Legacy admin lesson-plan routes kept for backward compat
    path('admin/lesson-plans/',              AdminLessonPlanListView.as_view(),   name='admin-lesson-plan-list'),
    path('admin/lesson-plans/<uuid:pk>/review/', AdminLessonPlanReviewView.as_view(), name='admin-lesson-plan-review'),

    # ── Platform owner endpoints ──────────────────────────────
    path('platform/schools/', include('schools.platform_urls')),
]
