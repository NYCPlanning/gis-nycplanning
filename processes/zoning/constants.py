ZONING_CONVENTIONS = {
    "nyco": {
        "trd_fc_name": "DZM_nyco",
        "trd_full_fc_name": "GISTRD.TRD.DZM_nyco",
        "public_output_name": "nyc_zoning_commercial_overlays",
        "public_shp_name":"nyc_zoning_commercial_overlays.shp",
        "keep_fields": ["OBJECTID", "Shape", "OVERLAY", "Shape_Length", "Shape_Area"],
        "rename_fields": {},
        "sql_expression":None,
        "statistics_fields":[],
    },
    "nylh": {
        "trd_fc_name": "DZM_nylh",
        "trd_full_fc_name": "GISTRD.TRD.DZM_nylh",
        "public_output_name": "nyc_zoning_limited_height",
        "public_shp_name": "nyc_zoning_limited_height.shp",
        "keep_fields": ["OBJECTID", "Shape", "LHNAME", "LHLBL","Shape_Length", "Shape_Area"],
        "rename_fields": {},
        "sql_expression":None,
        "statistics_fields":[],
    },
    "nysp": {
        "trd_fc_name": "DZM_nysp",
        "trd_full_fc_name": "GISTRD.TRD.DZM_nysp",
        "public_output_name": "nyc_zoning_special_districts",
        "public_shp_name": "nyc_zoning_special_districts.shp",
        "keep_fields": ["OBJECTID", "Shape", "SDNAME", "SDLBL", "Shape_Length", "Shape_Area"],
        "rename_fields": {},
        "sql_expression":None,
        "statistics_fields":[["SDLBL", "FIRST"]],
    },
    "nysp_sd": {
        "trd_fc_name": "DZM_nysp_sd",
        "trd_full_fc_name": "GISTRD.TRD.DZM_nysp_sd",
        "public_output_name": "nyc_zoning_special_subdistricts",
        "public_shp_name": "nyc_zoning_special_subdistricts.shp",
        "keep_fields": ["OBJECTID", "Shape", "SPNAME", "SPLBL", "SUBDIST", "SUBDIST_LBL", "SUBAREA_LBL", "SUBAREA_OTR","Shape_Length", "Shape_Area"],
        "rename_fields": {},
        "sql_expression":"SUBDIST IS NOT NULL",
        "statistics_fields":[],
    },
    "nyzd": {
        "trd_fc_name": "DZM_nyzd",
        "trd_full_fc_name": "GISTRD.TRD.DZM_nyzd",
        "public_output_name": "nyc_zoning_districts",
        "public_shp_name": "nyc_zoning_districts.shp",
        "keep_fields": ["OBJECTID", "Shape", "ZONEDIST", "Shape_Length", "Shape_Area"],
        "rename_fields": {},
        "sql_expression":None,
        "statistics_fields":[],
    },
    "nyzma": {
        "trd_fc_name": "DZM_nyzi",
        "trd_full_fc_name": "GISTRD.TRD.DZM_nyzi",
        "public_output_name": "nyc_zoning_map_amendments",
        "public_shp_name": "nyc_zoning_map_amendments.shp",
        "keep_fields": ["OBJECTID", "Shape", "EFFECTIVE", "STATUS", "ULURPNO", "LUCATS", "PROJECT_NAME", "Shape_Length", "Shape_Area"],
        "rename_fields": {},
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