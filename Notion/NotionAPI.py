from notion_client import AsyncClient

from Notion.DataSourceQuery import DataSourceQuery


class NotionAPI:
    def __init__(self, token):
        self.client = AsyncClient(auth=token)
        self.token = token

    async def query_data(self, data_source_id, **kwargs) -> DataSourceQuery:
        raw_json = await self.client.data_sources.query(data_source_id, **kwargs)
        return DataSourceQuery(raw_json)

