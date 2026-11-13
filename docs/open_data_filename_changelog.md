# NYC Planning Open Data Change Log
#### Last Updated: November 10, 2026

## Description
This change log records changes to download links, and file names for datasets published on [Bytes of the Big Apple](https://www.nyc.gov/content/planning/pages/resources#datasets). NYC Planning is updating its data pipeline and migrating datasets to a consistent naming convention. Datasets will be
added to this page as their changes are scheduled. 

Each dataset has its own section. Latest changes within a section are listed first.

## How to Migrate
If you download, script against, or link to an affected dataset:
1. **Update download URLs.** The zip file name is part of the download URL, so a renamed zip file has a new URL.
2. **Update file and layer names.** Change references to geodatabases, feature classes, shapefiles, and CSVs in scripts, ETL jobs, map documents, and saved projects.
3. **Update field names** if the dataset lists field changes. See data dictionaries for schema changes.

Latest-data zip files no longer include a date in the file name, so the link to the latest release stays the same from one release to the next. Archived releases keep a `version` or `YYYYMM` in the name.

## Table of Contents
- [Georeferenced Zoning Maps](#georeferenced-zoning-maps)
- [Greater Transit Zone and Transit Zones](#greater-transit-zone-and-transit-zones)
- [Zoning Features](#zoning-features)
- [Zoning Tax Lot Database (ZTLDB)](#zoning-tax-lot-database)

## Georeferenced Zoning Maps
- **Dataset page:** https://www.nyc.gov/content/planning/pages/resources/datasets/georeferenced-map
- **Download URL format:** `https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/gis-zoning-features/<file name>`

### November 15th-30th, 2026: New file names and URLs (scheduled)
Effective mid to late-November 2026, NYC Georeferenced Zoning Maps will have updated file names and URLs.

#### Zip files and download URLs
| Release | Old file name | New file name |
|---|---|---|
| Latest | `georeferencedzoningmaps_YYYYMM.zip` | `nyc_zoning_georeferenced_maps_gdb.zip` |
| Archive | `georeferencedzoningmaps_YYYYMM.zip` | `nyc_zoning_georeferenced_maps_YYYYMM_gdb.zip` |

#### File geodatabase
| Old name | New name |
|---|---|
| `georeferencednyczoningmaps.gdb` | `nyc_zoning_georeferenced_maps.gdb` |

#### Geodatabase contents
| Old name | New name |
|---|---|
| `georeferencednyczoningmaps` | `zoning_georeferenced_maps` |

## Greater Transit Zone and Transit Zones
- **Dataset page:** https://www.nyc.gov/content/planning/pages/resources/datasets/greater-transit-zone
- **Download URL format:** `https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/greater-transit-zone/<file name>`

### November 10, 2026: New file names and URLs
Effective November 10, 2026, Greater Transit Zone and Transit Zones have updated shapefile names and new file geodatabase downloads. There are no field or schema changes.

#### Zip files and download URLs
| Dataset | Release | Format | Old file name | New file name |
|---|---|---|---|---|
| Greater Transit Zone | Latest | Shapefile | `nyc_greater_transit_zone.zip` | `nyc_greater_transit_zone_shp.zip` |
| Greater Transit Zone | Latest | File geodatabase | Not previously available | `nyc_greater_transit_zone_gdb.zip` |
| Greater Transit Zone | Archive | Shapefile | `nyc_greater_transit_zone_YYYYMMDD.zip` | `nyc_greater_transit_zone_YYYYMM_shp.zip` |
| Greater Transit Zone | Archive | File geodatabase | Not previously available | `nyc_greater_transit_zone_YYYYMM_gdb.zip` |
| Transit Zones | Latest | Shapefile | `nyc_transit_zones.zip` | `nyc_transit_zones_shp.zip` |
| Transit Zones | Latest | File geodatabase | Not previously available | `nyc_transit_zones_gdb.zip` |
| Transit Zones | Archive | Shapefile | `nyc_transit_zones_YYYYMMDD.zip` | `nyc_transit_zones_YYYYMM_shp.zip` |
| Transit Zones | Archive | File geodatabase | Not previously available | `nyc_transit_zones_YYYYMM_gdb.zip` |

The new release uses `202610` for `YYYYMM` in archived zip file names. The December 5, 2024 shapefile releases remain available in the archive under their existing dated zip file names.

#### Shapefiles
| Dataset | Old name | New name |
|---|---|---|
| Greater Transit Zone | `greater_transit_zone_YYYYMMDD.shp` | `greater_transit_zone.shp` |
| Transit Zones | `transit_zones_YYYYMMDD.shp` | `transit_zones.shp` |

#### File geodatabases
| Dataset | Old name | New name |
|---|---|---|
| Greater Transit Zone | Not previously available | `nyc_greater_transit_zone.gdb` |
| Transit Zones | Not previously available | `nyc_transit_zones.gdb` |

#### Geodatabase contents
| Dataset | New feature class name |
|---|---|
| Greater Transit Zone | `greater_transit_zone` |
| Transit Zones | `transit_zones` |

## Zoning Features
- **Dataset page:** https://www.nyc.gov/content/planning/pages/resources/datasets/gis-zoning-features
- **Download URL format:** `https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/gis-zoning-features/<file name>`

### November 15th-30th, 2026: New file names and URLs (scheduled)
Effective mid to late-November 2026, NYC GIS Zoning Features will have updated file names and URLs.

#### Zip files and download URLs
| Release | Format | Old file name | New file name |
|---|---|---|---|
| Latest | Shapefile | `nycgiszoningfeatures_YYYYMMshp.zip` | `nyc_zoning_features_shp.zip` |
| Latest | File geodatabase | `nycgiszoningfeatures_YYYYMMfgdb.zip` | `nyc_zoning_features_gdb.zip` |
| Archive | Shapefile | `nycgiszoningfeatures_YYYYMMshp.zip` | `nyc_zoning_features_YYYYMM_shp.zip` |
| Archive | File geodatabase | `nycgiszoningfeatures_YYYYMMfgdb.zip` | `nyc_zoning_features_YYYYMM_gdb.zip` |

#### Feature classes and shapefiles
| Layer | Old name | New name |
|---|---|---|
| Commercial overlays | `nyco` | `zoning_commercial_overlays` |
| Limited height districts | `nylh` | `zoning_limited_height` |
| Special purpose districts | `nysp` | `zoning_special_districts` |
| Special purpose subdistricts | `nysp_sd` | `zoning_special_subdistricts` |
| Zoning districts | `nyzd` | `zoning_districts` |
| Zoning map amendments | `nyzma` | `zoning_map_ammendments` |

#### File geodatabase
| Old name | New name |
|---|---|
| `zoning.gdb` | `nyc_zoning_features.gdb` |

## Zoning Tax Lot Database
- **Dataset page:** https://www.nyc.gov/content/planning/pages/resources/datasets/zoning-taxlot-database
- **Download URL format:** `https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/zoning-tax-lot-database/<file name>`

### November 15th-30th, 2026: New file names and URLs (scheduled)
Effective mid to late-November 2026, NYC Zoning Tax Lot Database (ZTLDB) will have updated file names and URLs.

#### Zip files and download URLs
| Release | Format | Old file name | New file name |
|---|---|---|---|
|Latest|csv|nyczoningtaxlotdb_YYYYMMDD.zip|nyc_zoning_tax_lot_database_csv.zip|
|Archive|csv|nyczoningtaxlotdb_YYYYMMDD.zip|nyc_zoning_tax_lot_database_YYYYMM_csv.zip|

#### CSVs
| Old name | New name |
|---|---|
|NY_ZoningTaxLotDBYYYYMMDD.csv|zoning_tax_lot_database.csv|