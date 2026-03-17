# Exploring use of a multi environment pipeline

## Context
Most of the Python tools used by the DCP GIS Team use virtual environments based off of the default conda installation that comes with ArcGIS Pro. Much of our data exists in the Esri ecosystem, and having access to `arcpy`, `arcgis`, and other Esri-specific packages is important.

This limits us to the version of Python that is packaged with ArcGIS Pro (e.g. Pro 3.5 ships with Python 3.11.11). Often there are alternative open source tools that we would like to use to replace Esri's methods, such as Data Engineering's `dcpy` package. This causes issues if we want to run tools based on the Python 3.13-based `dcpy`, while our default conda environment is pinned to 3.11.

This experiment is intended to prove the viability of a single pipeline based around multiple versions of Python. 

An example of a problem this could solve is: accessing and transforming some dataset using Esri's conda, calling `dcpy` to generate up to date metadata for that dataset, and then using Esri's conda to write that dataset to an endpoint like an enterprise geodatabase.

Some benefits include being able to call tools from different Python versions, being able to "sandwich" `dcpy`-based processing in between Esri-based processing, and keeping the whole pipeline in Python for simplicity.

Alternate approaches could use a more mature orchestration tool that calls different Python interpreters for different tasks, or simply using bash/PowerShell to orchestrate the pipeline.

## Execution
 (assumes that the repo root is the current workinf directory)

- Create the non-conda virtual envirnment by running `build.ps1`

- Call pipeline via `python experiments\multi_env\pipeline_runner.py`

- Examine console outputs