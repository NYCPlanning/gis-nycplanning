"""Scrape a NYC DCP dataset page into url-level observed data points.

The dataset pages are client-rendered SPAs - the <main> is empty on a plain fetch. The real
content comes from two JSON endpoints the page's own JS calls, which this module hits
directly. Both are derived from the page slug, so pointing this at a different DCP dataset
page of the same shape needs no code change.

The parsing itself (release/label structure, format-inference heuristics) is still specific
to how the PLUTO family of pages is built - see the plan's scope-boundaries note.
"""

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from processes.get_bytes.common import get_zip_namelist

CONTENT_API_TEMPLATE = (
    "https://apps.nyc.gov/content-api/v1/content/planning/resources/datasets/{page}"
)
ARCHIVE_JSON_TEMPLATE = (
    "https://www.nyc.gov/assets/planning/json/content/resources/"
    "dataset-archives/{page}.json"
)

PRODUCT = "pluto"
TM_SYMBOL = "™"

LABEL_FORMAT_PATTERNS = [
    (re.compile(r"file geodatabase|fgdb", re.IGNORECASE), "fgdb"),
    (re.compile(r"shapefile|\(shp\)", re.IGNORECASE), "shp"),
    (re.compile(r"\(csv\)|\.csv format", re.IGNORECASE), "csv"),
    (re.compile(r"\(txt\)|\.txt format", re.IGNORECASE), "txt"),
]

URL_FORMAT_TOKENS = [
    ("_fgdb", "fgdb"),
    ("_shp", "shp"),
    ("_csv", "csv"),
    ("_txt", "txt"),
]


def page_slug_from_url(url: str) -> str:
    """'https://www.nyc.gov/.../datasets/mappluto-pluto-change' -> 'mappluto-pluto-change'."""
    return Path(urlparse(url).path).name


