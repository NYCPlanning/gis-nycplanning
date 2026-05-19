import arcpy
import requests

# define constants
SOURCE_URL = ""  # URL to GDB on AGO
STAGING_PATH = ""  # Local file path to store GDB
XML_PATH = ""  # Path to exported XML
EGDB = ""  # Connection file to enterprise DB


def download_file(url, dest_path):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def main():
    arcpy.env.overwriteOutput = True

    download_file(url=SOURCE_URL, dest_path=STAGING_PATH)

    arcpy.management.ExportXMLWorkspaceDocument(
        in_data=STAGING_PATH,
        out_file=XML_PATH,
        export_type="DATA",
    )

    arcpy.management.ImportXMLWorkspaceDocument(
        target_geodatabase=EGDB,
        in_file=XML_PATH,
        import_type="DATA",
    )


if __name__ == "__main__":
    main()
