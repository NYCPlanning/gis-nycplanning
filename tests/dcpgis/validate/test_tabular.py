"""Tests for dcpgis.validate.tabular - pure functions over bytes, no I/O."""

import csv

from dcpgis.validate import tabular


def test_get_table_profile_counts_rows_and_columns():
    assert tabular.get_table_profile(b"a,b,c\n1,2,3\n4,5,6\n") == {
        "encoding": "utf-8",
        "row_count": 2,  # header excluded
        "col_count": 3,
    }


def test_get_table_profile_splits_columns_on_commas_only():
    assert tabular.get_table_profile(b"a\tb\tc\n1\t2\t3\n4\t5\t6\n") == {
        "encoding": "utf-8",
        "row_count": 2,
        "col_count": 1,
    }


def test_get_table_profile_records_fallback_encoding():
    # 0x92 is a cp1252 smart quote and invalid UTF-8 - real older PLUTO files contain these.
    profile = tabular.get_table_profile(b"owner\nO\x92Brien\n")
    assert profile["encoding"] == "cp1252"
    assert profile["row_count"] == 1


def test_get_table_profile_empty_content_has_no_counts(caplog):
    profile = tabular.get_table_profile(b"   ", label="empty.txt")
    assert profile["row_count"] is None
    assert profile["col_count"] is None
    assert "empty.txt is empty" in caplog.text


def test_get_table_profile_stray_carriage_return_is_unparseable(caplog):
    # Counting it as a row break instead would report 3 rows here without any warning.
    profile = tabular.get_table_profile(b"a,b\n1,x\ry\n3,4\n", label="cr.csv")
    assert profile["col_count"] == 2
    assert profile["row_count"] is None
    assert "could not parse cr.csv" in caplog.text


def test_get_table_profile_unparseable_keeps_encoding_and_header(caplog):
    # An unbalanced quote swallows the rest of the file into one field, which csv.reader
    # rejects once it passes the field size limit. The header before it still counts.
    data = b'a,b\n1,"' + b"x" * (csv.field_size_limit() + 1) + b"\n"
    profile = tabular.get_table_profile(data, label="bad.csv")
    assert profile["encoding"] == "utf-8"
    assert profile["col_count"] == 2
    assert profile["row_count"] is None
    assert "could not parse bad.csv" in caplog.text
