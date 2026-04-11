from pathlib import Path

import pytest
import yaml

from bliq.data.symbols import SymbolSelection, resolve_symbols
from bliq.infra.errors import ConfigError


def test_explicit_list():
    out = resolve_symbols(
        SymbolSelection(explicit=["BTCUSDT", "ETHUSDT"])
    )
    assert out == ["BTCUSDT", "ETHUSDT"]


def test_from_file_yaml_list(tmp_path: Path):
    f = tmp_path / "symbols.yaml"
    yaml.safe_dump({"symbols": ["BTCUSDT", "SOLUSDT"]}, f.open("w"))
    out = resolve_symbols(SymbolSelection(from_file=f))
    assert out == ["BTCUSDT", "SOLUSDT"]


def test_from_file_plain_text(tmp_path: Path):
    f = tmp_path / "symbols.txt"
    f.write_text("BTCUSDT\n# comment\nETHUSDT\n\n")
    out = resolve_symbols(SymbolSelection(from_file=f))
    assert out == ["BTCUSDT", "ETHUSDT"]


def test_no_selection_raises():
    with pytest.raises(ConfigError, match="no symbol selection"):
        resolve_symbols(SymbolSelection())


def test_top_n_requires_m2(tmp_path: Path):
    with pytest.raises(ConfigError, match="--top is not available in M1"):
        resolve_symbols(SymbolSelection(top_n=50))
