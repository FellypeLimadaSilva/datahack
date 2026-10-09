from __future__ import annotations

import logging
import posixpath
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import fsspec
import yaml
from defusedxml.ElementTree import fromstring
from pydantic import TypeAdapter, ValidationError

from datahack_ingest.catalog import (
    DEFAULT_EXCLUDE,
    Catalog,
    Source,
    read_catalog_specs,
)
from datahack_ingest.extractors.files import _modified_epoch, accepts, resolve_uri
from datahack_ingest.normalize import MAX_IDENT, normalize_identifier
from datahack_ingest.settings import Settings

log = logging.getLogger(__name__)

FORMAT_BY_EXT = {
    ".csv": "csv",
    ".tsv": "csv",
    ".txt": "csv",
    ".psv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xml": "xml",
    ".avro": "avro",
    ".orc": "orc",
}
COMPRESSION_EXT = (".gz", ".gzip", ".bz2", ".xz", ".zst", ".zstd")
SQLITE_EXT = (".db", ".sqlite", ".sqlite3")
NOT_TABULAR = (
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".svg",
    ".md",
    ".rtf",
    ".html",
    ".htm",
    ".py",
    ".ipynb",
    ".pbix",
)
HINTS = {
    ".xls": "Excel 97-2003 não suportado: salve como .xlsx ou .csv",
    ".mdb": "Access não suportado: exporte as tabelas para .csv ou .xlsx",
    ".accdb": "Access não suportado: exporte as tabelas para .csv ou .xlsx",
    ".sql": "dump SQL: restaure em um banco e declare uma fonte kind: sql",
    ".dump": "backup binário: restaure em um banco e declare uma fonte kind: sql",
    ".backup": "backup binário: restaure em um banco e declare uma fonte kind: sql",
    ".bak": "backup binário: restaure em um banco e declare uma fonte kind: sql",
    ".dbf": "DBF não suportado: converta para .csv",
}
SIDECAR = "_source.yml"
GLOB_CHARS = set("*?[]{}")
AUTO_FLATTEN_LEVEL = 2

_SOURCE_ADAPTER = TypeAdapter(Source)


@dataclass
class ResolvedCatalog:
    catalog: Catalog
    origins: dict[str, str] = field(default_factory=dict)
    ignored: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def origin(self, name: str) -> str:
        return self.origins.get(name, "catalog")


def _split_ext(name: str) -> tuple[str, str, str | None]:
    lower = name.lower()
    compression = None
    for ext in COMPRESSION_EXT:
        if lower.endswith(ext):
            compression = ext
            lower = lower[: -len(ext)]
            name = name[: -len(ext)]
            break
    stem, ext = posixpath.splitext(name)
    return stem, ext.lower(), compression


def classify(name: str) -> tuple[str | None, str | None]:
    _, ext, _ = _split_ext(posixpath.basename(name))
    if ext in FORMAT_BY_EXT:
        return FORMAT_BY_EXT[ext], None
    if ext == ".zip":
        return "zip", None
    if ext in SQLITE_EXT:
        return "sqlite", None
    if ext in HINTS:
        return None, HINTS[ext]
    if ext in NOT_TABULAR:
        return None, "não é dado tabular"
    return None, f"extensão não reconhecida ({ext or 'sem extensão'})"


def _suffix_pattern(name: str) -> str:
    base = posixpath.basename(name).lower()
    _, ext, compression = _split_ext(base)
    return f"*{ext}{compression or ''}"


def _pattern_format(pattern: str) -> str:
    fmt, _ = classify(f"x{pattern.lstrip('*')}")
    if fmt is None:
        raise ValueError(f"padrão sem formato suportado: {pattern}")
    return fmt


