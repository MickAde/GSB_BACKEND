from django.urls import path

from .views import ActiveSchoolListView, SchoolCultureView, SchoolDetailView, SubjectListView

urlpatterns = [
    # ── Public ────────────────────────────────────────────────
    path('active/',            ActiveSchoolListView.as_view(), name='schools-active'),
    path('<uuid:pk>/',         SchoolDetailView.as_view(),     name='schools-detail'),
    path('<uuid:pk>/culture/', SchoolCultureView.as_view(),    name='schools-culture'),

    # ── Authenticated: subjects ───────────────────────────────
    path('subjects/',          SubjectListView.as_view(),      name='schools-subjects'),
]
