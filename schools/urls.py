from django.urls import path

from .views import ActiveSchoolListView, SchoolCultureView, SchoolDetailView

urlpatterns = [
    # ── Public ────────────────────────────────────────────────
    path('active/',           ActiveSchoolListView.as_view(), name='schools-active'),
    path('<uuid:pk>/',        SchoolDetailView.as_view(),     name='schools-detail'),
    path('<uuid:pk>/culture/', SchoolCultureView.as_view(),   name='schools-culture'),
]