class _Names:
    def __init__(self, reserved: set[str]) -> None:
        self.used = set(reserved)

    def take(self, *parts: str) -> str:
        base = normalize_identifier("_".join(p for p in parts if p))
        if not base[0].isalpha():
            base = f"t_{base}"[:MAX_IDENT]
        name, n = base, 1
        while name in self.used:
            n += 1
            suffix = f"_{n}"
            name = base[: MAX_IDENT - len(suffix)] + suffix
        self.used.add(name)
        return name


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class InboxScanner:
    def __init__(self, settings: Settings, reserved: set[str]) -> None:
        self.settings = settings
        self.rel_root = settings.inbox_path.strip("/")
        self.root = resolve_uri(settings.landing_uri, self.rel_root)
        self.fs, _, _ = fsspec.get_fs_token_paths(self.root)
        self.names = _Names(reserved)
        self.reserved = reserved
        self.specs: list[dict[str, Any]] = []
        self.ignored: list[dict[str, str]] = []
        self.errors: list[dict[str, str]] = []
        self.local = "file" in (
            self.fs.protocol if isinstance(self.fs.protocol, tuple) else (self.fs.protocol,)
        )

    def scan(self) -> None:
        root = self.fs._strip_protocol(self.root)
        if not self.fs.exists(root):
            return
        for entry in sorted(self.fs.ls(root, detail=True), key=lambda e: e["name"]):
            path = entry["name"]
            base = posixpath.basename(path.rstrip("/"))
            if not accepts(base, ["*"], DEFAULT_EXCLUDE):
                continue
            if GLOB_CHARS & set(base):
                self._ignore(path, "nome com * ? [ ] { }: renomeie o arquivo ou a pasta")
                continue
            try:
                if entry["type"] == "directory":
                    self._folder(path, base)
                else:
                    self._loose(path, base)
            except Exception as exc:
                self.errors.append({"path": path, "reason": f"{type(exc).__name__}: {exc}"})

    def _ignore(self, path: str, reason: str) -> None:
        self.ignored.append({"path": path, "reason": reason})
        log.warning("arquivo ignorado na inbox", extra={"file": path, "reason": reason})

    def _base_spec(self, name: str, rel: str) -> dict[str, Any]:
        return {
            "name": name,
            "description": f"Descoberta automática: {rel}",
            "owner": "inbox",
            "tags": ["auto", "inbox"],
        }

    def _file_spec(self, name: str, rel: str, fmt: str, **file_opts: Any) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "path": rel,
            "format": fmt,
            "min_age_seconds": self.settings.inbox_settle_seconds,
            "flatten_max_level": AUTO_FLATTEN_LEVEL,
        }
        if fmt == "csv":
            opts.update(sep="auto", encoding="auto")
        if fmt in {"jsonl", "json"}:
            opts["encoding"] = "auto"
        if fmt == "json":
            opts["records_path"] = "auto"
        opts.update(file_opts)
        return {
            **self._base_spec(name, rel),
            "kind": "file",
            "load_strategy": "append",
            "file": opts,
        }

    def _zip_formats(self, path: str) -> Counter[str]:
        with self.fs.open(path, "rb") as raw, zipfile.ZipFile(raw) as zf:
            formats: Counter[str] = Counter()
            for member in zf.namelist():
                if member.endswith("/") or not accepts(member, ["*"], DEFAULT_EXCLUDE):
                    continue
                fmt, _ = classify(member)
                if fmt and fmt not in {"zip", "sqlite"}:
                    formats[_suffix_pattern(member)] += 1
            return formats

    def _too_recent(self, path: str) -> bool:
        settle = self.settings.inbox_settle_seconds
        if not settle:
            return False
        modified = _modified_epoch(self.fs.info(path))
        return modified is not None and time.time() - modified < settle

    def _loose(self, path: str, base: str) -> None:
        rel = f"{self.rel_root}/{base}"
        fmt, reason = classify(base)
        stem = _split_ext(base)[0]
        handlers = {"sqlite": self._loose_sqlite, "zip": self._loose_zip, "xlsx": self._loose_xlsx}
        if fmt is None:
            self._ignore(path, reason or "não suportado")
        elif fmt in handlers:
            handlers[fmt](path, rel, stem)
        else:
            self.specs.append(self._file_spec(self.names.take(stem), rel, fmt))

    def _loose_sqlite(self, path: str, rel: str, stem: str) -> None:
        self._sqlite(path, stem)

    def _loose_zip(self, path: str, rel: str, stem: str) -> None:
        patterns = self._zip_formats(path)
        if not patterns:
            self._ignore(path, "zip sem arquivos tabulares suportados")
            return
        by_format: dict[str, list[str]] = defaultdict(list)
        for pattern in patterns:
            by_format[_pattern_format(pattern)].append(pattern)
        multiple = len(by_format) > 1
        for member_fmt, member_patterns in sorted(by_format.items()):
            pattern = max(member_patterns, key=lambda p: patterns[p])
            name = self.names.take(stem, member_fmt if multiple else "")
            self.specs.append(self._file_spec(name, rel, member_fmt, zip_member_pattern=pattern))

    def _loose_xlsx(self, path: str, rel: str, stem: str) -> None:
        sheets = self._sheets(path)
        if not sheets:
            self._ignore(path, "Excel sem abas visíveis")
            return
        multiple = len(sheets) > 1
        for sheet in sheets:
            name = self.names.take(stem, sheet if multiple else "")
            self.specs.append(self._file_spec(name, rel, "xlsx", sheet_name=sheet))

    def _sheets(self, path: str) -> list[str]:
        with self.fs.open(path, "rb") as f, zipfile.ZipFile(f) as zf:
            root = fromstring(zf.read("xl/workbook.xml"))
        return [
            el.attrib["name"]
            for el in root.iter()
            if el.tag.rsplit("}", 1)[-1] == "sheet"
            and el.attrib.get("state", "visible") == "visible"
            and "name" in el.attrib
        ]

    def _sqlite(self, path: str, stem: str) -> None:
        if not self.local:
            self._ignore(path, "SQLite só é lido em disco local")
            return
        if self._too_recent(path):
            self._ignore(path, "arquivo ainda em gravação; será lido na próxima execução")
            return
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                    "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name"
                )
            ]
        if not tables:
            self._ignore(path, "banco SQLite sem tabelas")
            return
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            self.specs.append(
                {
                    **self._base_spec(
                        self.names.take(stem, table),
                        f"{self.rel_root}/{posixpath.basename(path)}:{table}",
                    ),
                    "kind": "sql",
                    "load_strategy": "full",
                    "sql": {"url": f"sqlite:///{uri}&uri=true", "query": f"SELECT * FROM {quoted}"},
                }
            )

    def _folder(self, path: str, base: str) -> None:
        rel = f"{self.rel_root}/{base}"
        sidecar = self._sidecar(path)
        if sidecar.get("enabled") is False:
            self._ignore(path, "pasta desabilitada no _source.yml")
            return
        groups: dict[str, list[str]] = defaultdict(list)
        zip_members: dict[str, Counter[str]] = defaultdict(Counter)
        for file in sorted(self.fs.find(path)):
            name = posixpath.basename(file)
            if not accepts(name, ["*"], DEFAULT_EXCLUDE):
                continue
            fmt, reason = classify(name)
            if fmt is None or fmt == "sqlite":
                self._ignore(file, reason or "SQLite deve ficar solto na raiz da inbox")
                continue
            if fmt == "zip":
                for pattern, count in self._zip_formats(file).items():
                    member_fmt = _pattern_format(pattern)
                    groups[member_fmt].append(file)
                    zip_members[member_fmt][pattern] += count
                continue
            groups[fmt].append(file)
        if not groups:
            self._ignore(path, "pasta sem arquivos suportados")
            return
        override_fmt = (sidecar.get("file") or {}).get("format")
        if override_fmt:
            merged = sorted({f for files in groups.values() for f in files})
            groups = {override_fmt: merged}
        multiple = len(groups) > 1
        for fmt, files in sorted(groups.items()):
            include = sorted({_suffix_pattern(f) for f in files})
            extra: dict[str, Any] = {"include": include}
            if zip_members.get(fmt):
                extra["zip_member_pattern"] = zip_members[fmt].most_common(1)[0][0]
            requested = sidecar.get("name") if not multiple else None
            if requested and requested in self.reserved:
                self.errors.append(
                    {"path": path, "reason": f"nome {requested!r} já existe no catálogo"}
                )
                return
            name = requested or self.names.take(base, fmt if multiple else "")
            self.names.used.add(name)
            spec = self._file_spec(name, rel, fmt, **extra)
            override = {k: v for k, v in sidecar.items() if k != "name"}
            self.specs.append(_deep_merge(spec, override) if override else spec)

    def _sidecar(self, path: str) -> dict[str, Any]:
        candidate = posixpath.join(path, SIDECAR)
        if not self.fs.exists(candidate):
            return {}
        with self.fs.open(candidate, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{candidate}: deve ser um mapeamento YAML")
        forbidden = {"kind"} & set(data)
        if forbidden:
            raise ValueError(
                f"{candidate}: campo não permitido no _source.yml: {sorted(forbidden)}"
            )
        return data


def resolve_catalog(settings: Settings, catalog_path: str | None = None) -> ResolvedCatalog:
    specs: list[dict[str, Any]] = []
    origins: dict[str, str] = {}
    for origin, path, active in (
        ("catalog", catalog_path or settings.catalog_path, True),
        ("examples", settings.examples_catalog_path, settings.examples_enabled),
    ):
        if not active:
            continue
        if origin == "examples" and not fsspec.filesystem("file").exists(str(path)):
            continue
        for spec in read_catalog_specs(path):
            specs.append(spec)
            if isinstance(spec, dict) and spec.get("name"):
                origins.setdefault(spec["name"], origin)

    base = Catalog.model_validate({"sources": specs})
    resolved = ResolvedCatalog(catalog=base, origins=origins)
    if not settings.inbox_enabled:
        return resolved

    reserved = {s.name for s in base.sources} | {s.table for s in base.sources}
    scanner = InboxScanner(settings, reserved)
    scanner.scan()
    resolved.ignored.extend(scanner.ignored)
    resolved.errors.extend(scanner.errors)

    discovered = []
    for spec in scanner.specs:
        try:
            discovered.append(_SOURCE_ADAPTER.validate_python(spec))
            origins[spec["name"]] = "inbox"
        except ValidationError as exc:
            resolved.errors.append({"path": spec["file"]["path"], "reason": str(exc)})
    if discovered:
        resolved.catalog = Catalog(sources=[*base.sources, *discovered])
    return resolved
