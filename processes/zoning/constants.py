ZONING_CONVENTIONS = {
    "nyco": {
        "trd_fc_name": "DZM_nyco",
        "public_output_name": "nyc_zoning_commercial_overlays",
        "desired_fields": ["OBJECTID", "Shape", "OVERLAY", "Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[],
    },
    "nylh": {
        "trd_fc_name": "DZM_nylh",
        "public_output_name": "nyc_zoning_limited_height",
        "desired_fields": ["OBJECTID", "Shape", "LHNAME", "LHLBL","Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[],
    },
    "nysp": {
        "trd_fc_name": "DZM_nysp",
        "public_output_name": "nyc_zoning_special_districts",
        "desired_fields": ["OBJECTID", "Shape", "SDNAME", "SDLBL", "Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[["SDLBL", "FIRST"]],
    },
    "nysp_sd": {
        "trd_fc_name": "DZM_nysp_sd",
        "public_output_name": "nyc_zoning_special_subdistricts",
        "desired_fields": ["OBJECTID", "Shape", "SPNAME", "SPLBL", "SUBDIST", "SUBDIST_LBL", "SUBAREA_LBL", "SUBAREA_OTR","Shape_Length", "Shape_Area"],
            
        "sql_expression":"SUBDIST IS NOT NULL",
        "statistics_fields":[],
    },
    "nyzd": {
        "trd_fc_name": "DZM_nyzd",
        "public_output_name": "nyc_zoning_districts",
        "desired_fields": ["OBJECTID", "Shape", "ZONEDIST", "Shape_Length", "Shape_Area"],
        "sql_expression":None,
        "statistics_fields":[],
    },
    "nyzma": {
        "trd_fc_name": "DZM_nyzi",
        "public_output_name": "nyc_zoning_map_amendments",
        "desired_fields": ["OBJECTID", "Shape", "EFFECTIVE", "STATUS", "ULURPNO", "LUCATS", "PROJECT_NAME", "Shape_Length", "Shape_Area"],
        "sql_expression":"INITIATIVE_TYPE = '1' AND (STATUS = '1' OR STATUS = '2')",
        "statistics_fields":[],
    },
}

GEOREF_CONVENTIONS = {
    "georeferenced_zoning_maps": {
        "trd_fc_name": "NYC_Zoning_Maps",
        "public_output_name": "nyc_georeferenced_zoning_maps",
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