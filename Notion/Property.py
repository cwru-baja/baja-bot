from Notion.BaseNotion import BaseNotion
from Notion.NotionAPI import NotionAPI


class Property(BaseNotion):
    def __init__(self, prop_title, prop_values: dict, client: NotionAPI):
        super().__init__(client)
        self.raw_json: dict = prop_values
        self.title: str = prop_title

        self.id: str | None = prop_values.get("id", None)
        self.type: str = prop_values["type"]

        self.value: dict = prop_values[self.type]

        self.is_set = bool(self.value)

    def __bool__(self):
        return self.is_set