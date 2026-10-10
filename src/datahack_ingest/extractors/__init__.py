from __future__ import annotations

from datahack_ingest.catalog import AnySource, ApiSource, FileSource
from datahack_ingest.extractors.api import ApiExtractor
from datahack_ingest.extractors.base import ExtractState, ExtractUnit
from datahack_ingest.extractors.files import FileExtractor


def build_extractor(source: AnySource, landing_uri: str):
    if isinstance(source, FileSource):
        return FileExtractor(source, landing_uri)
    if isinstance(source, ApiSource):
        return ApiExtractor(source)
    raise TypeError(f"tipo de fonte não suportado: {type(source).__name__}")


__all__ = ["ExtractState", "ExtractUnit", "build_extractor"]
