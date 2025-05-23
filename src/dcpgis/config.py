import logging
from pathlib import Path
from typing import Dict

import yaml


class Config:
    def __init__(self, app_env, config_file_path):
        self.app_env = app_env
        self.config_file_path = config_file_path

    def get_config_from_yaml(self) -> Dict:
        try:
            with open(
                # TODO: make path name less specific so that name can be injected on instantiation
                #      while keeping env swap functionality as clean and clear as possible.
                Path(self.config_file_path) / f"{self.app_env}_settings.yml",
                mode="r",
                encoding="utf-8",
            ) as config:
                configs: Dict = yaml.safe_load(config)
        except yaml.YAMLError as yaml_err:
            logging.exception(
                f"Error occurred while reading the file. Error: {yaml_err}"
            )
            raise
        logging.info("Configuration settings initialized")
        return configs
