import typing
from datetime import datetime
from typing import List, Dict

from baja_notion.base_notion import BaseNotion
from baja_notion.property import Property
from utils import parse_time_utc

if typing.TYPE_CHECKING:
    from baja_notion.notion_api import NotionAPI


class DataSource(BaseNotion):
    def __init__(self, data_source_json: dict, client: "NotionAPI"):
        super().__init__(client)
        self.raw_json = data_source_json

        self.id: str = data_source_json["id"]
        self.created_time: datetime = parse_time_utc(data_source_json["created_time"])
        self.last_edited_time: datetime = parse_time_utc(data_source_json["last_edited_time"])

        self.created_by: dict = data_source_json["created_by"]
        self.last_edited_by: dict = data_source_json["last_edited_by"]

        self.title: Property = data_source_json["title"][0]

        # TODO add
        self.description = data_source_json["description"]

        self.is_inline: bool = data_source_json["is_inline"]

        self.properties: List[Property] = [
            Property(title, prop_json, self.client)
            for title, prop_json in data_source_json["properties"].items()
        ]

        self._ordered_props: Dict[str, Property] = {prop.title.lower(): prop for prop in self.properties}

    def get_property(self, prop_title: str) -> Property:
        """Returns Property object with given name"""
        result = self._ordered_props.get(prop_title.lower(), None)
        if result is None:
            raise KeyError(f"Property {prop_title} not found")
        return result
