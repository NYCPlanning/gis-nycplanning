import xml.etree.ElementTree as ET
import sys
import platform


def part_c(item_path):
    """Return the CreaDate and CreaTime elements from shapefile metadata"""

    print("Part C: Getting creation time with arcpy/conda-based env")
    print(f"\tPython version: {platform.python_version()}")
    print(f"\tFile: {__file__}")
    print(f"\tInterpreter: {sys.executable}")

    md_path = str(item_path) + ".xml"
    tree = ET.parse(md_path)
    root = tree.getroot()
    crea_time_element = root.find("./Esri/CreaTime")
    crea_date_element = root.find("./Esri/CreaDate")

    print("\tCreation timestamp values from new metadata:")
    print(
        f"\t\tCreaDate: {crea_date_element.text}\n\t\tCreaTime: {crea_time_element.text}"
    )
