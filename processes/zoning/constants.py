#TODO: Add docstring documentation
ZONING_CONVENTIONS = {
    "nyco": {
        "trd_fc_name": "DZM_nyco",
        "public_output_name": "nyc_zoning_commercial_overlays",
        "desired_fields": ["OBJECTID", "Shape", "OVERLAY", "Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[],
        "meta_res_title": "NYC Commercial Overlays (NYCO)",
        "gdb_name": "nyc_zoning_features.gdb",
        "apply_to_shapefile": True,
    },
    "nylh": {
        "trd_fc_name": "DZM_nylh",
        "public_output_name": "nyc_zoning_limited_height",
        "desired_fields": ["OBJECTID", "Shape", "LHNAME", "LHLBL","Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[],
        "meta_res_title": "NYC Limited Height Districts (NYLH)",
        "gdb_name": "nyc_zoning_features.gdb",
        "apply_to_shapefile": True,
    },
    "nysp": {
        "trd_fc_name": "DZM_nysp",
        "public_output_name": "nyc_zoning_special_districts",
        "desired_fields": ["OBJECTID", "Shape", "SDNAME", "SDLBL", "Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[["SDLBL", "FIRST"]],
        "meta_res_title": "NYC Special Purpose Districts (NYSP)",
        "gdb_name": "nyc_zoning_features.gdb",
        "apply_to_shapefile": True,
    },
    "nysp_sd": {
        "trd_fc_name": "DZM_nysp_sd",
        "public_output_name": "nyc_zoning_special_subdistricts",
        "desired_fields": ["OBJECTID", "Shape", "SDNAME", "SDLBL", "SUBDIST", "SUB_AREA_NM", "SUBDIST_LBL", "SUBAREA_LBL", "SUBAREA_OTR","Shape_Length", "Shape_Area"],
        "sql_expression":"SUBDIST IS NOT NULL",
        "statistics_fields":[],
        "meta_res_title": "NYC Special Purpose Sub-Districts (NYSP_SD)",
        "gdb_name": "nyc_zoning_features.gdb",
        "apply_to_shapefile": True,
    },
    "nyzd": {
        "trd_fc_name": "DZM_nyzd",
        "public_output_name": "nyc_zoning_districts",
        "desired_fields": ["OBJECTID", "Shape", "ZONEDIST", "Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[],
        "meta_res_title": "NYC Zoning Districts (NYZD)",
        "gdb_name": "nyc_zoning_features.gdb",
        "apply_to_shapefile": True,
    },
    "nyzma": {
        "trd_fc_name": "DZM_nyzi",
        "public_output_name": "nyc_zoning_map_amendments",
        "desired_fields": ["OBJECTID", "Shape", "EFFECTIVE", "STATUS", "ULURPNO", "LUCATS", "PROJECT_NAME", "Shape_Length", "Shape_Area"],
        "sql_expression":"INITIATIVE_TYPE = '1' AND (STATUS = '1' OR STATUS = '2')",
        "statistics_fields":[],
        "meta_res_title": "NYC Zoning Map Amendments (NYZMA)",
        "gdb_name": "nyc_zoning_features.gdb",
        "apply_to_shapefile": True,
    },
}

GEOREF_CONVENTIONS = {
    "georeferenced_zoning_maps": {
        "trd_fc_name": "NYC_Zoning_Maps",
        "public_output_name": "nyc_georeferenced_zoning_maps",
        "meta_res_title": "NYC Georeferenced Zoning Maps",
        "gdb_name": "nyc_georeferenced_zoning_maps.gdb",
        "apply_to_shapefile": False,
    }
}

ZONING_PACKAGING= {
    "zip_files": {
        "zoning_features_gdb": {
            "src_parent_dir": "gdb",
            "name": "nyc_zoning_features_gdb.zip",
            "contents":["nyc_zoning_features.gdb"]
        },
        "georeferenced_gdb": {
            "src_parent_dir": "gdb",
            "name": "nyc_georeferenced_zoning_maps_gdb.zip",
            "contents":["nyc_georeferenced_zoning_maps.gdb"]
        },
        "zoning_features_shp": {
            "src_parent_dir": "shp",
            "name": "nyc_zoning_features_shp.zip",
            "contents":["nyc_zoning_commercial_overlays.*",
                        "nyc_zoning_districts.*",
                        "nyc_zoning_limited_height.*",
                        "nyc_zoning_map_amendments.*",
                        "nyc_zoning_special_districts.*",
                        "nyc_zoning_special_subdistricts.*",
                        ]
        },
    },
    "metadata": {
        "zd": {
            "src_parent_dir": "metadata",
            "name": "nyc_zoning_districts_metadata.xlsx",
        }
    }
}

#TODO: Confirm all zoning features have the same crea_date
METADATA_XML_VALUES = {
    "crea_date": "20151216",
    "pub_date": "", 
    "council_date": "",
    "crea_time": "00000000",
    "arcgis_format": "1.0",
    "sync_once": "TRUE",
    "item_name": "",
    "item_name_sync": "TRUE",
    "ims_content_type": "002",
    "ims_content_type_sync": "TRUE",
    "min_scale": "150000000",
    "max_scale": "5000",
    "arcgis_profile": "ISO 19139 Metadata Implementation Specification",
    "res_title": "",
    "scope_value": "005",
    "md_date_st": "19261122",
    "md_date_st_sync": "TRUE",
}