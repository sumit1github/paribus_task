from channels.generic.websocket import AsyncWebsocketConsumer

from bulk.constant import BATCH_GROUP_NAME


class BatchProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(BATCH_GROUP_NAME, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(BATCH_GROUP_NAME, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Replies to ResilientSocket heartbeat pings.
        if text_data == "ping":
            await self.send(text_data="pong")

    async def progress_message(self, event):
        await self.send(text_data=event['html'])
