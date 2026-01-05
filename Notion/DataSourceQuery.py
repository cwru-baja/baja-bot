from typing import List

from Notion.Page import Page


class DataSourceQuery:
    def __init__(self, query_json: dict):
        self.raw_json: dict = query_json
        self.request_id: str = query_json["request_id"]

        # TODO see what the format of this is
        self.next_cursor = query_json["next_cursor"]
        self.has_more: bool = query_json["has_more"]
        self.type: str = query_json["type"]
        self.results: List[Page] = [Page(page_json) for page_json in query_json["results"]]

    def __len__(self):
        return len(self.results)