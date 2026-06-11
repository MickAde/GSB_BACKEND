from django.urls import path

from .admin_views import (
    AdminCultureView,
    AdminDailyContentDetailView,
    AdminDailyContentListCreateView,
    AdminSchoolView,
)

urlpatterns = [
    path('school/',                      AdminSchoolView.as_view(),                   name='admin-school'),
    path('culture/',                     AdminCultureView.as_view(),                  name='admin-culture'),
    path('daily-content/',               AdminDailyContentListCreateView.as_view(),   name='admin-daily-content-list'),
    path('daily-content/<uuid:pk>/',     AdminDailyContentDetailView.as_view(),       name='admin-daily-content-detail'),
]
