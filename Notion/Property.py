class Property:
    def __init__(self, prop_title, prop_values: dict):
        self.raw_json: dict = prop_values
        self.title: str = prop_title

        self.id: str = prop_values["id"]
        self.type: str = prop_values["type"]

        self.value: dict = prop_values[self.type]

        self.is_set = bool(self.value)

    def __bool__(self):
        return self.is_set