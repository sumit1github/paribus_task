from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('hospitals/bulk/', include('bulk.api_urls')),
    path('hospitals/batch/', include('bulk.batch_api_urls')),
    path('hospitals/', include('hospital_management.urls')),
    path('', include('bulk.urls')),
]
