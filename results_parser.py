import requests
from bs4 import BeautifulSoup

class ResultsParser:
    base_url = f"https://results.bajasae.net/MyResults.aspx"

    def __init__(self, car_num=4):
        self.car_num = car_num
        self.car_request_url = self.base_url + f"?carnum={car_num}"

    def get_results(self):
        BeautifulSoup("test")
        return None