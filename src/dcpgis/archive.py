import posixpath
import zipfile


def discover_gdb_folders(names: list[str]) -> list[str]:
    folders = set()
    for name in names:
        idx = name.lower().find(".gdb/")
        if idx != -1:
            folders.add(name[: idx + 4])
    return sorted(folders)


def discover_loose_dirs(names: list[str]) -> list[str]:
    """Parent directories ('' for top level) holding at least one .shp or standalone .dbf.

    Gated on those actually being present, so a caller opening each result as a shapefile
    source never gets a directory with nothing in it to open (e.g. only PDFs).
    """
    dirs = set()
    for name in names:
        lower = name.lower()
        if ".gdb/" in lower or lower.endswith(".zip"):
            continue
        if lower.endswith((".shp", ".dbf")):
            dirs.add(posixpath.dirname(name))
    return sorted(dirs)


def discover_nested_zips(names: list[str]) -> list[str]:
    return sorted(n for n in names if n.lower().endswith(".zip"))


def _discover_by_suffix(names: list[str], suffixes: tuple[str, ...]) -> list[str]:
    found = []
    for name in names:
        lower = name.lower()
        if ".gdb/" in lower or lower.endswith(".zip"):
            continue
        if lower.endswith(suffixes):
            found.append(name)
    return sorted(found)


def discover_tabular_files(names: list[str]) -> list[str]:
    """Standalone .csv/.txt members.

    Skips .gdb-internal files (a gdb's tabular data already arrives as layers) and nested zips.
    Every .txt counts, judged by suffix alone, so a README.txt or metadata .txt is returned
    alongside real tables; callers whose archives carry those need to filter them out."""
    return _discover_by_suffix(names, (".csv", ".txt"))


def discover_pdf_files(names: list[str]) -> list[str]:
    return _discover_by_suffix(names, (".pdf",))


def object_key(path: str, shp_bases: set[str]) -> tuple[str, str]:
    """Which object a zip member belongs to, and that object's kind.

    Lock files are tested before the .gdb prefix so they stay top-level objects; folded into
    the gdb, callers couldn't see whether an archive ships them.

    Any standalone .csv, .txt or .dbf is kind "table", by suffix alone, so a README.txt is
    a "table" too.
    """
    lower = path.lower()
    if lower.endswith(".lock"):
        return path, "lock"

    idx = lower.find(".gdb/")
    if idx != -1:
        return path[: idx + 4], "gdb"

    if lower.endswith(".zip"):
        return path, "zip"

    base, ext = shapefile_split(path)
    if base in shp_bases:
        return f"{base}.shp", "shapefile"
    if ext in (".csv", ".txt", ".dbf"):
        return path, "table"
    return path, "file"


def shapefile_split(path: str) -> tuple[str, str]:
    """(basename, extension), treating .shp.xml as one extension so the metadata sidecar
    groups with its shapefile rather than looking like a lone .xml."""
    lower = path.lower()
    if lower.endswith(".shp.xml"):
        return path[: -len(".shp.xml")], ".shp.xml"
    base, ext = posixpath.splitext(path)
    return base, ext.lower()


def build_object_inventory(
    infolist: list[zipfile.ZipInfo],
    gdb_contents: dict[str, list[dict]],
    unreadable: set[str],
) -> list[dict]:
    """What the archive holds, as objects rather than files.

    Args:
        infolist: the archive's members, e.g. from a central-directory read.
        gdb_contents: each .gdb's datasets, keyed by gdb path, as the caller resolved them.
            Namelists can't reveal these, so a gdb missing from the mapping is listed empty.
        unreadable: gdb paths the caller could not open. They get `contents: None`, so
            "could not look" stays distinguishable from "empty".

    Returns:
        One dict per object - `path`, `kind` (shapefile, gdb, lock, zip, table, file) and
        `size_bytes` summed over its members - plus `parts` (extensions) for a shapefile and
        `contents` for a gdb, sorted by path.

    Grouping is filename-only, so it still names a shapefile inside an archive no reader can
    open.
    """
    files = [i for i in infolist if not i.is_dir()]
    shp_bases = {shapefile_split(i.filename)[0] for i in files if i.filename.lower().endswith(".shp")}

    objects: dict[str, dict] = {}
    parts: dict[str, set[str]] = {}
    for info in files:
        key, kind = object_key(info.filename, shp_bases)
        obj = objects.setdefault(key, {"path": key, "kind": kind, "size_bytes": 0})
        obj["size_bytes"] += info.file_size
        if kind == "shapefile":
            parts.setdefault(key, set()).add(shapefile_split(info.filename)[1])

    for key, obj in objects.items():
        if obj["kind"] == "shapefile":
            obj["parts"] = sorted(parts[key])
        elif obj["kind"] == "gdb":
            obj["contents"] = None if key in unreadable else gdb_contents.get(key, [])
    return sorted(objects.values(), key=lambda o: o["path"])
