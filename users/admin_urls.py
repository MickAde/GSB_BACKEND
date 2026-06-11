from django.urls import path

from .admin_views import (
    AdminUserBulkCreateView,
    AdminUserDetailView,
    AdminUserListCreateView,
    AdminUserSetPasswordView,
)

urlpatterns = [
    path('',         AdminUserListCreateView.as_view(),  name='admin-users-list'),
    path('bulk/',    AdminUserBulkCreateView.as_view(),  name='admin-users-bulk'),
    path('<uuid:pk>/',              AdminUserDetailView.as_view(),     name='admin-users-detail'),
    path('<uuid:pk>/set-password/', AdminUserSetPasswordView.as_view(), name='admin-users-set-password'),
]
