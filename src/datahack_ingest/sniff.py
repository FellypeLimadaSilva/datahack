from __future__ import annotations

import csv
import io
from collections import Counter
from typing import IO

import ijson
from defusedxml.ElementTree import iterparse

SAMPLE_BYTES = 1024 * 1024
DELIMITERS = (",", ";", "\t", "|")
_SNIFF_RECORDS = 50


def detect_encoding(sample: bytes) -> str:
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError as exc:
        if exc.reason == "unexpected end of data" and exc.start >= len(sample) - 3:
            return "utf-8"
    try:
        sample.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def decode_sample(sample: bytes, encoding: str) -> str:
    text = sample.decode(encoding, errors="replace")
    return text.lstrip("﻿")


def detect_delimiter(text: str, quotechar: str = '"') -> str:
    lines = text.splitlines(keepends=True)
    if len(lines) > 1 and not text.endswith(("\n", "\r")):
        lines = lines[:-1]
    body = "".join(lines[: _SNIFF_RECORDS * 4])
    best, best_score = ",", (0.0, 0)
    for delimiter in DELIMITERS:
        reader = csv.reader(io.StringIO(body), delimiter=delimiter, quotechar=quotechar)
        try:
            records = [r for _, r in zip(range(_SNIFF_RECORDS), reader, strict=False) if r]
        except csv.Error:
            continue
        if not records:
            continue
        width = len(records[0])
        if width < 2:
            continue
        consistent = sum(1 for r in records if len(r) == width) / len(records)
        score = (round(consistent, 2), width)
        if score > best_score:
            best, best_score = delimiter, score
    return best


def infer_xml_record_tag(f: IO[bytes], max_events: int = 50_000) -> str | None:
    counts: Counter[tuple[int, str]] = Counter()
    record_like: set[tuple[int, str]] = set()
    depth = -1
    root_children: Counter[str] = Counter()
    try:
        for n, (event, elem) in enumerate(iterparse(f, events=("start", "end"))):
            tag = elem.tag.rsplit("}", 1)[-1] if isinstance(elem.tag, str) else str(elem.tag)
            if event == "start":
                depth += 1
                continue
            key = (depth, tag)
            counts[key] += 1
            if len(elem) or elem.attrib:
                record_like.add(key)
            if depth == 1:
                root_children[tag] += 1
            depth -= 1
            if depth >= 1:
                elem.clear()
            if n >= max_events:
                break
    except Exception:
        if not counts:
            raise
    repeated = [
        (d, -c, t) for (d, t), c in counts.items() if d >= 1 and c >= 2 and (d, t) in record_like
    ]
    if repeated:
        return min(repeated)[2]
    if root_children:
        return root_children.most_common(1)[0][0]
    return None


def infer_json_records_path(f: IO[bytes], max_events: int = 200_000) -> tuple[bool, str | None]:
    previous: tuple[str, str] | None = None
    for n, (prefix, event, _) in enumerate(ijson.parse(f)):
        if n == 0 and event == "start_array":
            return True, None
        expected_item = f"{previous[0]}.item" if previous and previous[0] else "item"
        if (
            previous
            and previous[1] == "start_array"
            and event == "start_map"
            and prefix == expected_item
        ):
            return False, previous[0] or None
        previous = (prefix, event)
        if n >= max_events:
            break
    return False, None
