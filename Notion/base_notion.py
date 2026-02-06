import typing

if typing.TYPE_CHECKING:
    from notion.notion_api import NotionAPI


class BaseNotion:
    def __init__(self, client: "NotionAPI"):
        self.client: "NotionAPI" = client