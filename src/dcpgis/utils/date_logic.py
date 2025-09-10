import arcpy
import logging
from datetime import datetime, date, timedelta


def get_latest_date_from_field(feature_class_path: str, date_field: str, override_config_value: str = None) -> str:
    """
    Retrieve the latest date from a specified date field in an ArcGIS feature class.

    Args:
        feature_class_path (str): The path to the feature class to search.
        date_field (str): The name of the date field to query for the latest date.
        override_config_value (str, optional): If provided, this value will be returned instead of querying the feature class.

    Returns:
        str: The latest date in YYYYMMDD format, or None if no date is found.
    """
    if override_config_value is None:
        latest_date = None
        with arcpy.da.SearchCursor(
            in_table=feature_class_path,
            field_names=[date_field],
        ) as cursor:
            for row in cursor:
                if row[0] is not None:
                    if latest_date is None or row[0] > latest_date:
                        latest_date = row[0]
        return latest_date.strftime("%Y%m%d") if latest_date else None
    else: 
        latest_date = override_config_value
        logging.debug(f"Using override date from config file: {latest_date}")
        return latest_date.strftime("%Y%m%d") if latest_date else None

def calc_open_data_cycle_month(config_date: str) -> str:
    """
    Calculate a YYYYMM date string representing the open data cycle month
    Can override this calculation by entering a YYYYMM date string into the config file
    Source: https://stackoverflow.com/a/9725093
    """
    if config_date is None:
        logging.debug("Date field from config file is blank - calculating YYYYMM from today's date")
        today = date.today()
        first_of_this_month = today.replace(day=1)
        last_month = first_of_this_month - timedelta(days=1)
        last_month = last_month.strftime("%Y%m")
        return last_month
    else:
        logging.debug("Pulling YYYYMM date from date field in config file")
        return str(config_date)