import csv
import io
import logging

logger = logging.getLogger(__name__)

TABULAR_ENCODINGS = ("utf-8", "cp1252", "latin-1")


def get_table_profile(data: bytes, label: str = "table") -> dict:
    """Decode `data` and count its rows and columns with stdlib csv's default comma dialect.

    Args:
        data: the file's raw bytes.
        label: names the file in log messages.

    Returns:
        `{"encoding", "row_count", "col_count"}`.

        `encoding` is the first of TABULAR_ENCODINGS that decoded it.
        `row_count` excludes the header. Both counts are None when the file is empty.
        When parsing fails partway, `row_count` is None but `col_count` keeps the
        header's count if the header itself parsed.

    Encoding order: older files often predate UTF-8, a few use bytes cp1252 leaves
    undefined, and latin-1 decodes every byte, so it's the guaranteed fallback.

    There's no delimiter sniffing. Other delimiters still get a row count, but `col_count`
    is then one more than the header's comma count - usually 1 for a tab- or pipe-delimited file.
    """
    text = ""
    encoding = None
    for candidate in TABULAR_ENCODINGS:
        try:
            text = data.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue

    row_count = None
    col_count = None
    if not text.strip():
        logger.warning(f"{label} is empty")
    else:
        try:
            reader = csv.reader(io.StringIO(text))
            header = next(reader, None)
            col_count = len(header) if header else None
            row_count = sum(1 for _ in reader)
        except csv.Error as exc:
            logger.warning(f"could not parse {label}: {exc}")

    return {"encoding": encoding, "row_count": row_count, "col_count": col_count}
