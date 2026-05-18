from django.urls import path

from .api_views import (
    BulkResumeAPIView,
    BulkStatusAPIView,
    BulkUploadAPIView,
    BulkValidateAPIView,
)

app_name = 'bulk_api'

urlpatterns = [
    path('', BulkUploadAPIView.as_view(), name='upload'),
    path('validate', BulkValidateAPIView.as_view(), name='validate'),
    path('<uuid:batch_id>', BulkStatusAPIView.as_view(), name='status'),
    path('<uuid:batch_id>/resume', BulkResumeAPIView.as_view(), name='resume'),
]
