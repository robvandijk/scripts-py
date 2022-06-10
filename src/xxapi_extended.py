import logging as log
import pprint
from substrateinterface import SubstrateInterface, Keypair  # pip3 install substrate-interface
from substrateinterface.exceptions import SubstrateRequestException
import src.helpers as helpers
import src.tmapi as tmapi
from datetime import datetime
import sys
import src.xxapi as xxapi
import json_fix
import json
import os

g_all_nominators = {}

class XXNetworkInterfaceExtended(xxapi.XXNetworkInterface):
    def __init__(self, url: str = "ws://localhost:9944", logfile: str = "", verbose: bool = False,
            staking_verbose: bool = False, write_waiting_list: bool = False):
        super(XXNetworkInterfaceExtended, self).__init__(url=url, logfile=logfile, verbose=verbose)
        global g_staking_verbose
        g_staking_verbose = staking_verbose
        self.write_waiting_list = (write_waiting_list == "true")

    def info_waiting_list(self):
        self.get_data()

        self.setup_auxiliary_data()

        self.process_data()

        self.output_info()

    def get_data(self):
        # Get Team Multipliers
        self.tm_values = tmapi.TeamMultiplierApi().current_tm_values()
        if len(self.tm_values) == 0:
            log.info(f"\n\n    TM values could not be retrieved - will continue without taking into account TM values\n\n")

        # all_nominators is a dictionary with key: nominator and value: {submitted_in: Int, suppressed: Bool, targets: Array}
        # targets contains the keys of the validators nominated
        all_nominators = self.map_query("Staking", "Nominators", "")
        all_validator_keys = self.map_query("Staking", "Validators", "").keys()

        # Add each validator to list of all_nominators (they nominate themselves using self-stake)
        for validator in all_validator_keys:
            if validator not in all_nominators:
                all_nominators[validator] = {"targets": [validator]}

        global g_all_nominators
        g_all_nominators = dict(map(lambda kv: (kv[0], NominatorInfo(kv[0], kv[1])), all_nominators.items()))

        # Determine keys of validators in Waiting list
        active_validator_keys = self.item_query("Session", "Validators") # Currently 360 active validators
        self.waiting_validator_keys = all_validator_keys - active_validator_keys

        # Get ledger. This returns a dictionary:
        #   key -> {'active': 219622070803574, 'claimed_rewards': [0], 'cmix_id': None, 'stash': '6..................', 'total': 380000000000000,
        #           'unlocking': [{'era': 32, 'value': 160377929196426}]},
        # "stash" contains the nominator/validator key, "active" contains the amount bonded
        self.ledger = self.map_query("Staking", "Ledger", "")

    def setup_auxiliary_data(self):
        # Create a map from validators -> nominators
        self.all_validators = {}
        for nominator, nominator_info in g_all_nominators.items():
            for validator in nominator_info.targets:
                if validator not in self.all_validators:
                    self.all_validators[validator] = ValidatorInfo(validator)
                self.all_validators[validator].add_nominator(nominator, nominator_info)

        # Determine for each entry in the ledger the bonded amount of coins
        for key in self.ledger:
            nominator_key = self.ledger[key]["stash"]
            bonded = self.ledger[key]["active"] / 1_000_000_000
            if nominator_key not in g_all_nominators:
                continue # Not sure what these are (old non-active accounts?); skip them
            nominator = g_all_nominators[nominator_key]
            nominator.bonded = bonded

        # Set TM values
        for validator_key, tm_value in self.tm_values.items():
            validator = self.all_validators[validator_key]
            validator.tm_value = tm_value

    def process_data(self):
        self.waiting_validator_infos = []
        for validator_key in self.waiting_validator_keys:
            validator = self.all_validators[validator_key]
            validator.estimate_effective_stake()
            self.waiting_validator_infos.append(validator)

    def output_info(self):
        intro = """

            Below the validators from the Waiting list are shown ordered by 'effective stake'.
            The effective stake is calculated by summing the bonded amounts of the nominators divided
            by the number of validators they nominate (including the self-stake).
            The validators on top of the list are most likely to enter the Active list the next era
            (if you run this just before the election cutoff).
        """
        log.info(intro)
        self.waiting_validator_infos.sort(key=lambda x:x.effective_stake, reverse=True)
        for index, validator in enumerate(self.waiting_validator_infos):
            key = validator.key
            eff_stake = validator.effective_stake
            self_stake = validator.self_stake
            n = validator.number_of_nominators()
            add_tm_info = f", TM {validator.tm_value:8.0f}" if validator.tm_value else ""
            log.info(f"{(index+1):3d} Validator: {key}, effective stake {eff_stake:8.0f}, self_stake {self_stake:8.0f}, {n:3d} nominators{add_tm_info}")
        log.info(" ")
#         p.s. to pretty print arrays and dicts:
#         str = pprint.pformat(g_all_nominators)
#         log.info(str)

        if self.write_waiting_list:
            self.write_waiting_list_to_file()

    def write_waiting_list_to_file(self):
            curr_era = self.item_query("Staking", "ActiveEra")
            curr_era = curr_era['index']
            basename = f"{curr_era}.json"
            path = os.path.join(os.getcwd(), "info_waiting_lists")
            os.makedirs(path, exist_ok = True)
            filename = os.path.join(path, basename)
            with open(os.path.join(path, filename), "w") as write_file:
                json.dump(self.waiting_validator_infos, write_file, indent=4)

class NominatorInfo():
    def __init__(self, key, data):
        self.key = key
        self.targets = data["targets"]

    def number_of_validators(self):
        return len(self.targets)

    def __json__(self):
        my_dict = self.__dict__
        return my_dict

class ValidatorInfo():
    def __init__(self, key):
        self.key = key
        self.total_stake = 0
        self.effective_stake = 0
        self.self_stake = 0
        self.tm_value = None
        if key in g_all_nominators:
            nominator_info = g_all_nominators[key]
        else:
            nominator_info = NominatorInfo(key, {"targets": [key]})
        self.nominators = {key: nominator_info}

    def number_of_nominators(self):
        return len(self.nominators)

    def add_nominator(self, key, nominator_info):
        if key in self.nominators:
            return
        self.nominators[key] = nominator_info

    def estimate_effective_stake(self):
        if g_staking_verbose:
            log.info(f"Validator: {self.key} - {len(self.nominators)} nominators, TM: {self.tm_value}")

        if self.tm_value:
            self.effective_stake = self.tm_value

        for nominator_key, nominator_info in self.nominators.items():
            bonded = nominator_info.bonded
            n = nominator_info.number_of_validators()
            if g_staking_verbose:
                log.info(f"    Nominator: {nominator_key} - bonded {bonded:8.0f} - {n:3d} validators")
            self.total_stake = self.total_stake + bonded
            effective_stake = bonded / n
            self.effective_stake = self.effective_stake + effective_stake
            if nominator_key == self.key:
                self.self_stake = bonded

    def __json__(self):
        my_dict = self.__dict__
        return my_dict
