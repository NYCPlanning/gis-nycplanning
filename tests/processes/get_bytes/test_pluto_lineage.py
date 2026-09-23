"""Tests for pluto_lineage.py. Every stem below is a real filename from a published release."""

import pytest

from processes.get_bytes import pluto_lineage


@pytest.mark.parametrize(
    "path_in_zip, item",
    [
        # pluto - citywide, borough-split in every historical naming scheme, and the old
        # attribute tables shipped inside MapPLUTO zips
        ("pluto_26v2.csv", "pluto"),
        ("pluto_25v2_1.csv", "pluto"),
        ("dcp_pluto_18v11.csv", "pluto"),
        ("BK.csv", "pluto"),
        ("MN05D.txt", "pluto"),
        ("bx12v1.txt", "pluto"),
        ("Borofiles_CSV\\BK2017V1.csv", "pluto"),
        ("BK_18v1.csv", "pluto"),
        ("nyc_pluto_08b\\SI08B.txt", "pluto"),
        ("bk_pluto.dbf", "pluto"),
        ("bxpluto.dbf", "pluto"),
        # mappluto - shapefiles, borough shapefiles, and gdb feature classes
        ("MapPLUTO.shp", "mappluto"),
        ("MapPLUTO_UNCLIPPED.shp", "mappluto"),
        ("Manhattan\\MNMapPLUTO.shp", "mappluto"),
        ("MapPLUTO25v1.gdb\\MapPLUTO_25v1_clipped", "mappluto"),
        ("MapPLUTO.gdb\\MapPLUTO_25v2_1_unclipped", "mappluto"),
        ("MapPLUTO_19V1.gdb\\MapPLUTO_19V1_Shoreline_Clipped", "mappluto"),
        ("MapPLUTO.gdb\\MapPLUTO_20v2_ShorelineClipped", "mappluto"),
        ("MapPLUTO.gdb\\MapPLUTO_19v1_Water_Included", "mappluto"),
        ("MapPLUTO.gdb\\MapPLUTO_UNCLIPPED_gdb", "mappluto"),
        ("SI_Dcp_Mappinglot.shp", "mappluto_mappinglot"),
        # documents
        ("pluto_datadictionary.pdf", "pluto_datadictionary"),
        ("PLUTODD.pdf", "pluto_datadictionary"),
        ("PLUTODD07C.pdf", "pluto_datadictionary"),
        ("PLUTODD17v1.1.pdf", "pluto_datadictionary"),
        ("PLUTODD23v3_1.pdf", "pluto_datadictionary"),
        ("pluto_readme.pdf", "pluto_readme"),
        ("PlutoReadme18v2.1.pdf", "pluto_readme"),
        ("PlutoReademe23v3_1.pdf", "pluto_readme"),
        ("plutochangefile_readme.pdf", "plutochangefile_readme"),
        ("PLUTOChangeFileReadme23v3_1.pdf", "plutochangefile_readme"),
        ("meta_mappluto.pdf", "meta_mappluto"),
        ("MapPLUTO_UNCLIPPED_Metadata.pdf", "meta_mappluto"),
        # change file members
        ("pluto_changes_applied.csv", "pluto_changes_applied"),
        ("pluto_changes_not_applied.csv", "pluto_changes_not_applied"),
        ("pluto_corrections.csv", "pluto_corrections"),
        ("pluto_corrections_applied.csv", "pluto_corrections_applied"),
        ("pluto_corrections_not_applied.csv", "pluto_corrections_not_applied"),
    ],
)
def test_item_for_real_release_filenames(path_in_zip, item):
    assert pluto_lineage.item_for(path_in_zip) == item


@pytest.mark.parametrize(
    "path_in_zip",
    [
        "pluto_removed_records.csv",
        "MapPLUTO.gdb\\NOT_MAPPED_LOTS",
        "PLUTOChangeFile22v1.csv",
        "Plutolay16v1.pdf",
        "Dates of Data 12v2.pdf",
        "PLUTO05D.pdf",
        "version.txt",
    ],
)
def test_item_for_unlisted_files_are_not_classified(path_in_zip):
    # A closed list: anything unlisted is flagged rather than guessed at, so a new upstream
    # filename shows up in the report instead of silently joining the nearest family.
    assert pluto_lineage.item_for(path_in_zip) == pluto_lineage.NOT_CLASSIFIED


def test_item_for_does_not_let_a_family_prefix_swallow_its_neighbours():
    # "mappluto" contains "pluto", and the metadata PDF starts with "mappluto" - whole-stem
    # matching is what keeps these apart.
    assert pluto_lineage.item_for("bkmappluto.shp") == "mappluto"
    assert pluto_lineage.item_for("mappluto_metadata.pdf") == "meta_mappluto"
    assert pluto_lineage.item_for("PLUTO04C.pdf") == pluto_lineage.NOT_CLASSIFIED
