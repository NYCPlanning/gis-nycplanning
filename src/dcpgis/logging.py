import logging
from pathlib import Path

print("hello, i'm a logging module")

def set_logger(
    file: Path, mode: str = "a", format: str = "{asctime} - {levelname} - {message}"
):
    logger = logging.getLogger(__name__)
    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(file, mode=mode, encoding="utf-8")
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    formatter = logging.Formatter(
        fmt=format,
        style="{",
        datefmt="%Y-%m-%d %H:%M",
    )

    console_handler.setFormatter(formatter)
    return logger
