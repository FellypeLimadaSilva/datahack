import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from datahack_ingest.catalog import load_catalog
from datahack_ingest.extractors import ExtractState, build_extractor
from datahack_ingest.runner import RunResult, _prepare_frame

ROOT = Path(__file__).resolve().parents[2]
HEADER = {
    "NC": "Nível Territorial (Código)",
    "NN": "Nível Territorial",
    "MC": "Unidade de Medida (Código)",
    "MN": "Unidade de Medida",
    "V": "Valor",
    "D1C": "Município (Código)",
    "D1N": "Município",
    "D2C": "Variável (Código)",
    "D2N": "Variável",
    "D3C": "Ano (Código)",
    "D3N": "Ano",
    "D4C": "Sexo (Código)",
    "D4N": "Sexo",
    "D5C": "Idade (Código)",
    "D5N": "Idade",
    "D6C": "Forma de declaração da idade (Código)",
    "D6N": "Forma de declaração da idade",
}


def _row(code: str, name: str, age_code: str, age: str, value: str) -> dict:
    return {
        "NC": "6",
        "NN": "Município",
        "MC": "45",
        "MN": "Pessoas",
        "V": value,
        "D1C": code,
        "D1N": name,
        "D2C": "93",
        "D2N": "População residente",
        "D3C": "2022",
        "D3N": "2022",
        "D4C": "6794",
        "D4N": "Total",
        "D5C": age_code,
        "D5N": age,
        "D6C": "113635",
        "D6N": "Total",
    }


PAYLOAD = [
    HEADER,
    _row("5100102", "Acorizal - MT", "6575", "18 anos", "49"),
    _row("5100102", "Acorizal - MT", "6576", "19 anos", "41"),
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(PAYLOAD).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


@pytest.fixture
def sidra():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/values/t/9514"
    srv.shutdown()


def test_ibge_source_from_catalog_drops_header_and_renames(sidra):
    source = load_catalog(ROOT / "config" / "sources.yml").get("ibge_populacao_idade_mt")
    assert source.enabled
    assert "c287/6575,6576,6577,6578,6579,6580,6581" in source.api.url
    local = source.model_copy(update={"api": source.api.model_copy(update={"url": sidra})})
    result = RunResult(source=local.name, run_id="t")
    frames = [
        _prepare_frame(local, raw, result)
        for unit in build_extractor(local, "").units(ExtractState(strategy="full"))
        for raw in unit.frames
    ]
    rows = [r for f in frames for r in f.to_dict("records")]
    assert result.rows_filtered == 1
    assert rows == [
        {
            "co_municipio": "5100102",
            "no_municipio": "Acorizal - MT",
            "nu_ano": "2022",
            "co_idade": "6575",
            "idade": "18 anos",
            "qt_populacao": "49",
        },
        {
            "co_municipio": "5100102",
            "no_municipio": "Acorizal - MT",
            "nu_ano": "2022",
            "co_idade": "6576",
            "idade": "19 anos",
            "qt_populacao": "41",
        },
    ]
