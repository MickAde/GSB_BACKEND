from django.urls import path
from .views import (
    AttemptResultView,
    CreateQuizView,
    ListQuizzesView,
    PerformanceStatsView,
    QuizDetailView,
    QuizStatusView,
    SubmitAttemptView,
    TeacherStudentStatsView,
)

urlpatterns = [
    # Student / Visitor quiz endpoints
    path('',               ListQuizzesView.as_view(),    name='quiz-list'),
    path('create/',        CreateQuizView.as_view(),     name='quiz-create'),
    path('performance/',   PerformanceStatsView.as_view(), name='quiz-performance'),
    path('<uuid:pk>/',            QuizDetailView.as_view(),   name='quiz-detail'),
    path('<uuid:pk>/status/',     QuizStatusView.as_view(),   name='quiz-status'),
    path('<uuid:pk>/attempt/',    SubmitAttemptView.as_view(), name='quiz-attempt-submit'),
    path('<uuid:pk>/attempt/result/', AttemptResultView.as_view(), name='quiz-attempt-result'),

    # Teacher monitoring
    path('teacher/students/', TeacherStudentStatsView.as_view(), name='teacher-students'),
]
