from __future__ import annotations

from datahack_ingest.catalog import ApiSource, FileSource, SqlSource
from datahack_ingest.extractors.api import ApiExtractor
from datahack_ingest.extractors.base import ExtractState, ExtractUnit
from datahack_ingest.extractors.files import FileExtractor
from datahack_ingest.extractors.sql import SqlExtractor


def build_extractor(source: FileSource | ApiSource | SqlSource, landing_uri: str):
    if isinstance(source, FileSource):
        return FileExtractor(source, landing_uri)
    if isinstance(source, ApiSource):
        return ApiExtractor(source)
    if isinstance(source, SqlSource):
        return SqlExtractor(source)
    raise TypeError(f"tipo de fonte não suportado: {type(source).__name__}")


__all__ = ["ExtractState", "ExtractUnit", "build_extractor"]
