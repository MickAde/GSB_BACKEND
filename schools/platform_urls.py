from django.urls import path

from .platform_views import PlatformSchoolDetailView, PlatformSchoolListCreateView

urlpatterns = [
    path('',          PlatformSchoolListCreateView.as_view(), name='platform-schools-list'),
    path('<uuid:pk>/', PlatformSchoolDetailView.as_view(),    name='platform-schools-detail'),
]
