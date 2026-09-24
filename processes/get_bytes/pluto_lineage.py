"""PLUTO-specific naming: which `item` each file inside a release zip is.

Kept apart from the rest of the tool, which is otherwise product-agnostic, so supporting another
product means adding a vocabulary rather than editing the pipeline.
"""

import posixpath
import re

NOT_CLASSIFIED = "not_classified"

# Items whose rows carry the clipped/unclipped sub_dataset. The inference also stamps the label
# on everything else in the same zip, where it means nothing.
CLIPPED_ITEMS = {"mappluto"}

_BORO = r"(bk|bx|mn|qn|si)"

# Each pattern must match the whole stem, so no rule can shadow another and order is irrelevant.
ITEM_RULES = [
    (
        rf"pluto_\d{{2}}v\d+(_\d+)?|dcp_pluto_\d{{2}}v\d+"
        rf"|{_BORO}(_?pluto|_?\d{{2}}v\d+|\d{{4}}v\d+|\d{{2}}[a-d])?",
        "pluto",
    ),
    (
        rf"{_BORO}?mappluto(_unclipped)?(_gdb)?"
        r"|mappluto_\d{2}v\d+(_\d+)?_((un)?clipped|shoreline_?clipped|water_included)",
        "mappluto",
    ),
    (rf"{_BORO}_dcp_mappinglot", "mappluto_mappinglot"),
    (
        r"pluto_datadictionary|plutodd(\d{2}(v\d+([._]\d+)?|[a-d]))?",
        "pluto_datadictionary",
    ),
    # "reademe" is a typo in the 23v3_1 archives, not a separate document.
    (r"pluto_readme|plutoreade?me\d{2}v\d+([._]\d+)?", "pluto_readme"),
    (
        r"plutochangefile_readme|plutochangefilereadme\d{2}v\d+(_\d+)?",
        "plutochangefile_readme",
    ),
    (r"meta_mappluto|mappluto(_unclipped)?_metadata", "meta_mappluto"),
    (r"pluto_changes_applied", "pluto_changes_applied"),
    (r"pluto_changes_not_applied", "pluto_changes_not_applied"),
    (r"pluto_corrections", "pluto_corrections"),
    (r"pluto_corrections_applied", "pluto_corrections_applied"),
    (r"pluto_corrections_not_applied", "pluto_corrections_not_applied"),
]

_COMPILED_RULES = [
    (re.compile(pattern, re.IGNORECASE), item) for pattern, item in ITEM_RULES
]

# Only real file extensions are stripped: .gdb layer names have none, and splitext would cut one
# at any dot in the name.
_FILE_EXTENSION = re.compile(r"\.(shp|dbf|csv|txt|pdf)$", re.IGNORECASE)

# Pre-2009 releases are lettered (05D); later ones are numbered (26v2, 25v2.1 / 25v2_1).
VERSION_PATTERN = re.compile(r"\d{2}v\d+(?:[._]\d+)?|\d{2}[a-d](?![a-z])", re.IGNORECASE)


def version_token(text: str | None) -> str | None:
    """The release version in a page label or filename, or None if there isn't one.

    Normalized so the page's "25v2.1" matches the filename's "25v2_1", and a label suffix like
    "18v2Beta" reduces to "18v2".
    """
    match = VERSION_PATTERN.search(text or "")
    return match.group(0).replace(".", "_").lower() if match else None


def item_for(path_in_zip: str) -> str:
    """The reference-list item a zip member belongs to, or NOT_CLASSIFIED.

    Takes `path_in_zip` as stored in dataset_level (backslash-separated); for a .gdb layer
    the last segment is the layer name.
    """
    basename = posixpath.basename(path_in_zip.replace("\\", "/"))
    stem = _FILE_EXTENSION.sub("", basename)
    for pattern, item in _COMPILED_RULES:
        if pattern.fullmatch(stem):
            return item
    return NOT_CLASSIFIED
