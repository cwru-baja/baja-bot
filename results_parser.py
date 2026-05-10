import re
from collections import defaultdict

import requests
from bs4 import BeautifulSoup


class ResultsParser:
    base_url = "https://results.bajasae.net/MyResults.aspx"
    event_results_url = "https://results.bajasae.net/EventResults.aspx"
    static_event_names = {"businesspresentation", "costevent", "design"}
    supported_events = ("statics", "dynamics", "endurance")
    event_titles = {
        "statics": "Static event results",
        "dynamics": "Dynamic event results",
        "endurance": "Endurance results",
    }
    dynamic_event_points = 70.0
    endurance_event_points = 400.0

    def __init__(self, car_num=4):
        self.car_num = car_num
        self.car_request_url = self.base_url + f"?carnum={car_num}"
        self.session = requests.Session()
        self._event_results_cache = {}

    def get_results(self, event="statics"):
        if event not in self.supported_events:
            raise ValueError("Event must be one of statics, dynamics, endurance")

        final_url = self.car_request_url + f"&tab={event}"
        result = self.session.get(final_url, timeout=15)
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

        dynamic_table = panel.select_one("#MainContent_GridViewDynamicResults")
        if dynamic_table is not None:
            dynamic_rows = self._parse_table_records(dynamic_table)
            if dynamic_rows:
                return self._build_dynamic_results_message(dynamic_rows)

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

    def get_predicted_dynamic_scores(self, limit=10):
        leaderboard = self._build_predicted_dynamic_leaderboard()
        if not leaderboard["available_events"]:
            return "**Live predicted dynamic scores**\nNo dynamic event results are available yet."

        lines = []
        for index, team in enumerate(leaderboard["ranked_teams"][:limit], start=1):
            parts = [f"{abbr} {team['event_scores'][event_name]['score']:.2f} (#{team['event_scores'][event_name]['rank']})"
                     for event_name, abbr in leaderboard["event_abbreviations"].items()
                     if event_name in team["event_scores"]]
            line = (
                f"{index}. #{team['car_no']} {team['display_name']} - "
                f"{team['total_score']:.2f} pts | {' | '.join(parts)}"
            )
            lines.append(line)

        header = (
            f"**Live predicted dynamic scores**\n"
            f"Available now: {len(leaderboard['available_events'])} event(s), "
            f"{leaderboard['available_points']:.0f} pts live "
            f"(2026 rules total dynamic pool: 680 pts, PDF p. 103).\n"
        )

        if leaderboard["pending_events"]:
            header += "Pending: " + ", ".join(leaderboard["pending_events"]) + "\n"

        return self._build_message(
            "Live predicted dynamic scores",
            lines,
            "No dynamic event results are available yet.",
        ).replace("**Live predicted dynamic scores**\n", header, 1)

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

    def _parse_table_records(self, table):
        headers = self._table_headers(table)
        if not headers:
            return []

        records = []
        for row in table.find_all("tr")[1:]:
            cells = self._row_cells(row)
            if not cells or not any(cells):
                continue

            record = {}
            for header, value in zip(headers, cells):
                if header:
                    record[header] = value
            records.append(record)
        return records

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

    def _build_dynamic_results_message(self, dynamic_rows):
        grouped_rows, event_order = self._group_dynamic_rows(dynamic_rows)
        score_details = self._calculate_dynamic_scores(grouped_rows)

        lines = []
        subtotal = 0.0
        subtotal_possible = 0.0

        for event_name in event_order:
            best_row = self._select_best_dynamic_row(grouped_rows[event_name], event_name)
            summary = self._summarize_dynamic_row(best_row)

            score_info = score_details.get(event_name, {})
            if score_info.get("score") is not None:
                summary.append(f"Score: {score_info['score']:.2f}")
                subtotal += score_info["score"]
                subtotal_possible += score_info["possible_points"]
            elif score_info.get("note"):
                summary.append(f"Score: {score_info['note']}")

            lines.append(f"*{event_name}:* {' | '.join(summary)}")

        if subtotal_possible:
            lines.append(
                f"**Calculated dynamic subtotal:** {subtotal:.2f} / {subtotal_possible:.0f}"
            )

        return self._build_message(
            self.event_titles["dynamics"],
            lines,
            "Dynamic results are not available yet.",
        )

    def _build_predicted_dynamic_leaderboard(self):
        available_events = []
        pending_events = []
        team_totals = {}
        event_abbreviations = {}
        available_points = 0.0

        for event_name in self._fetch_dynamic_event_names():
            benchmark_rows = self._fetch_event_result_rows(event_name)
            if not benchmark_rows:
                pending_events.append(event_name)
                continue

            event_type = self._infer_dynamic_event_type(event_name, rows=benchmark_rows)
            possible_points = self._event_possible_points(event_name, event_type)
            event_scores = []
            for row in benchmark_rows:
                score = self._score_dynamic_event(event_name, event_type, row, benchmark_rows)
                if score is None:
                    score = 0.0

                entry = {
                    "car_no": row.get("car_no"),
                    "display_name": self._display_name(row),
                    "score": round(score, 2),
                    "row": row,
                }
                event_scores.append(entry)

            ranked_event_scores = self._rank_score_entries(event_scores)
            available_events.append(event_name)
            event_abbreviations[event_name] = self._event_abbreviation(event_name)
            available_points += possible_points

            for entry in ranked_event_scores:
                car_no = entry["car_no"]
                if not car_no:
                    continue

                if car_no not in team_totals:
                    team_totals[car_no] = {
                        "car_no": car_no,
                        "display_name": entry["display_name"],
                        "total_score": 0.0,
                        "event_scores": {},
                    }

                team_totals[car_no]["total_score"] += entry["score"]
                team_totals[car_no]["event_scores"][event_name] = {
                    "score": entry["score"],
                    "rank": entry["rank"],
                }

        ranked_teams = self._rank_score_entries(list(team_totals.values()), score_key="total_score")
        return {
            "available_events": available_events,
            "pending_events": pending_events,
            "available_points": available_points,
            "event_abbreviations": event_abbreviations,
            "ranked_teams": ranked_teams,
        }

    def _group_dynamic_rows(self, rows):
        grouped = defaultdict(list)
        event_order = []
        for row in rows:
            event_name = row.get("Event")
            if not event_name:
                continue
            if event_name not in grouped:
                event_order.append(event_name)
            grouped[event_name].append(row)
        return grouped, event_order

    def _summarize_dynamic_row(self, row):
        summary = []

        status = row.get("Status")
        if status:
            summary.append(f"Status: {status}")

        position = row.get("Position")
        if position:
            summary.append(f"Position: {position}")

        corrected_time = row.get("Corrected Time")
        if corrected_time:
            summary.append(f"Corrected Time: {corrected_time}")

        raw_time = row.get("Raw Time")
        if raw_time and raw_time != corrected_time:
            summary.append(f"Raw Time: {raw_time}")

        major_penalty = row.get("Major Penalty")
        if major_penalty and major_penalty != "0":
            summary.append(f"Major Penalty: {major_penalty}")

        minor_penalty = row.get("Minor Penalty")
        if minor_penalty and minor_penalty != "0":
            summary.append(f"Minor Penalty: {minor_penalty}")

        distance = row.get("Distance")
        if distance and (self._parse_number(distance) or 0.0) > 0.0:
            summary.append(f"Distance: {distance}")

        if not summary:
            summary.append("No data available yet")
        return summary

    def _select_best_dynamic_row(self, rows, event_name):
        positioned = [
            row for row in rows
            if self._parse_int(row.get("Position")) is not None
        ]
        if positioned:
            return min(positioned, key=lambda row: self._parse_int(row.get("Position")))

        event_type = self._infer_dynamic_event_type(event_name, rows=rows)
        return self._choose_best_result_row(rows, event_type)

    def _calculate_dynamic_scores(self, grouped_rows):
        scores = {}
        for event_name, team_rows in grouped_rows.items():
            event_type = self._infer_dynamic_event_type(event_name, rows=team_rows)
            benchmark_rows = self._fetch_event_result_rows(event_name)
            if not benchmark_rows:
                scores[event_name] = {
                    "score": None,
                    "note": "pending",
                    "possible_points": self.dynamic_event_points,
                }
                continue

            team_row = self._select_best_dynamic_row(team_rows, event_name)
            score = self._score_dynamic_event(event_name, event_type, team_row, benchmark_rows)
            scores[event_name] = {
                "score": score,
                "note": None if score is not None else "pending",
                "possible_points": self.dynamic_event_points,
            }
        return scores

    def _fetch_event_result_rows(self, event_name):
        cache_key = self._normalize_event_name(event_name)
        if cache_key in self._event_results_cache:
            return self._event_results_cache[cache_key]

        page = self.session.get(self.event_results_url, timeout=15)
        page.raise_for_status()
        parsed = BeautifulSoup(page.text, "html.parser")

        selected_event_id = self._match_event_option(parsed, event_name)
        if selected_event_id is None:
            self._event_results_cache[cache_key] = []
            return []

        payload = {
            "__EVENTTARGET": "ctl00$MainContent$ButtonLookupEvent",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": self._input_value(parsed, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": self._input_value(parsed, "__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": self._input_value(parsed, "__EVENTVALIDATION"),
            "ctl00$MainContent$DropDownListEvents": selected_event_id,
        }

        result_page = self.session.post(self.event_results_url, data=payload, timeout=15)
        result_page.raise_for_status()
        result_parsed = BeautifulSoup(result_page.text, "html.parser")

        table = self._find_event_results_table(result_parsed)
        if table is None:
            self._event_results_cache[cache_key] = []
            return []

        event_type = self._infer_dynamic_event_type(event_name)
        raw_rows = self._parse_table_records(table)
        normalized_rows = [self._normalize_event_result_row(row) for row in raw_rows]
        benchmark_rows = self._aggregate_event_result_rows(normalized_rows, event_type)
        self._event_results_cache[cache_key] = benchmark_rows
        return benchmark_rows

    def _fetch_dynamic_event_names(self):
        page = self.session.get(self.event_results_url, timeout=15)
        page.raise_for_status()
        parsed = BeautifulSoup(page.text, "html.parser")
        select = parsed.select_one("#MainContent_DropDownListEvents")
        if select is None:
            return []

        dynamic_events = []
        for option in select.select("option"):
            label = self._clean_text(option.get_text(" ", strip=True))
            if not label:
                continue
            if self._normalize_event_name(label) in self.static_event_names:
                continue
            dynamic_events.append(label)
        return dynamic_events

    def _input_value(self, parsed, element_id):
        element = parsed.select_one(f"#{element_id}")
        if element is None:
            return ""
        return element.get("value", "")

    def _match_event_option(self, parsed, event_name):
        select = parsed.select_one("#MainContent_DropDownListEvents")
        if select is None:
            return None

        target_name = self._normalize_event_name(event_name)
        options = {}
        for option in select.select("option"):
            label = self._clean_text(option.get_text(" ", strip=True))
            value = option.get("value")
            if label and value:
                options[self._normalize_event_name(label)] = value

        if target_name in options:
            return options[target_name]

        keywords = self._event_match_keywords(event_name)
        for normalized_name, value in options.items():
            if all(keyword in normalized_name for keyword in keywords):
                return value

        for normalized_name, value in options.items():
            if any(keyword in normalized_name for keyword in keywords):
                return value

        return None

    def _event_match_keywords(self, event_name):
        normalized = self._normalize_event_name(event_name)
        if "accel" in normalized:
            return ["accel"]
        if "maneuver" in normalized:
            return ["maneuver"]
        if "hill" in normalized:
            return ["hill"]
        if "traction" in normalized:
            return ["traction"]
        if "pull" in normalized:
            return ["pull"]
        if "rock" in normalized:
            return ["rock"]
        if "crawl" in normalized:
            return ["crawl"]
        if "suspension" in normalized:
            return ["suspension"]
        return [normalized]

    def _find_event_results_table(self, parsed):
        for table in parsed.select("table"):
            headers = self._table_headers(table)
            if not headers:
                continue
            if "Car No." in headers and "Status" in headers:
                return table
        return None

    def _normalize_event_result_row(self, row):
        return {
            "car_no": row.get("Car No.", row.get("Car No")),
            "school_name": row.get("School Name", ""),
            "team_name": row.get("Team Name", ""),
            "status": row.get("Status", ""),
            "time": self._first_number(
                row.get("Adjusted Time"),
                row.get("Best Time"),
                row.get("Time"),
                row.get("Corrected Time"),
                row.get("Raw Time"),
            ),
            "distance": self._first_number(
                row.get("Best Distance"),
                row.get("Distance"),
            ),
        }

    def _aggregate_event_result_rows(self, rows, event_type):
        grouped = defaultdict(list)
        for row in rows:
            car_no = row.get("car_no")
            if car_no:
                grouped[car_no].append(row)

        aggregated = []
        for car_no, group_rows in grouped.items():
            best_row = self._choose_best_result_row(group_rows, event_type)
            best_row["car_no"] = car_no
            aggregated.append(best_row)
        return aggregated

    def _choose_best_result_row(self, rows, event_type):
        if not rows:
            return {}

        if event_type == "acceleration":
            timed_rows = [
                row for row in rows
                if self._row_time_value(row) is not None and self._row_time_value(row) > 0.0
            ]
            if timed_rows:
                return min(timed_rows, key=lambda row: self._row_time_value(row))
            return rows[0]

        if event_type == "maneuverability":
            timed_rows = [
                row for row in rows
                if self._row_time_value(row) is not None and self._row_time_value(row) > 0.0
            ]
            if timed_rows:
                return min(timed_rows, key=lambda row: self._row_time_value(row))
            return rows[0]

        distances = [
            self._row_distance_value(row)
            for row in rows
            if self._row_distance_value(row) is not None
        ]
        max_distance = max(distances) if distances else None
        full_distance_rows = [
            row for row in rows
            if max_distance is not None and self._is_close(self._row_distance_value(row), max_distance)
        ]
        timed_full_distance_rows = [
            row for row in full_distance_rows
            if self._row_time_value(row) is not None and self._row_time_value(row) > 0.0
        ]
        if timed_full_distance_rows:
            return min(timed_full_distance_rows, key=lambda row: self._row_time_value(row))

        if full_distance_rows:
            return full_distance_rows[0]

        if distances:
            farthest_rows = [
                row for row in rows
                if self._is_close(self._row_distance_value(row), max_distance)
            ]
            timed_farthest_rows = [
                row for row in farthest_rows
                if self._row_time_value(row) is not None and self._row_time_value(row) > 0.0
            ]
            if timed_farthest_rows:
                return min(timed_farthest_rows, key=lambda row: self._row_time_value(row))
            return farthest_rows[0]

        timed_rows = [
            row for row in rows
            if self._row_time_value(row) is not None and self._row_time_value(row) > 0.0
        ]
        if timed_rows:
            return min(timed_rows, key=lambda row: self._row_time_value(row))

        return rows[0]

    def _score_dynamic_event(self, event_name, event_type, team_row, benchmark_rows):
        team_time = self._row_time_value(team_row)
        team_distance = self._row_distance_value(team_row)

        if event_type == "acceleration":
            return self._score_acceleration(team_time, benchmark_rows)

        if event_type == "maneuverability":
            return self._score_maneuverability(team_time, benchmark_rows)

        if event_type == "traction":
            return self._score_traction(team_time, team_distance, benchmark_rows)

        if self._specialty_uses_traction(benchmark_rows, team_row):
            # BAJA_RULES_2026 Rev A, D.7.6 (p. 109) allows specialty events
            # to use a Traction-style scoring option.
            return self._score_traction(team_time, team_distance, benchmark_rows)
        # BAJA_RULES_2026 Rev A, D.7.6 (p. 109) allows specialty events
        # to use a Maneuverability-style scoring option.
        return self._score_maneuverability(team_time, benchmark_rows)

    def _score_acceleration(self, team_time, benchmark_rows):
        timed_rows = [
            row for row in benchmark_rows
            if row.get("time") is not None and row.get("time") > 0.0
        ]
        if team_time is None or not timed_rows:
            return None

        tmin = min(row["time"] for row in timed_rows)
        tmax = min(max(row["time"] for row in timed_rows), 1.5 * tmin)
        if self._is_close(tmax, tmin):
            return self.dynamic_event_points
        if team_time > tmax:
            return 0.0

        # BAJA_RULES_2026 Rev A, D.4.6 (pp. 104-105).
        score = self.dynamic_event_points * (tmax - team_time) / (tmax - tmin)
        return round(max(0.0, min(self.dynamic_event_points, score)), 2)

    def _score_maneuverability(self, team_time, benchmark_rows):
        timed_rows = [
            row for row in benchmark_rows
            if row.get("time") is not None and row.get("time") > 0.0
        ]
        if team_time is None or not timed_rows:
            return None

        tmin = min(row["time"] for row in timed_rows)
        tmax = min(max(row["time"] for row in timed_rows), 2.5 * tmin)
        if self._is_close(tmax, tmin):
            return self.dynamic_event_points
        if team_time > tmax:
            return 0.0

        # BAJA_RULES_2026 Rev A, D.6.6 (p. 108).
        score = self.dynamic_event_points * (tmax - team_time) / (tmax - tmin)
        return round(max(0.0, min(self.dynamic_event_points, score)), 2)

    def _score_traction(self, team_time, team_distance, benchmark_rows):
        rows_with_distance = [
            row for row in benchmark_rows if row.get("distance") is not None
        ]
        if not rows_with_distance or team_distance is None:
            return None

        dmin = min(row["distance"] for row in rows_with_distance)
        dmax = max(row["distance"] for row in rows_with_distance)
        if self._is_close(dmax, 0.0):
            return None

        successful_rows = [
            row for row in rows_with_distance if self._status_is_success(row.get("status"))
        ]
        if not successful_rows:
            if self._is_close(dmax, dmin):
                return self.dynamic_event_points

            # BAJA_RULES_2026 Rev A, D.5.6.1 (p. 106).
            score = self.dynamic_event_points * (team_distance - dmin) / (dmax - dmin)
            return round(max(0.0, min(self.dynamic_event_points, score)), 2)

        full_distance = max(row["distance"] for row in successful_rows)
        full_distance_rows = [
            row for row in successful_rows if self._is_close(row["distance"], full_distance)
        ]

        if len(successful_rows) == len(rows_with_distance) and all(
            self._is_close(row["distance"], full_distance) for row in rows_with_distance
        ):
            timed_rows = [
                row for row in full_distance_rows
                if row.get("time") is not None and row.get("time") > 0.0
            ]
            if team_time is None or not timed_rows:
                return None

            tmin = min(row["time"] for row in timed_rows)
            tmax = min(max(row["time"] for row in timed_rows), 2.5 * tmin)
            if self._is_close(tmax, tmin):
                return self.dynamic_event_points
            if team_time > tmax:
                return 0.0

            # BAJA_RULES_2026 Rev A, D.5.6.2 (p. 106).
            score = self.dynamic_event_points * (tmax - team_time) / (tmax - tmin)
            return round(max(0.0, min(self.dynamic_event_points, score)), 2)

        timed_full_distance_rows = [
            row for row in full_distance_rows
            if row.get("time") is not None and row.get("time") > 0.0
        ]
        if not timed_full_distance_rows:
            return None

        tmin = min(row["time"] for row in timed_full_distance_rows)
        group_one_scores = {
            row.get("car_no"): self.dynamic_event_points * (tmin / row["time"])
            for row in timed_full_distance_rows
            if row.get("time")
        }
        if not group_one_scores:
            return None

        if self._is_close(team_distance, full_distance):
            if team_time is None:
                return None

            # BAJA_RULES_2026 Rev A, D.5.6.3 Group 1 (p. 107).
            score = self.dynamic_event_points * (tmin / team_time)
            return round(max(0.0, min(self.dynamic_event_points, score)), 2)

        lowest_group_one_score = min(group_one_scores.values())
        # BAJA_RULES_2026 Rev A, D.5.6.3 Group 2 (p. 107).
        score = lowest_group_one_score * (team_distance / full_distance)
        return round(max(0.0, min(self.dynamic_event_points, score)), 2)

    def _infer_dynamic_event_type(self, event_name, rows=None):
        normalized = self._normalize_event_name(event_name)
        if "accel" in normalized:
            return "acceleration"
        if "maneuver" in normalized:
            return "maneuverability"
        if any(keyword in normalized for keyword in ("hill", "traction", "pull")):
            return "traction"
        if "endurance" in normalized:
            return "endurance"
        if any(keyword in normalized for keyword in ("rock", "crawl", "suspension", "mud", "bog")):
            if self._rows_have_distance(rows):
                return "specialty"
            return "maneuverability"
        return "maneuverability"

    def _event_possible_points(self, event_name, event_type):
        if event_type == "endurance":
            return self.endurance_event_points
        return self.dynamic_event_points

    def _event_abbreviation(self, event_name):
        normalized = self._normalize_event_name(event_name)
        if "accel" in normalized:
            return "Acc"
        if "hill" in normalized:
            return "Hill"
        if "traction" in normalized:
            return "Trac"
        if "maneuver" in normalized:
            return "Man"
        if "rock" in normalized:
            return "Rock"
        if "crawl" in normalized:
            return "Rock"
        if "suspension" in normalized:
            return "Susp"
        if "endurance" in normalized:
            return "End"
        return event_name[:4]

    def _display_name(self, row):
        team_name = self._clean_text(row.get("team_name", ""))
        school_name = self._clean_text(row.get("school_name", ""))
        label = team_name or school_name or f"Car {row.get('car_no', '?')}"
        return self._truncate_text(label, 30)

    def _truncate_text(self, text, max_length):
        if len(text) <= max_length:
            return text
        return text[: max_length - 3].rstrip() + "..."

    def _rank_score_entries(self, entries, score_key="score"):
        sorted_entries = sorted(
            entries,
            key=lambda entry: (-entry.get(score_key, 0.0), self._parse_int(entry.get("car_no")) or 9999),
        )

        last_score = None
        last_rank = 0
        for index, entry in enumerate(sorted_entries, start=1):
            current_score = entry.get(score_key, 0.0)
            if last_score is None or not self._is_close(current_score, last_score, tolerance=1e-4):
                last_rank = index
                last_score = current_score
            entry["rank"] = last_rank
        return sorted_entries

    def _specialty_uses_traction(self, benchmark_rows, team_row):
        if self._rows_have_distance(benchmark_rows):
            return True
        team_distance = self._team_row_distance(team_row)
        return team_distance is not None and team_distance > 0.0

    def _rows_have_distance(self, rows):
        if not rows:
            return False

        for row in rows:
            if isinstance(row, dict):
                if row.get("distance") is not None and row.get("distance") > 0.0:
                    return True
                parsed_distance = self._first_number(row.get("Distance"), row.get("Best Distance"))
                if parsed_distance is not None and parsed_distance > 0.0:
                    return True
        return False

    def _team_row_time(self, row):
        return self._first_number(
            row.get("Corrected Time"),
            row.get("Raw Time"),
            row.get("Time"),
        )

    def _team_row_distance(self, row):
        return self._first_number(row.get("Distance"))

    def _row_time_value(self, row):
        if "time" in row:
            return row.get("time")
        return self._team_row_time(row)

    def _row_distance_value(self, row):
        if "distance" in row:
            return row.get("distance")
        return self._team_row_distance(row)

    def _first_number(self, *values):
        for value in values:
            parsed = self._parse_number(value)
            if parsed is not None:
                return parsed
        return None

    def _parse_number(self, value):
        if value is None:
            return None

        text = self._clean_text(str(value))
        if not text:
            return None

        if ":" in text:
            return self._parse_time_string(text)

        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match is None:
            return None
        return float(match.group(0))

    def _parse_time_string(self, value):
        cleaned = self._clean_text(value)
        parts = cleaned.split(":")
        try:
            total = 0.0
            for part in parts:
                total = total * 60 + float(part)
            return total
        except ValueError:
            return None

    def _parse_int(self, value):
        number = self._parse_number(value)
        if number is None:
            return None
        return int(number)

    def _status_is_success(self, status):
        if not status:
            return False
        normalized = self._normalize_event_name(status)
        return normalized in {"ok", "complete", "completed", "success"}

    def _normalize_event_name(self, value):
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def _is_close(self, left, right, tolerance=1e-6):
        if left is None or right is None:
            return False
        return abs(left - right) <= tolerance
