from pathlib import Path
from dcpgis.cli import CLI, DISTRIBUTE_ARGS

SETTINGS_FILE_PARENT = Path(__file__).parent.parent.parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent.parent.parent.parent / "log"


def main():
    cli = CLI()
    cli.add_arguments(DISTRIBUTE_ARGS)
    args = cli.parse_args()

    ENVIRONMENT = args.env

    print(f"ENVIRONMENT:     {ENVIRONMENT}")


if __name__ == "__main__":
    main()
