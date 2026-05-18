from django.urls import path

from .api_views import BatchActivateAPIView, BatchHospitalsAPIView

app_name = 'batch_api'

urlpatterns = [
    path('<uuid:batch_id>', BatchHospitalsAPIView.as_view(), name='hospitals'),
    path('<uuid:batch_id>/activate', BatchActivateAPIView.as_view(), name='activate'),
]
