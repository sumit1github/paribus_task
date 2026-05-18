from django.urls import path

from .views import BatchActivateView, BatchDeleteView, BulkUploadView

app_name = 'bulk'

urlpatterns = [
    path('', BulkUploadView.as_view(), name='upload'),
    path('activate/', BatchActivateView.as_view(), name='activate'),
    path('delete/', BatchDeleteView.as_view(), name='delete'),
]
