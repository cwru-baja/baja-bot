import requests
from bs4 import BeautifulSoup

class ResultsParser:
    base_url = f"https://results.bajasae.net/MyResults.aspx"

    def __init__(self, car_num=4):
        self.car_num = car_num
        self.car_request_url = self.base_url + f"?carnum={car_num}"

    def get_results(self, event="statics"):
        if event not in ["statics", "dynamics", "endurance"]:
            raise ValueError("Event must be one of statics, dynamics, endurance")

        final_url = self.car_request_url + f"&tab={event}"
        result = requests.get(final_url)
        parsed = BeautifulSoup(result.text, "html.parser")

        if event == "statics":
            return self.parse_statics(parsed)
        else:
            raise NotImplementedError

    def parse_statics(self, parsed):
        table_rows = parsed.select("table.table.table-striped.table-hover")[0].find_all("tr", recursive=False)
        msg = "## Static event results:"
        for row in table_rows:
            # Something like "Cost Report Score (of 15): Not Yet Available"
            result_data = [data.text.strip() for data in row.find_all("td", recursive=False)][:2]
            result_msg = f"*{result_data[0]}* {result_data[1]}"
            msg += result_msg + "\n"
        return msg
