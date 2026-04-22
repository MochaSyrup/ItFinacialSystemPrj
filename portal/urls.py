from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.monitoring.urls')),
    path('interfaces/', include('apps.interfaces.urls')),
    path('evaluation/', include('apps.evaluation.urls')),
]
