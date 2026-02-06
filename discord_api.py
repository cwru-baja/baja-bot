class DiscordAPI:
    def __init__(self, interaction):
        self.interaction = interaction

    async def get_messages(self, limit=500, before=None, after=None):
        """Gets all messages before or after a certain time, with a limit on the number of messages."""
        messages_async = self.interaction.channel.history(limit=limit, oldest_first=True, before=before, after=after)
        return [message async for message in messages_async]

    async def get_messages_with_threads(self, limit=500, after=None):
        """Gets messages for a channel and all threads within the timeframe."""
        channel = self.interaction.channel
        messages = []

        # Channel history
        messages_async = channel.history(limit=limit, oldest_first=True, after=after)
        messages.extend([message async for message in messages_async])

        # Collect active threads
        thread_ids = set()
        threads = []
        for thread in getattr(channel, "threads", []):
            if thread.id not in thread_ids:
                thread_ids.add(thread.id)
                threads.append(thread)

        # Archived threads (public and private if permitted)
        try:
            async for thread in channel.archived_threads(limit=None):
                if thread.id not in thread_ids:
                    thread_ids.add(thread.id)
                    threads.append(thread)
        except Exception:
            pass

        try:
            async for thread in channel.archived_threads(limit=None, private=True):
                if thread.id not in thread_ids:
                    thread_ids.add(thread.id)
                    threads.append(thread)
        except Exception:
            pass

        # Thread histories
        for thread in threads:
            try:
                thread_messages = thread.history(limit=limit, oldest_first=True, after=after)
                messages.extend([message async for message in thread_messages])
            except Exception:
                continue

        # Sort for consistent ordering
        messages.sort(key=lambda msg: msg.created_at)
        return messages

    async def think(self):
        """Displays "thinking" message"""
        await self.interaction.response.defer(thinking=True)

    async def followup(self, message, **kwargs):
        """Sends response to thinking message"""
        await self.interaction.followup.send(message, **kwargs)

    async def send_message(self, message, **kwargs):
        """Sends a regular message"""
        await self.interaction.response.send_message(message, **kwargs)

