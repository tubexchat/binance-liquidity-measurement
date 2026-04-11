"""Symbol selection / resolution for all bliq subcommands.

M1 supports: explicit list, from-file (YAML or newline text), or a stubbed
"all" branch placeholder. The `--top N` branch is defined here but raises
until M2 ships the 24h ticker fetch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bliq.infra.errors import ConfigError


@dataclass
class SymbolSelection:
    explicit: list[str] = field(default_factory=list)
    all_symbols: bool = False
    top_n: int | None = None
    from_file: Path | None = None


def _load_file(path: Path) -> list[str]:
    if not path.exists():
        raise ConfigError(f"symbols file not found: {path}")
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
        if isinstance(data, list):
            return [str(s).strip() for s in data if str(s).strip()]
        if isinstance(data, dict) and "symbols" in data:
            return [str(s).strip() for s in data["symbols"] if str(s).strip()]
        raise ConfigError(f"unexpected YAML shape in {path}")
    # plain text: one symbol per line, '#' for comments
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.split("#", 1)[0].strip()
        if stripped:
            out.append(stripped)
    return out


def resolve_symbols(sel: SymbolSelection) -> list[str]:
    if sel.explicit:
        return list(sel.explicit)
    if sel.from_file is not None:
        return _load_file(sel.from_file)
    if sel.top_n is not None:
        raise ConfigError("--top is not available in M1 (arrives in M2)")
    if sel.all_symbols:
        raise ConfigError("--all is not available in M1 (arrives in M2)")
    raise ConfigError("no symbol selection provided")
