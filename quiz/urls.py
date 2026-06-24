from django.urls import path
from .views import (
    AttemptResultView,
    CreateQuizView,
    ListQuizzesView,
    PerformanceStatsView,
    QuizDetailView,
    QuizStatusView,
    StudentQuizPreferencesView,
    SubjectLimitsView,
    SubjectStatsView,
    SubmitAttemptView,
    TeacherStudentStatsView,
    TeacherThresholdDetailView,
    TeacherThresholdListCreateView,
    TopicStatsView,
)

urlpatterns = [
    # Student / Visitor quiz endpoints
    path('',                  ListQuizzesView.as_view(),       name='quiz-list'),
    path('create/',           CreateQuizView.as_view(),        name='quiz-create'),
    path('performance/',      PerformanceStatsView.as_view(),  name='quiz-performance'),
    path('preferences/',      StudentQuizPreferencesView.as_view(), name='quiz-preferences'),
    path('subject-limits/',   SubjectLimitsView.as_view(),     name='quiz-subject-limits'),
    path('subject-stats/',    SubjectStatsView.as_view(),      name='quiz-subject-stats'),
    path('topic-stats/',      TopicStatsView.as_view(),        name='quiz-topic-stats'),
    path('<uuid:pk>/',             QuizDetailView.as_view(),         name='quiz-detail'),
    path('<uuid:pk>/status/',      QuizStatusView.as_view(),         name='quiz-status'),
    path('<uuid:pk>/attempt/',     SubmitAttemptView.as_view(),      name='quiz-attempt-submit'),
    path('<uuid:pk>/attempt/result/', AttemptResultView.as_view(),   name='quiz-attempt-result'),

    # Teacher thresholds + monitoring
    path('teacher/thresholds/',           TeacherThresholdListCreateView.as_view(), name='teacher-thresholds'),
    path('teacher/thresholds/<uuid:pk>/', TeacherThresholdDetailView.as_view(),     name='teacher-threshold-detail'),
    path('teacher/students/',             TeacherStudentStatsView.as_view(),        name='teacher-students'),
]
