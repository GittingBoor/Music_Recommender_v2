"""Metadata extraction package.

One module per external provider (AcoustID, MusicBrainz, Last.fm, Spotify),
plus pure text/date helpers in ``cleaning`` and local file-tag reading in
``file_tags``. ``extractor.extract_all_metadata`` orchestrates them.
"""
from src.metadata.extractor import extract_all_metadata
from src.metadata.file_tags import extract_file_metadata

__all__ = ["extract_all_metadata", "extract_file_metadata"]
