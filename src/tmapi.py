import logging as log
import os
import requests
import datetime
import re

class TeamMultiplierApi:
    def __init__(self, base_url: str = "https://team-multiplier.xx.network/multiplier-logs/"):
        self.base_url = base_url

    def current_tm_values(self):
        data_array = self.read_latest_log()

        index_start = self.find_start_index(data_array)
        if not index_start:
            log.info("\n\n    WARNING: Could not locate start index in Team Multiplier log\n\n")
            return {}

        tm_values = {}
        key, tm_value, next_index = self.find_next(data_array, index_start)
        while next_index:
            tm_values[key] = tm_value
            key, tm_value, next_index = self.find_next(data_array, next_index)
        return tm_values

    def read_latest_log(self):
        url = self.latest_url()
        if url == None:
            log.info("\n\n    WARNING: could not read log containing Team Multipliers\n\n")
            return []
        data = requests.get(url).text
        return data.split("\n")

    def latest_url(self):
        date = datetime.datetime.now()
        url = self.base_url + date.strftime("%Y-%m-%d") + ".log"
        response = requests.head(url)
        if response.status_code == 200:
            return url

        date = date + datetime.timedelta(days=-1)
        url = self.base_url + date.strftime("%Y-%m-%d") + ".log"
        response = requests.head(url)
        if response.status_code == 200:
            log.info("\n\n    NOTE: could not access today's log containing Team Multipliers, will try to access yesterday's log\n\n")
            return url
        else:
            return None

    def find_start_index(self, tm_array):
        for index, line in enumerate(tm_array):
            match = re.search(r"Adjusting multiplier values", line)
            if match:
                return index + 1
        return None

    def find_next(self, tm_array, next_index):
        rng = range(next_index, len(tm_array) - 1)
        for index in rng:
            line = tm_array[index]
            match = re.search(r"---- Processing node\s+(.*)\s+----", line)
            if match:
                validator_key = match.group(1)
                next_line = tm_array[index + 1]
                match_tm = re.search(r"Node receives\s+(.*?)(?:,|$)", next_line)
                if match_tm:
                    tm_value = float(match_tm.group(1))
                else:
                    raise(f"line containing Node receives not found for {validator_key}")
                return [validator_key, tm_value, index + 2]
        return [None, None, None]

