import logging
from datetime import date, datetime, timedelta

import arcpy


def get_latest_date_from_field(feature_class_path: str, date_field: str, override_config_value: str | None) -> str:
    """
    Retrieve the latest date from a specified date field in an ArcGIS feature class.

    Args:
        feature_class_path (str): The path to the feature class to search.
        date_field (str): The name of the date field to query for the latest date.
        override_config_value (str, optional): If provided, this value will be returned instead of querying the feature class.

    Returns:
        str: The latest date in YYYYMMDD format.

    Raises:
        ValueError: If no override is provided and the date field contains no dates.
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
        if latest_date is None:
            raise ValueError(f"No dates found in field '{date_field}' of {feature_class_path}")
        return str(latest_date.strftime("%Y%m%d"))
    else:
        latest_date = override_config_value
        logging.debug(f"Using override date from config file: {latest_date}")
        return str(latest_date)


def calc_open_data_cycle_month(config_date: str | None) -> str:
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
        return str(last_month.strftime("%Y%m"))
    else:
        logging.debug("Pulling YYYYMM date from date field in config file")
        return str(config_date)


def reformat_date_str_to_written_month(date_string: str) -> str:
    """
    Reformats a date string in YYYYMMDD format to a written month format (e.g., 'January 1, 2020').

    Args:
        date_string (str): The date string in YYYYMMDD format.
    Returns:
        str: The reformatted date string in 'Month Day, Year' format.
    """
    date_obj = datetime.strptime(date_string, "%Y%m%d")
    written_month = date_obj.strftime("%B %d, %Y")
    return written_month
