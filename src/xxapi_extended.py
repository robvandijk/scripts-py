import logging as log
import pprint
from substrateinterface import SubstrateInterface, Keypair  # pip3 install substrate-interface
from substrateinterface.exceptions import SubstrateRequestException
import src.helpers as helpers
from datetime import datetime
import sys
import src.xxapi as xxapi

class XXNetworkInterfaceExtended(xxapi.XXNetworkInterface):
    def __init__(self, url: str = "ws://localhost:9944", logfile: str = "", verbose: bool = False, staking_verbose: bool = False):
        super(XXNetworkInterfaceExtended, self).__init__(url=url, logfile=logfile, verbose=verbose)
        global g_staking_verbose
        g_staking_verbose = staking_verbose

    def info_waiting_list(self):
        self.get_data()

        self.setup_auxiliary_data()

        self.process_data()

        self.output_info()

    def get_data(self):
        # all_nominators is a dictionary with key: nominator and value: {submitted_in: Int, suppressed: Bool, targets: Array}
        # targets contains the keys of the validators nominated
        all_nominators = self.map_query("Staking", "Nominators", "")
        all_validator_keys = self.map_query("Staking", "Validators", "").keys()

        # Add each validator to list of all_nominators (they nominate themselves using self-stake)
        for validator in all_validator_keys:
            if validator not in all_nominators:
                all_nominators[validator] = {"targets": [validator]}

        self.all_nominators = dict(map(lambda kv: (kv[0], NominatorInfo(kv[0], kv[1])), all_nominators.items()))

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
        for nominator, nominatorInfo in self.all_nominators.items():
            for validator in nominatorInfo.targets:
                if validator not in self.all_validators:
                    self.all_validators[validator] = ValidatorInfo(validator)
                self.all_validators[validator].add_nominator(nominator)

        # Determine for each entry in the ledger the bonded amount of coins
        for key in self.ledger:
            nominator_key = self.ledger[key]["stash"]
            bonded = self.ledger[key]["active"] / 1_000_000_000
            if nominator_key not in self.all_nominators:
                continue # Not sure what these are (old non-active accounts?); skip them
            nominator = self.all_nominators[nominator_key]
            nominator.bonded = bonded

    def process_data(self):
        self.waiting_validator_infos = []
        for validator_key in self.waiting_validator_keys:
            validator = self.all_validators[validator_key]
            validator.estimate_effective_stake(self.all_nominators)
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
            n = validator.nominators
            log.info(f"{(index+1):3d} Validator: {key}, effective stake {eff_stake:8.0f}, self_stake {self_stake:8.0f}, {len(n):3d} nominators")
        log.info(" ")
#         p.s. to pretty print arrays and dicts:
#         str = pprint.pformat(self.all_nominators)
#         log.info(str)

class NominatorInfo():
    def __init__(self, key, data):
        self.key = key
        self.targets = data["targets"]

    def number_of_validators(self):
        return len(self.targets)

class ValidatorInfo():
    def __init__(self, key):
        self.key = key
        self.nominators = set({key})
        self.total_stake = 0
        self.effective_stake = 0
        self.self_stake = 0

    def add_nominator(self, key):
        self.nominators.add(key)

    def estimate_effective_stake(self, all_nominators):
        if g_staking_verbose:
            log.info(f"Validator: {self.key} - {len(self.nominators)} nominators")
        for nominator_key in self.nominators:
            nominator = all_nominators[nominator_key]
            bonded = nominator.bonded
            n = nominator.number_of_validators()
            if g_staking_verbose:
                log.info(f"    Nominator: {nominator_key} - bonded {bonded:8.0f} - {n:3d} validators")
            self.total_stake = self.total_stake + bonded
            effective_stake = bonded / n
            self.effective_stake = self.effective_stake + effective_stake
            if nominator_key == self.key:
                self.self_stake = bonded
