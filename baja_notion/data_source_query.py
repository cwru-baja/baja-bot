import typing
from typing import List

from baja_notion.base_notion import BaseNotion
from baja_notion.page import Page

if typing.TYPE_CHECKING:
    from baja_notion.notion_api import NotionAPI


class DataSourceQuery(BaseNotion):
    def __init__(self, query_json: dict, client: "NotionAPI"):
        super().__init__(client)
        self.raw_json: dict = query_json

        self.request_id: str = query_json["request_id"]

        # TODO see what the format of this is
        self.next_cursor = query_json["next_cursor"]
        self.has_more: bool = query_json["has_more"]
        self.type: str = query_json["type"]
        self.results: List[Page] = [Page(page_json, self.client) for page_json in query_json["results"]]

    def __len__(self):
        return len(self.results)
