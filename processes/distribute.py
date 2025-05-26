import logging
from pathlib import Path


def run(
    args,
    settings: dict
    # process, product, destination
    ):

    OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"])
    CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"])
    CONNECTION_FILE_NAME: str = settings["connection_file_name"]

    
    def announce_self():
        logging.info(
            f"Hi! This is the {__name__} module, ready to {args.process.upper()} {args.product.upper()} to {args.destination.upper()}"
        )

    announce_self()
