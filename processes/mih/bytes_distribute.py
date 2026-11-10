import logging
import zipfile
from datetime import datetime
from pathlib import Path

import arcpy

from main import find_latest_mih_fc, get_city_council_date
from dcpgis.utils import strip_metadata_and_update_dates


# ---------------------------------------------------------------------------
# BYTES (BP / open data) steps
# ---------------------------------------------------------------------------


def resolve_output_dirs(publication_date: str, mih_output_path: Path) -> dict[str, Path]:
    """Create and return year/publication_date/shp and meta subdirectories."""
    root = mih_output_path / publication_date[:4] / publication_date
    (root / "shp").mkdir(parents=True, exist_ok=True)
    (root / "meta").mkdir(parents=True, exist_ok=True)
    return {"root": root, "shp": root / "shp", "meta": root / "meta"}


def export_to_shapefile(sde_path: Path, version_name: str, shp_dir: Path, mih_config: dict) -> Path:
    """Export MIH FC from the given SDE version to shapefile and repair geometry. Return path to .shp file."""
    schema = mih_config["connection_file"]["schema"]
    fc_name = f"{schema}.{mih_config['mih_sde_fc_name']}"

    arcpy.env.workspaceVersion = version_name
    arcpy.env.workspace = str(sde_path)

    arcpy.conversion.FeatureClassToShapefile([fc_name], str(shp_dir))

    shp_path = shp_dir / f"{mih_config['mih_sde_fc_name']}.shp"
    arcpy.management.RepairGeometry(str(shp_path))

    return shp_path


def zip_shapefile(shp_dir: Path, output_dir: Path, publication_date: str) -> Path:
    """Zip shapefile components into nycmih_<publication_date>.zip."""
    zip_path = output_dir / f"nycmih_{publication_date}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in shp_dir.iterdir():
            zf.write(f, arcname=f.name)  # arcname= stores just the filename, not the full path
    return zip_path


def generate_metadata_xml(meta_dir: Path, templates_dir: Path, publication_date: str, city_council_date: str) -> None:
    """Render MIH metadata XMLs from repo templates, filling in publication and city council dates."""
    pub_dt = datetime.strptime(publication_date, "%Y%m%d")
    cc_dt = datetime.strptime(city_council_date, "%Y%m%d")
    publication_date_short = pub_dt.strftime("%#m/%d/%y")  # Windows: %#m suppresses leading zero
    city_council_date_long = cc_dt.strftime("%#m/%d/%Y")
    for filename in ["MIHmetaBytes.xml", "MIHmetaGuide.xml"]:
        template = (templates_dir / filename).read_text()
        rendered = template.format(
            publication_date=publication_date,
            publication_date_short=publication_date_short,
            city_council_date_long=city_council_date_long,
        )
        (meta_dir / filename).write_text(rendered)


def run_bytes(global_config: dict, mih_config: dict) -> None:
    sde_path = Path(global_config["connection_file_path"]) / mih_config["connection_file"]["name"]
    mih_output_path = Path(global_config["open_data_staging_path"]) / mih_config["mih_output_subpath"]
    schema = mih_config["connection_file"]["schema"]
    fc_path = str(sde_path / f"{schema}.{mih_config['mih_sde_fc_name']}")

    version_name, publication_date = find_latest_mih_fc(sde_path)
    city_council_date = get_city_council_date(fc_path, version_name)
    templates_dir = Path(__file__).parent.parent.parent / "templates" / "metadata"
    dirs = resolve_output_dirs(publication_date, mih_output_path)

    shp_path = export_to_shapefile(sde_path, version_name, dirs["shp"], mih_config)
    strip_metadata_and_update_dates(str(shp_path), publication_date)
    zip_shapefile(dirs["shp"], dirs["root"], publication_date)
    generate_metadata_xml(dirs["meta"], templates_dir, publication_date, city_council_date)

    logging.info("BYTES distribution complete")
