# import pyperclip
# import json
from notion_client import AsyncClient

from Notion.DataSource import DataSource
from Notion.DataSourceQuery import DataSourceQuery


class NotionAPI(AsyncClient):
    def __init__(self, token):
        super().__init__(auth=token)
        # self.client = AsyncClient(auth=token)
        # self.token = token

    async def query_data(self, data_source_id, **kwargs) -> DataSourceQuery:
        raw_json = await self.data_sources.query(data_source_id, **kwargs)
        return DataSourceQuery(raw_json, self)

    async def retrieve_data(self, data_source_id, **kwargs) -> DataSource:
        return DataSource(await self.data_sources.retrieve(data_source_id, **kwargs), self)

