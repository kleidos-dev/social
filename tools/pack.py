# SPDX-License-Identifier: MIT
"""The pack's one data file, and where everything is.

``pack.json`` lists every image: the source it is drawn from, the PNG files it
is given and the platform rule each file answers to; then the repository
cards, what is not made, and the previews. Nothing else says what the pack
holds: the exporter, the checks and the README's tables all read it.

This module also puts ``brand/tools`` on the path, so every other module of
``tools/`` imports it first and then ``kleidos_brand``: both repositories draw
with brand's rules, brand's browser and brand's encoder.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: This repository.
ROOT = Path(__file__).resolve().parents[1]
#: The brand repository, as a submodule.
BRAND = Path("brand")

if not (ROOT / BRAND / "tools" / "kleidos_brand").is_dir():
    sys.exit("the brand submodule is not checked out: run 'git submodule update --init'"
             " (for a local brand beside this clone: 'git config submodule.brand.url ../brand',"
             " then 'git -c protocol.file.allow=always submodule update --init')")
sys.path.insert(0, str(ROOT / BRAND / "tools"))

PACK_JSON = Path("pack.json")
EXPORTS_JSON = Path("exports.json")
README = Path("README.md")
SRC_DIR = Path("src")
PNG_DIR = Path("png")
PREVIEWS_DIR = Path("previews")

#: The brand files every image here is drawn from, relative to the brand repository.
BRAND_INPUTS = (
    Path("logo/src/mark.svg"),
    Path("logo/src/lockups.json"),
    Path("tokens/tokens.json"),
    Path("fonts/mona-sans/MonaSansVF[wdth,opsz,wght].ttf"),
    Path("fonts/mona-sans/MonaSansMonoVF[wght].ttf"),
    Path("tools/kleidos_brand/meta.py"),  # the metadata profile every picture carries
)


def brand_root(root: Path = ROOT) -> Path:
    """Return the brand repository of the tree at *root*."""
    return root / BRAND


@dataclass(frozen=True)
class Output:
    """One PNG of an image: its path, its pixels and the platform rule it answers to."""

    file: Path
    px: tuple[int, int]
    rule: str


@dataclass(frozen=True)
class Image:
    """One image of the pack: its source and the files drawn from it."""

    source: Path
    what: str
    outputs: tuple[Output, ...]
    mark_alone: dict[str, Any] | None


@dataclass(frozen=True)
class Row:
    """One repository's card: its name as GitHub writes it, its label, its line and its motif."""

    repo: str
    label: str
    line: str
    lines: tuple[str, ...]
    motif: str
    file: Path | None  # None for the template row, which is drawn into a preview only


def load(root: Path = ROOT) -> dict[str, Any]:
    """Return ``pack.json`` of the tree at *root*."""
    return json.loads((root / PACK_JSON).read_text(encoding="utf-8"))


def images(data: dict[str, Any]) -> list[Image]:
    """Return the profile images, in file order."""
    return [
        Image(
            Path(entry["source"]),
            entry["what"],
            tuple(Output(Path(out["file"]), (out["px"][0], out["px"][1]), out["rule"]) for out in entry["outputs"]),
            entry.get("mark_alone"),
        )
        for entry in data["images"]
    ]


def _row(entry: dict[str, Any]) -> Row:
    return Row(entry["repo"], entry["label"], entry["line"], tuple(entry["lines"]), entry["motif"],
               Path(entry["file"]) if "file" in entry else None)


def rows(data: dict[str, Any]) -> list[Row]:
    """Return the repositories' cards, in file order."""
    return [_row(entry) for entry in data["cards"]["repos"]]


def template_row(data: dict[str, Any]) -> Row:
    """Return the placeholder row the empty card system is looked at with."""
    return _row(data["cards"]["template_row"])


def card_size(data: dict[str, Any]) -> tuple[int, int]:
    """Return a card's pixels."""
    width, height = data["cards"]["px"]
    return width, height


def limit(data: dict[str, Any], rule: str) -> int:
    """Return the byte limit of a platform rule: a file must weigh less."""
    return int(data["rules"][rule]["max_bytes"])
