# To hold environment config switching code currently defined
# in untracked dev files.
import yaml
from typing import Dict
from pathlib import Path


def msg():
    return "this is from the config file"


class Config:
    def __init__(self, app_env, config_file_path):
        self.app_env = app_env
        self.config_file_path = config_file_path

    def get_settings(self) -> Dict:
        try:
            with open(
                Path(self.config_file_path) / f"{self.app_env}_settings.yml",
                mode="r",
                encoding="utf-8",
            ) as config:
                configs: Dict = yaml.safe_load(config)
        except yaml.YAMLError as yaml_err:
            print(f"Error occurred while reading the file. Error: {yaml_err}")
            raise
        return configs
