from django.urls import path
from .views import (
    # New lesson document endpoints
    AdminLessonDocDetailView,
    AdminLessonDocListView,
    AdminLessonDocReviewView,
    DistributedLessonDocsView,
    LessonDocDetailView,
    LessonDocListCreateView,
    LessonDocRegenerateSectionView,
    LessonDocSubmitView,
    LessonDocVersionsView,
    # Legacy lesson plan endpoints (kept for backward compat)
    AIAssistView,
    AdminLessonPlanListView,
    AdminLessonPlanReviewView,
    LessonPlanCommentsView,
    LessonPlanDetailView,
    LessonPlanListCreateView,
    SubmitLessonPlanView,
)

urlpatterns = [
    # ── New AI-first lesson documents ──────────────────────────
    path('lesson-docs/',                              LessonDocListCreateView.as_view(),        name='lesson-doc-list'),
    path('lesson-docs/distributed/',                  DistributedLessonDocsView.as_view(),      name='lesson-doc-distributed'),
    path('lesson-docs/<uuid:pk>/',                    LessonDocDetailView.as_view(),            name='lesson-doc-detail'),
    path('lesson-docs/<uuid:pk>/submit/',             LessonDocSubmitView.as_view(),            name='lesson-doc-submit'),
    path('lesson-docs/<uuid:pk>/regenerate-section/', LessonDocRegenerateSectionView.as_view(), name='lesson-doc-regen-section'),
    path('lesson-docs/<uuid:pk>/versions/',           LessonDocVersionsView.as_view(),          name='lesson-doc-versions'),

    # ── Legacy lesson plans (kept for backward compat) ─────────
    path('lesson-plans/',                        LessonPlanListCreateView.as_view(),  name='lesson-plan-list'),
    path('lesson-plans/<uuid:pk>/',              LessonPlanDetailView.as_view(),      name='lesson-plan-detail'),
    path('lesson-plans/<uuid:pk>/submit/',       SubmitLessonPlanView.as_view(),      name='lesson-plan-submit'),
    path('lesson-plans/<uuid:pk>/ai-assist/',    AIAssistView.as_view(),              name='lesson-plan-ai-assist'),
    path('lesson-plans/<uuid:pk>/comments/',     LessonPlanCommentsView.as_view(),    name='lesson-plan-comments'),
]

# Admin URLs are registered separately under /api/v1/admin/ in core/urls.py
admin_urlpatterns = [
    path('lesson-docs/',                              AdminLessonDocListView.as_view(),   name='admin-lesson-doc-list'),
    path('lesson-docs/<uuid:pk>/',                    AdminLessonDocDetailView.as_view(), name='admin-lesson-doc-detail'),
    path('lesson-docs/<uuid:pk>/review/',             AdminLessonDocReviewView.as_view(), name='admin-lesson-doc-review'),
    # Legacy
    path('lesson-plans/',                             AdminLessonPlanListView.as_view(),  name='admin-lesson-plan-list'),
    path('lesson-plans/<uuid:pk>/review/',            AdminLessonPlanReviewView.as_view(), name='admin-lesson-plan-review'),
]
