import discord

from Notion.Page import Page
from Notion.Property import Property


class DiscordAPI:
    def __init__(self, interaction):
        self.interaction = interaction

    async def get_messages(self, limit=500, before=None, after=None):
        """Gets all messages before or after a certain time, with a limit on the number of messages."""
        messages_async = self.interaction.channel.history(limit=limit, oldest_first=True, before=before, after=after)
        return [message async for message in messages_async]

    async def think(self):
        """Displays "thinking" message"""
        await self.interaction.response.defer(thinking=True)

    async def followup(self, message, **kwargs):
        """Sends response to thinking message"""
        await self.interaction.followup.send(message, **kwargs)

    async def send_message(self, message, **kwargs):
        """Sends a regular message"""
        await self.interaction.response.send_message(message, **kwargs)

