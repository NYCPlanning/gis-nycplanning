"""Fixtures for the get_bytes test suite.

The HTTP fakes, the network guard and the shapefile fixtures are shared with the dcpgis tests,
so they live in the top-level tests/conftest.py.
"""

import zipfile

import pytest


@pytest.fixture()
def mocked_responses_path(resources_path):
    return resources_path / "mocked_responses"


@pytest.fixture()
def nested_zip_path(tmp_path, resources_path):
    """A zip-of-zips built at test time by wrapping the real shapefile fixture in an outer
    zip - mirrors the real mappluto_16v2/17v1 shape without checking in another binary blob
    for something fully derivable from an existing fixture.
    """
    inner_name = "shapefile_nyzd_one_row.zip"
    inner_bytes = (resources_path / inner_name).read_bytes()
    outer_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(outer_path, "w") as zf:
        zf.writestr(inner_name, inner_bytes)
    return outer_path
