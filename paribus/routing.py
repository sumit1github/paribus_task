from django.urls import re_path

from bulk.consumers import BatchProgressConsumer

websocket_urlpatterns = [
    re_path(r'^ws/batch/(?P<batch_id>[\w-]+)/$', BatchProgressConsumer.as_asgi()),
]
