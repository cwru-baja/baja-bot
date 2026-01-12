from typing import List

from Notion.BaseNotion import BaseNotion
from Notion.Page import Page

import typing

if typing.TYPE_CHECKING:
    from Notion.NotionAPI import NotionAPI

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