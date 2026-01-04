from notion_client import AsyncClient

class NotionAPI:
    def __init__(self, token):
        self.client = AsyncClient(auth=token)
        self.token = token

    async def query_data(self, data_source_id, filter_obj):
        return await self.client.data_sources.query(data_source_id, filter=filter_obj)

