"""Static guard against the troubleshooter drifting onto dcpgis or a custom conda env.

Reads the tool's own source as plain text - no arcpy import, no ArcGIS Pro install
required - so this runs in any plain Python environment (including a lint-only CI
runner that doesn't have arcpy).
"""

import re
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[4] / "utilities" / "gis_machine_troubleshooter"
SOURCE_FILES = [
    TOOL_DIR / "run_troubleshooter.ps1",
    TOOL_DIR / "internal" / "troubleshooter_functions.ps1",
    TOOL_DIR / "internal" / "collect_gis_info.py",
]


def _source_text() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in SOURCE_FILES}


def test_source_files_exist():
    # Guards the test itself against silently checking nothing if the tool is
    # ever restructured again.
    for path in SOURCE_FILES:
        assert path.is_file(), f"expected troubleshooter source file at {path}"


def test_no_dcpgis_usage():
    # Matches an actual dependency on dcpgis (an import, a path segment, a module
    # reference) but not the header comments that document this tool's intentional
    # non-dependency on it - those legitimately contain the word.
    usage_pattern = re.compile(r"(import\s+dcpgis|from\s+dcpgis|[\\/]dcpgis[\\/])", re.IGNORECASE)
    for path, text in _source_text().items():
        match = usage_pattern.search(text)
        assert not match, (
            f"{path.name} appears to use dcpgis ({match.group(0)!r}) - the troubleshooter "
            "must stay standalone and not depend on this repo's package"
        )


def test_python_side_does_not_touch_sys_path():
    # No sys.path manipulation means collect_gis_info.py can only ever import what the
    # interpreter that launched it already has on its path - i.e. whatever conda env
    # run_troubleshooter.ps1 pointed $pythonPath at, never a repo-relative src/ package.
    text = (TOOL_DIR / "internal" / "collect_gis_info.py").read_text(encoding="utf-8")
    assert "sys.path" not in text


def test_only_the_base_arcgis_conda_env_is_ever_referenced():
    # Every conda-env-shaped path (...\envs\<name>\...) across the tool's own source
    # must name the default ArcGIS Pro env, never a cloned/custom one (e.g. the
    # "gis-env" produced by utilities/powershell/deploy_esri_py_env_pro.ps1).
    env_name_pattern = re.compile(r"envs\\([\w.-]+)\\", re.IGNORECASE)
    found_env_names = set()
    for text in _source_text().values():
        found_env_names.update(env_name_pattern.findall(text))

    assert found_env_names, "expected to find at least one conda env path to check"
    assert found_env_names == {"arcgispro-py3"}, (
        f"found unexpected conda env name(s) {found_env_names - {'arcgispro-py3'}} - "
        "the troubleshooter must only ever resolve the default ArcGIS Pro env"
    )
