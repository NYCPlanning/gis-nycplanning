# Zoning Process

## Overview
The `processes/zoning` module prepares and distributes TRD-owned zoning products, as defined in `constants.py`. It extracts zoning features from the source database, applies transformations such as field filtering and spatial operations, generates and applies standardized updated metadata, and packages the results for distribution to the desired open data staging directory. 

![image](.\documentation\high-level-workflow.png)

## How to run
To run, establish `gis-nycplanning/` as your base directory and run `python processes/zoning/zoning.py --env prod` or `python processes/zoning/zoning.py --env dev` in your terminal.

## Key Components
`config/`
- `prod_config.yml`— global config

`processes/zoning/`
- `zoning.py` — main orchestration script
- `constants.py` — configuration dictionaries and naming conventions
- `utils.py` — helper functions for export, metadata, and cleanup. These utilities are specific to Zoning distribution, but are potentially conceptionally applicable across products.
- `config/` — product-specific configuration files
- `log/` — process log files
- `templates/` — metadata templates

`src/dcpgis/`
- `cli.py` — ...
- `utils/` — global utilities

## Configuration
Environment arguments: `--env dev`, `--env prod`

Config Files
- `config/[env]_config.yml`: 
  - [env] determined by --env CLI argument
  - Variable descriptions can be found in `/config/template_config.yml`
  - The global config is intended to only include variables that are broadly applicapble. Editable values are intended to only be populated for override purposes and should therefore have logic associated to calculate them when scripts are being run typical circumstances
- `processes/zoning/config/[env]_config.yml`: 
  - [env] determined by --env CLI argument
  - Variable descriptions can be found in `/processes/zoning/config/template_config.yml`
  - The intention of having a local product config is to allow for product-by-product variability

## Workflow
- Temporary staging directory creation
- Creating geodatabases and shapefile outputs
- Exporting zoning feature classes
- Copying and packaging raster/map products
- Metadata generation and application
- Final staging to open data directories
- Temp directory deleted

## Logging and Diagnostics
- prod_zoning.log and/or dev_zoning.log should be present `processes/zoning/log/`. Logging defaults to `INFO`, and can be overriden in the global config (e.g., `log_level_override: DEBUG`) 
- How to interpret process logs
- Common runtime issues and where to find details

## Troubleshooting
- ...

## Contributing / Extending
- Metadata
  - Updates to static descriptive language can be made directly to xmls in `processes/zoning/templates/metadata/`. A copy should also be added to the `archive/` sub-directory.
  - Metadata xmls contain in-text {variables} that are defined in `processes/zoning/constants.py` `METADATA_XML_VALUES`. Version and product dependent values in this dictionary derived from product convention dictionaries and 
- Updating naming conventions or incorporating a new output?
  - File naming conventions can be updated in `constants.py`. Source, output, and schema information can be updated in the respective `{}_CONVENTIONS` dictionary; packaging outputs such as zipfile names and contents can be updated in `ZONING_PACKAGING`. 
    - Note: If a product's `public_output_name` is changed, ensure the corresponding xml file recieves the same updated name
  - New zoning features can be added to outputs by updating `constants.py`. For example, if the Zoning Index were to added as a desired output, a new key-value pair entry would be added to `ZONING_CONVENTIONS`. 

- Best practices for modifying the pipeline
