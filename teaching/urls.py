from django.urls import path
from .views import (
    AIAssistView,
    LessonPlanCommentsView,
    LessonPlanDetailView,
    LessonPlanListCreateView,
    SubmitLessonPlanView,
)

urlpatterns = [
    path('',            LessonPlanListCreateView.as_view(), name='lesson-plan-list'),
    path('<uuid:pk>/',            LessonPlanDetailView.as_view(),     name='lesson-plan-detail'),
    path('<uuid:pk>/submit/',     SubmitLessonPlanView.as_view(),     name='lesson-plan-submit'),
    path('<uuid:pk>/ai-assist/',  AIAssistView.as_view(),             name='lesson-plan-ai-assist'),
    path('<uuid:pk>/comments/',   LessonPlanCommentsView.as_view(),   name='lesson-plan-comments'),
]
