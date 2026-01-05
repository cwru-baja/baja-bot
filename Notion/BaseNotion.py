from Notion.NotionAPI import NotionAPI


class BaseNotion:
    def __init__(self, client: NotionAPI):
        self.client = client