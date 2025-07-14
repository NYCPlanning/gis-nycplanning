import argparse
from dataclasses import dataclass
from typing import Any, Optional


ENV_CHOICES = ["dev", "prod"]
PRODUCT_CHOICES = ["pluto", "mih", "template"]
DESTINATION_CHOICES = ["gisprod", "digital_ocean", "ago", "network_drive"]
ORIGIN_CHOICES = ["gistrd", "gisgru", "digital_ocean"]
DATASET_CHOICES = ["all", "partial"]


@dataclass
class CLIArgument:
    name_or_flag: str
    required: bool
    help_msg: str
    action: Optional[str] = "store"
    choices: Optional[list[str]] = None
    default: Optional[Any] = None


GLOBAL_ARGS: list = [
    CLIArgument(
        name_or_flag="--env",
        action="store",
        choices=ENV_CHOICES,
        required=True,
        help_msg="Used to specify either prod or dev configuration parameters.",
        default="dev",
    ),
]

DISTRIBUTE_ARGS: list = [
    CLIArgument(
        name_or_flag="--product",
        action="store",
        choices=PRODUCT_CHOICES,
        required=True,
        help_msg="The product to be moved/distributed. Products are datasets, or agreed upon groups of datasets.",
    ),
    CLIArgument(
        name_or_flag="--origin",
        action="store",
        choices=ORIGIN_CHOICES,
        required=True,
        help_msg="The origin from which data is being moved.",
    ),
    CLIArgument(
        name_or_flag="--destination",
        action="store",
        choices=DESTINATION_CHOICES,
        required=True,
        help_msg="The destination to which data is being moved.",
    ),
    CLIArgument(
        name_or_flag="--datasets",
        action="store",
        choices=DATASET_CHOICES,
        required=False,
        help_msg="Which of the constituent datasets composing a product are to be distributed.",
        default="all",
    ),
]

TRANSFORM_ARGS: list = []  # placeholder


class CLI:
    """
    A CLI object with default global argument(s)
    Global args can be overriden upon instantiation, using "default_args"
    """

    def __init__(
        self,
        default_args: list[CLIArgument] = GLOBAL_ARGS,
    ) -> None:
        self.default_args = default_args
        self.parser = argparse.ArgumentParser()
        self._add_global_args()

    def _add_global_args(self) -> None:
        for arg in self.default_args:
            self._add_argument(arg)

    def _add_argument(self, arg: CLIArgument):
        """Add a single argument to the parser."""
        kwargs: dict[str, Any] = {
            "help": arg.help_msg,
            # 'type': arg.type,     # Placeholder
            "default": arg.default,
            "required": arg.required,
        }

        # Only add non-None values
        if arg.action:
            kwargs["action"] = arg.action
        if arg.choices:
            kwargs["choices"] = arg.choices

        # Remove type for store_true/store_false actions
        # Implement if "type" is added as an attribute to CLIArgument in the future
        # if arg.action in ("store_true", "store_false"):
        #     kwargs.pop("type", None)
        #     kwargs.pop("default", None)

        self.parser.add_argument(arg.name_or_flag, **kwargs)

    def add_arguments(self, arguments: list[CLIArgument]) -> None:
        for arg in arguments:
            self._add_argument(arg)

    def parse_args(self) -> argparse.Namespace:
        return self.parser.parse_args()


# keeping for limited testing purposes
def main():
    cli = CLI()
    cli.add_arguments(DISTRIBUTE_ARGS)
    args = cli.parse_args()

    ENVIRONMENT = args.env

    print(f"ENVIRONMENT:     {ENVIRONMENT}")


if __name__ == "__main__":
    main()
