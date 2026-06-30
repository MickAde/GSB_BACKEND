from django.urls import path

from .admin_views import (
    AdminClassDetailView,
    AdminClassListCreateView,
    AdminCultureView,
    AdminDailyContentDetailView,
    AdminDailyContentListCreateView,
    AdminSchoolView,
    AdminSubjectDetailView,
    AdminSubjectListCreateView,
)

urlpatterns = [
    path('school/',                      AdminSchoolView.as_view(),                   name='admin-school'),
    path('culture/',                     AdminCultureView.as_view(),                  name='admin-culture'),
    path('classes/',                     AdminClassListCreateView.as_view(),           name='admin-class-list'),
    path('classes/<uuid:pk>/',           AdminClassDetailView.as_view(),              name='admin-class-detail'),
    path('subjects/',                    AdminSubjectListCreateView.as_view(),         name='admin-subject-list'),
    path('subjects/<uuid:pk>/',          AdminSubjectDetailView.as_view(),            name='admin-subject-detail'),
    path('daily-content/',               AdminDailyContentListCreateView.as_view(),   name='admin-daily-content-list'),
    path('daily-content/<uuid:pk>/',     AdminDailyContentDetailView.as_view(),       name='admin-daily-content-detail'),
]
