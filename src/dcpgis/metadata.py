import arcpy
from typing import Union


class Metadata(arcpy.metadata.Metadata):
    def __init__(self, dataset=Union[str, None]):
        if dataset:
            super().__init__(dataset)
        else:
            super().__init__()

    def generate_thumbnail(self):
        # visualize dataset and generate a thumbnail image
        raise NotImplementedError

    def update_metadata_values(self):
        # update default values like description and title, but also update custom
        # values via xpath like city council date, distribution URL, etc.
        raise NotImplementedError

    def update(self):
        # upgrade, synchronize, maybe also generate thumbnail
        raise NotImplementedError

    def clean(self):
        # delete gp history, sensitive paths, and everything else associated
        raise NotImplementedError
