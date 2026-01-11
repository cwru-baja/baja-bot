from datetime import datetime, timezone
from typing import List, Dict

from Notion.BaseNotion import BaseNotion
from Notion.Property import Property
from utils import parse_time_utc

import typing

if typing.TYPE_CHECKING:
    from Notion.NotionAPI import NotionAPI


class Page(BaseNotion):
    def __init__(self, page_json: dict, client: "NotionAPI"):
        super().__init__(client)
        self.raw_json: dict = page_json
        self.id: str = page_json["id"]

        self.created_time: datetime = parse_time_utc(page_json["created_time"])

        self.last_edited_time: datetime = parse_time_utc(page_json["last_edited_time"])

        self.created_by: dict = page_json["created_by"]
        self.last_edited_by: dict = page_json["last_edited_by"]

        # TODO fix
        self.cover = page_json["cover"]  # idk what this really is
        self.icon = page_json["icon"]
        self.parent = page_json["parent"]

        self.archived: bool = page_json["archived"]
        self.in_trash: bool = page_json["in_trash"]
        self.is_locked: bool = page_json["is_locked"]

        self.url: str = page_json["url"]
        self.public_url: str = page_json["public_url"]

        self.properties: List[Property] = [Property(title, prop_values, self.client) for title, prop_values in
                                           page_json["properties"].items()]

        self._ordered_props: Dict[str, Property] = {prop.title.lower(): prop for prop in self.properties}

    def get_property(self, prop_title: str) -> Property:
        """Returns Property object with given name"""
        result = self._ordered_props.get(prop_title.lower(), None)
        if result is None:
            raise KeyError(f"Property {prop_title} not found")
        return result

    async def update(self, property: Property, value: dict):
        update_dict = {
            property.title: value
        }
        # print(update_dict)
        await self.client.pages.update(self.id,
                                       properties=update_dict)
