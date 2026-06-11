from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

admin.site.site_header = 'Genius Study Buddy — Admin'
admin.site.site_title = 'GSB Admin'
admin.site.index_title = 'Platform Administration'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('core.urls')),

    # OpenAPI schema + docs (disable in production via SERVE_INCLUDE_SCHEMA=False in settings)
    path('api/v1/schema/',  SpectacularAPIView.as_view(),                            name='schema'),
    path('api/v1/docs/',    SpectacularSwaggerView.as_view(url_name='schema'),       name='swagger-ui'),
    path('api/v1/redoc/',   SpectacularRedocView.as_view(url_name='schema'),         name='redoc'),
]
