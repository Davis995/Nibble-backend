
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from authentication.views import SessionView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/session', SessionView.as_view(), name='session-check'),
    path('api/v1/tools/', include("tools.urls")),
    path('api/v1/auth/', include("authentication.urls")),
    path('api/v1/schools/', include("schools.urls")),
    path('api/v1/leads/', include("leads.urls")),
    path('api/v1/payments/', include("payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
