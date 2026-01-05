from datetime import datetime, timezone
from typing import List, Dict

from Notion.Property import Property


class Page:
    def __init__(self, page_json: dict):
        self.raw_json: dict = page_json
        self.id: str = page_json["id"]

        date_format = "%Y-%m-%dT%H:%M:%S.%fZ"
        raw_created_time = page_json["created_time"]
        self.created_time: datetime = datetime.strptime(raw_created_time, date_format).replace(tzinfo=timezone.utc)

        raw_modified_time = page_json["last_edited_time"]
        self.last_edited_time: datetime = datetime.strptime(raw_modified_time, date_format).replace(tzinfo=timezone.utc)

        self.created_by: dict = page_json["created_by"]
        self.last_edited_by: dict = page_json["last_edited_by"]

        # TODO fix
        self.cover = page_json["cover"] # idk what this really is
        self.icon = page_json["icon"]
        self.parent = page_json["parent"]

        self.archived: bool = page_json["archived"]
        self.in_trash: bool = page_json["in_trash"]
        self.is_locked: bool = page_json["is_locked"]

        self.url: str = page_json["url"]
        self.public_url: str = page_json["public_url"]

        self.properties: List[Property] = [Property(title, prop_values) for title, prop_values in page_json["properties"].items()]

        self._ordered_props: Dict[str, Property] = {prop.title: prop for prop in self.properties}

    def get_property(self, prop_title: str) -> Property:
        """Returns Property object with given name"""
        result = self._ordered_props.get(prop_title, None)
        if result is None:
            raise KeyError(f"Property {prop_title} not found")
        return result
