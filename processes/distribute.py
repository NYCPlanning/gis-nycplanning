import logging
from pathlib import Path
from typing import Union
import arcpy


def announce_module(module_name, process, product, destination):
    logging.info(
        f"Hi! This is the {module_name} module, ready to {process.upper()} \
            {product.upper()} to {destination.upper()}"
    )


def get_product_config_values() -> dict:
    """
    Product and constituent file info:
        - name of geodatabase(s) to access at source
        - names at source
        - names at destination
        - which to distribute, which to hold back
    Where, "source" is location to distribute from, like Digital Ocean
    """


product_distribution_attr: dict = {}


def get_data_from_source_location(placeholder):
    """
    Download and unzip from DO or other, ready to be distributed
    """


class EnterpriseGeodatabase:
    def __init__(self):
        ...

    def disconnect_users(self) -> None: ...
    def block_connections(self) -> None: ...
    def allow_connections(self) -> None: ...
    def list_connections(self) -> Union[list, dict]: ...
    def is_valid(self) -> bool: ...


def overwrite_feature_class(dataset):
    logging.info(dataset)

def run(
    args,
    settings: dict,
):
    announce_module(
        module_name=__name__,
        process=args.process,
        product=args.product,
        destination=args.destination,
    )

    OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"])
    CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"])
    CONNECTION_FILE_NAME: str = settings["connection_file_name"]

    product_distribution_attr = get_product_config_values()

    get_data_from_source_location(product_distribution_attr)

    if args.destination.lower() == "egdb":
        EGDB = EnterpriseGeodatabase()
        EGDB.list_connections()
        EGDB.disconnect_users()
        EGDB.block_connections()

        try:
            for dataset in product_distribution_attr:
                overwrite_feature_class(dataset)
                
                EGDB.is_valid()
        except arcpy.ExecuteError:
            logging.exception(arcpy.GetMessages())
            logging.exception()
        except Exception as e:
            logging.exception(e)
        finally:
            EGDB.allow_connections()

    else:
        logging.warning(f"{args.product} can not yet be handled by this code.")
