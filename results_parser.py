import requests
from bs4 import BeautifulSoup


class ResultsParser:
    base_url = "https://results.bajasae.net/MyResults.aspx"
    supported_events = ("statics", "dynamics", "endurance")
    event_titles = {
        "statics": "Static event results",
        "dynamics": "Dynamic event results",
        "endurance": "Endurance results",
    }

    def __init__(self, car_num=4):
        self.car_num = car_num
        self.car_request_url = self.base_url + f"?carnum={car_num}"

    def get_results(self, event="statics"):
        if event not in self.supported_events:
            raise ValueError("Event must be one of statics, dynamics, endurance")

        final_url = self.car_request_url + f"&tab={event}"
        result = requests.get(final_url, timeout=15)
        result.raise_for_status()
        parsed = BeautifulSoup(result.text, "html.parser")

        return getattr(self, f"parse_{event}")(parsed)

    def parse_statics(self, parsed):
        table = parsed.select_one("#MainContent_pnlTabStatics table.table.table-striped.table-hover")
        if table is None:
            return self._build_message(
                self.event_titles["statics"],
                [],
                "Static results are not available yet.",
            )

        return self._build_message(
            self.event_titles["statics"],
            self._parse_key_value_table(table),
            "Static results are not available yet.",
        )

    def parse_dynamics(self, parsed):
        panel = parsed.select_one("#MainContent_pnlTabDynamics")
        if panel is None:
            return self._build_message(
                self.event_titles["dynamics"],
                [],
                "Dynamic results are not available yet.",
            )

        no_results_message = self._extract_no_results(
            panel,
            "#MainContent_lblDynamicResults",
            "Dynamic results are not available yet.",
        )
        if no_results_message is not None:
            return no_results_message

        lines = []
        for table in panel.select("table"):
            lines.extend(self._parse_table(table))

        return self._build_message(
            self.event_titles["dynamics"],
            lines,
            "Dynamic results are not available yet.",
        )

    def parse_endurance(self, parsed):
        panel = parsed.select_one("#MainContent_pnlTabEndurance")
        if panel is None:
            return self._build_message(
                self.event_titles["endurance"],
                [],
                "Endurance results are not available yet.",
            )

        no_results_message = self._extract_no_results(
            panel,
            "#MainContent_lblEnduranceResults",
            "Endurance results are not available yet.",
        )
        if no_results_message is not None:
            return no_results_message

        lines = []
        summary_values = self._extract_key_value_pairs(panel)
        summary_fields = [
            "Lap Count",
            "Current Position",
            "Best Lap Time",
            "Second-Best Lap Time",
            "Average Lap Time",
            "Most Recent Lap Time",
            "Second Most Recent Lap Time",
            "Third Most Recent Lap Time",
            "Last Checkpoint",
            "Race Flag Status",
            "Race Time",
            "Last Update Time",
            "Current Race Leader",
            "Leader Laps",
            "Overall Best Lap By",
            "Overall Best Lap Time",
        ]

        for field in summary_fields:
            value = summary_values.get(field)
            if value:
                lines.append(f"*{field}:* {value}")

        checkpoint_lines = self._parse_checkpoint_rows(panel)
        if checkpoint_lines:
            lines.append("**Recent checkpoints**")
            lines.extend(checkpoint_lines[-3:])

        if not lines:
            for table in panel.select("table"):
                lines.extend(self._parse_table(table))

        return self._build_message(
            self.event_titles["endurance"],
            lines,
            "Endurance results are not available yet.",
        )

    def _extract_no_results(self, panel, selector, fallback_text):
        no_results = panel.select_one(selector)
        if no_results is None:
            return None

        message = self._clean_text(no_results.get_text(" ", strip=True))
        if message:
            return self._build_message(
                self._panel_title(panel),
                [],
                fallback_text if "No " in message else message,
            )
        return None

    def _parse_table(self, table):
        headers = self._table_headers(table)
        if headers:
            return self._parse_header_table(table, headers)
        return self._parse_key_value_table(table)

    def _parse_key_value_table(self, table):
        lines = []
        for row in table.find_all("tr"):
            cells = self._row_cells(row)
            if len(cells) < 2:
                continue

            label = cells[0].rstrip(":")
            value = cells[1]
            if not label or not value:
                continue

            lines.append(f"*{label}:* {value}")
        return lines

    def _parse_header_table(self, table, headers):
        lines = []
        for row in table.find_all("tr")[1:]:
            cells = self._row_cells(row)
            if not cells or not any(cells):
                continue

            label = cells[0] if cells[0] else headers[0]
            details = []
            for header, value in zip(headers[1:], cells[1:]):
                if value:
                    details.append(f"{header}: {value}")

            if details:
                lines.append(f"*{label}:* {' | '.join(details)}")
            elif label:
                lines.append(f"*{label}:*")
        return lines

    def _parse_checkpoint_rows(self, panel):
        for table in panel.select("table"):
            headers = self._table_headers(table)
            if not headers or "Checkpoint" not in headers:
                continue
            return self._parse_header_table(table, headers)
        return []

    def _extract_key_value_pairs(self, panel):
        pairs = {}
        for table in panel.select("table"):
            if self._table_headers(table):
                continue

            for row in table.find_all("tr"):
                cells = self._row_cells(row)
                if len(cells) < 2:
                    continue

                label = cells[0].rstrip(":")
                value = cells[1]
                if label and value:
                    pairs[label] = value
        return pairs

    def _table_headers(self, table):
        header_row = table.find("tr")
        if header_row is None or not header_row.find("th"):
            return []
        return self._row_cells(header_row)

    def _row_cells(self, row):
        cells = row.find_all(["th", "td"], recursive=False)
        return [self._clean_text(cell.get_text(" ", strip=True)) for cell in cells]

    def _panel_title(self, panel):
        heading = panel.find(["h1", "h2", "h3"])
        if heading is None:
            return "Results"
        return self._clean_text(heading.get_text(" ", strip=True))

    def _build_message(self, title, lines, empty_message):
        visible_lines = [line for line in lines if line]
        message = f"**{title}**\n"
        if visible_lines:
            message += "\n".join(visible_lines)
        else:
            message += empty_message

        if len(message) > 1900:
            message = message[:1890].rstrip() + "\n..."
        return message

    def _clean_text(self, text):
        return " ".join(text.replace("\xa0", " ").split()).strip()