def normalize_dataset_name(raw: str) -> str:
    """'MapPLUTO™ - Shapefile' -> 'mappluto'; 'PLUTO Change File' -> 'pluto_change_file'."""
    name = raw.replace(TM_SYMBOL, "")
    name = name.split(" - ")[0]
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def reference_doc_suffix(link_text: str) -> str:
    """'View Data Dictionary' -> 'datadictionary'; 'View Read Me' -> 'readme'.

    Unlike normalize_dataset_name, spaces are dropped entirely rather than turned into
    underscores, so this matches the source filenames' own convention
    (pluto_datadictionary.pdf, pluto_readme.pdf) instead of splitting each word.
    """
    text = re.sub(r"^view\s+", "", link_text, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def infer_type_from_label(label_text: str) -> str | None:
    for pattern, type_ in LABEL_FORMAT_PATTERNS:
        if pattern.search(label_text):
            return type_
    return None


def infer_type_from_url(url: str) -> str | None:
    lower_url = url.lower()
    for token, type_ in URL_FORMAT_TOKENS:
        if token in lower_url:
            return type_
    return None


def infer_type_from_zip_contents(url: str, session: requests.Session) -> str:
    names = get_zip_namelist(url, session)
    if names is None:
        return "unknown"
    lower_names = [n.lower() for n in names]
    if any(".gdb/" in n for n in lower_names):
        return "fgdb"
    if any(n.endswith(".shp") for n in lower_names):
        return "shp"
    if any(n.endswith(".csv") for n in lower_names):
        return "csv"
    if any(n.endswith(".txt") for n in lower_names):
        return "txt"
    return "unknown"


def infer_type(label_text: str, url: str, session: requests.Session) -> str:
    """Label text first, then the URL, then - only if both are silent - the zip's own
    contents. That last tier is the one network call in this module's otherwise pure
    inference chain, and is why depth 0 is "no deep inspection" rather than "no zip touched".
    """
    if url.lower().endswith(".pdf"):
        return "pdf"
    return (
        infer_type_from_label(label_text)
        or infer_type_from_url(url)
        or infer_type_from_zip_contents(url, session)
    )


def strip_cache_buster(url: str) -> str:
    return url.split("?", 1)[0]


def parse_archive(entries: list[dict], session: requests.Session) -> list[dict]:
    rows = []
    for entry in entries:
        raw_dataset = entry["dataset"]
        dataset_name = normalize_dataset_name(raw_dataset)
        for release in entry["releases"]:
            link = release["link"]
            rows.append(
                {
                    "dataset_name": dataset_name,
                    "type": infer_type(raw_dataset, link, session),
                    "version": release["text"].strip(),
                    "url": strip_cache_buster(link),
                }
            )
    return rows


def parse_recent_release(html_fragment: str, session: requests.Session) -> list[dict]:
    version_match = re.search(r"Latest Release:\s*([0-9]+v[0-9]+)", html_fragment)
    version = version_match.group(1) if version_match else ""

    soup = BeautifulSoup(html_fragment, "html.parser")
    recent = soup.find(id="recent-release")
    # isinstance rather than `is None`: find() can also return a bare NavigableString, which
    # has no find_all and would blow up below.
    if not isinstance(recent, Tag):
        return []

    rows = []
    for sub_section in recent.find_all("div", class_="sub-section"):
        h3 = sub_section.find("h3")
        if h3 is None:
            continue
        base_name = normalize_dataset_name(h3.get_text(strip=True))
        current_label = h3.get_text(strip=True)

        for tr in sub_section.find_all("tr"):
            th = tr.find("th")
            if th is not None:
                current_label = th.get_text(strip=True)
                continue
            for a in tr.find_all("a", href=True):
                href = a["href"].strip()
                if not href.lower().endswith((".zip", ".pdf")):
                    continue  # e.g. the MapPLUTO "View REST" ArcGIS service link
                if "download" in a.get("class", []):
                    dataset_name = base_name
                else:
                    # A reference doc (Data Dictionary / Read Me / MetaData), not the
                    # dataset file itself - give it its own name instead of reusing the
                    # dataset's, e.g. "pluto_datadictionary", "mappluto_metadata".
                    suffix = reference_doc_suffix(a.get_text(strip=True))
                    dataset_name = f"{base_name}_{suffix}" if suffix else base_name
                rows.append(
                    {
                        "dataset_name": dataset_name,
                        "type": infer_type(current_label, href, session),
                        "version": version,
                        "url": href,
                    }
                )
    return rows


def assign_identifiers(rows: list[dict]) -> None:
    """Add an `identifier` per row, equal to the URL's filename minus its extension,
    disambiguated with a deterministic 5-digit suffix when that base name is reused by more
    than one row.
    """
    groups: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        base_id = Path(urlparse(row["url"]).path).stem
        groups[base_id].append(row)

    for base_id, group in groups.items():
        if len(group) == 1:
            group[0]["identifier"] = base_id
            continue
        used_suffixes: set[str] = set()
        for row in group:
            digest = int(hashlib.md5(row["url"].encode()).hexdigest(), 16)
            suffix_num = digest % 100000
            while f"{suffix_num:05d}" in used_suffixes:
                suffix_num = (suffix_num + 1) % 100000
            suffix = f"{suffix_num:05d}"
            used_suffixes.add(suffix)
            row["identifier"] = f"{base_id}_{suffix}"


def fetch_page_rows(page: str, session: requests.Session) -> list[dict]:
    """Both sections of a dataset page, as raw rows with identifiers assigned."""
    content_resp = session.get(CONTENT_API_TEMPLATE.format(page=page), timeout=30)
    content_resp.raise_for_status()
    html_fragment = content_resp.json()["description"]

    archive_resp = session.get(ARCHIVE_JSON_TEMPLATE.format(page=page), timeout=30)
    archive_resp.raise_for_status()
    archive_entries = archive_resp.json()

    rows = parse_recent_release(html_fragment, session) + parse_archive(
        archive_entries, session
    )
    assign_identifiers(rows)
    return rows
