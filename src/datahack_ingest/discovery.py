from __future__ import annotations

import logging
import posixpath
import re
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
ROOT_OVERRIDES = "_sources.yml"
DOC_NAME = re.compile(
    r"dicion|leia[\s_-]?me|readme|manual|layout|nota[\s_-]?t[eé]cnica|questionari|instruc"
)
YEAR = re.compile(r"(?<![0-9])(19|20)[0-9]{2}(?![0-9])")
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


def is_documentation(name: str) -> bool:
    return bool(DOC_NAME.search(posixpath.basename(name).lower()))


def family(name: str) -> str:
    stem = _split_ext(posixpath.basename(name.rstrip("/")))[0]
    stripped = YEAR.sub(" ", stem)
    if not re.search(r"[A-Za-z]", stripped):
        stripped = stem
    return normalize_identifier(stripped)


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
        loose: list[tuple[str, str]] = []
        for entry in sorted(self.fs.ls(root, detail=True), key=lambda e: e["name"]):
            path = entry["name"]
            base = posixpath.basename(path.rstrip("/"))
            if not accepts(base, ["*"], DEFAULT_EXCLUDE):
                continue
            if GLOB_CHARS & set(base):
                self._ignore(path, "nome com * ? [ ] { }: renomeie o arquivo ou a pasta")
                continue
            if entry["type"] == "directory":
                self._guard(path, self._folder, path, base)
            else:
                loose.append((path, base))
        first = len(self.specs)
        self._loose(loose)
        self._apply_root_overrides(root, first)

    def _apply_root_overrides(self, root: str, first: int) -> None:
        candidate = posixpath.join(root, ROOT_OVERRIDES)
        if not self.fs.exists(candidate):
            return
        with self.fs.open(candidate, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
            self.errors.append(
                {
                    "path": candidate,
                    "reason": "deve mapear nome da fonte para campos a sobrescrever",
                }
            )
            return
        loose = {spec["name"]: i for i, spec in enumerate(self.specs) if i >= first}
        for name, override in data.items():
            if name not in loose:
                self.errors.append(
                    {
                        "path": candidate,
                        "reason": f"fonte {name!r} não encontrada entre os arquivos soltos",
                    }
                )
                continue
            if {"kind", "name"} & set(override):
                self.errors.append(
                    {"path": candidate, "reason": f"{name}: kind e name não podem mudar"}
                )
                continue
            self.specs[loose[name]] = _deep_merge(self.specs[loose[name]], override)

    def _guard(self, path: str, fn, *args) -> None:
        try:
            fn(*args)
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
            opts.update(sep="auto", encoding="auto", skip_rows="auto")
        if fmt == "xlsx":
            opts.update(skip_rows="auto", drop_note_rows=True, sheet_name="auto")
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

    def _zip_members(self, path: str) -> list[tuple[str, str]]:
        with self.fs.open(path, "rb") as raw, zipfile.ZipFile(raw) as zf:
            names = zf.namelist()
        members = []
        for member in names:
            if member.endswith("/") or not accepts(member, ["*"], DEFAULT_EXCLUDE):
                continue
            fmt, _ = classify(member)
            if fmt in {None, "zip", "sqlite"}:
                continue
            if is_documentation(member):
                self._ignore(f"{path}!{member}", "documentação (dicionário, leia-me, manual)")
                continue
            members.append((member, fmt))
        return members

    def _zip_formats(self, path: str) -> Counter[str]:
        return Counter(_suffix_pattern(m) for m, _ in self._zip_members(path))

    def _too_recent(self, path: str) -> bool:
        settle = self.settings.inbox_settle_seconds
        if not settle:
            return False
        modified = _modified_epoch(self.fs.info(path))
        return modified is not None and time.time() - modified < settle

    def _loose(self, entries: list[tuple[str, str]]) -> None:
        groups: dict[tuple[str, str], dict[str, Any]] = {}

        def group(fmt: str, name: str) -> dict[str, Any]:
            return groups.setdefault(
                (fmt, family(name)), {"files": set(), "members": set(), "paths": []}
            )

        for path, base in entries:
            fmt, reason = classify(base)
            if fmt is None:
                self._ignore(path, reason or "não suportado")
            elif is_documentation(base):
                self._ignore(path, "documentação (dicionário, leia-me, manual)")
            elif fmt == "sqlite":
                self._guard(path, self._sqlite, path, _split_ext(base)[0])
            elif fmt == "zip":
                try:
                    members = self._zip_members(path)
                except Exception as exc:
                    self.errors.append({"path": path, "reason": f"{type(exc).__name__}: {exc}"})
                    continue
                if not members:
                    self._ignore(path, "zip sem arquivos tabulares suportados")
                for member, member_fmt in members:
                    g = group(member_fmt, member)
                    g["files"].add(base)
                    g["members"].add(member)
                    g["paths"].append(path)
            else:
                g = group(fmt, base)
                g["files"].add(base)
                g["paths"].append(path)

        for (fmt, fam), g in sorted(groups.items()):
            self._guard(g["paths"][0], self._loose_group, fmt, fam, g)

    def _loose_group(self, fmt: str, fam: str, g: dict[str, Any]) -> None:
        files = sorted(g["files"])
        extra: dict[str, Any] = {"include": files, "recursive": False}
        if g["members"]:
            extra["zip_members"] = sorted(g["members"])
        rel = self.rel_root
        if fmt == "xlsx" and len(files) == 1 and not g["members"]:
            sheets = self._sheets(g["paths"][0])
            if not sheets:
                self._ignore(g["paths"][0], "Excel sem abas visíveis")
                return
            if len(sheets) > 1:
                for sheet in sheets:
                    name = self.names.take(fam, sheet)
                    self.specs.append(self._file_spec(name, rel, fmt, sheet_name=sheet, **extra))
                return
            extra["sheet_name"] = sheets[0]
        self.specs.append(self._file_spec(self.names.take(fam), rel, fmt, **extra))

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
            if is_documentation(name):
                self._ignore(file, "documentação (dicionário, leia-me, manual)")
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
