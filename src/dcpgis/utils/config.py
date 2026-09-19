import logging
from pathlib import Path
from typing import Union

import yaml


class Config:
    # TODO: move all open() calls to Path.open(), per ruff ruleset
    def __init__(self, app_env: str, config_file_path: Union[Path, str]):
        self.app_env = app_env
        self.config_file_path = config_file_path

    def get_config_from_yaml(self) -> dict:
        try:
            with open(
                # TODO: make path name less specific so that name can be injected on instantiation
                #      while keeping env swap functionality as clean and clear as possible.
                Path(self.config_file_path) / f"{self.app_env}_config.yml",
                mode="r",
                encoding="utf-8",
            ) as config:
                configs: dict = yaml.safe_load(config)
        except yaml.YAMLError as yaml_err:
            logging.exception(
                f"Error occurred while reading the file. Error: {yaml_err}"
            )
            raise
        logging.info("Configuration settings initialized")
        return configs

    def get_config_from_xlsx(self) -> dict:
        return {}
