import logging
from pathlib import Path


def initialize_logging(
    log_path: Path,
    log_filename: str,
    log_level: str = "INFO",
    format: str = "%(asctime)s :: %(levelname)s :: %(message)s",
):
    """Initialize logging. Output to file and console.
    source: https://stackoverflow.com/a/46098711
    source: https://github.com/NYCPlanning/db-template-repo/blob/main/python/run_logging.py

    Args:
        log_path (Path): Directory containing log file
        log_filename (str): Log filename. Do not include containing path
        log_level (str): Logging level. Defaults to "INFO"
        format (str): Defines format of log entries. Defaults to "%(asctime)s :: %(levelname)s :: %(message)s"
    """

    log_file = Path(log_path) / log_filename

    logging.basicConfig(
        level=log_level,
        format=format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
