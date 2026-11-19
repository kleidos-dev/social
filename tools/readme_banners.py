# SPDX-License-Identifier: MIT
"""The README banners: the repository card laid out again as a wide strip, one per repository.

``src/readme/banner.svg`` is the banner system, the card's parts at the
card's scale on a 2560 x 800 canvas: the lockup, a hairline and the label in
capitals; the repository's name; its line in one or two lines; the ruled
shelf; the repository's motif standing on it (``src/cards/motifs/``, as the
card has it). A banner row (``readme_banners.repos`` in ``pack.json``) takes
its label, its line and its motif from the repository's card row and adds
only the line's break into one or two lines; a repository with no card yet
carries its own.

Each row is published as two SVG files, words as outlines, no script, no
style sheet, no font, published 1280 x 400:

- ``banner-dark.svg``, the ``page`` skin: no ground, for GitHub's dark page;
- ``banner-light.svg``, the ``tile`` skin: the same drawing on the stage
  ground with rounded corners, brand's answer for a light page (its color
  mark holds on white only from 48 px, and a phone shows this mark at 24).

The boards banner's nine panels carry their unlock screens as inner PNGs,
pixels only, at each panel's active area. Every file carries brand's SVG
metadata block (``kleidos_brand.meta.svg_stamp``) written from its record
(``records.readme_banner``). No browser draws them, so the exporter and CI
hold them byte for byte.
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cards
import pack
import records
import source
import sync_readme_banners as sync
from kleidos_brand import SVG_HEADER, boards, lettering, meta

#: This repository's own row: its README shows its banner from its masters, written by the exporter.
REPO = "social"
#: The canvas a banner is drawn on (the card's units) and the size it is published at.
CANVAS = (2560, 800)
PUBLISHED = (1280, 400)
MAX_LINES = 2
#: The widths a README shows a banner at: a computer and a 360 px phone (measured, the rule's notes).
WIDE_PX = 823
NARROW_PX = 279
MIN_MARK_PX = 24.0  # the mark box on a phone: brand's floor on a dark ground
MIN_TITLE_PX = 12.0  # the title's capitals on a phone
MIN_LINE_PX = 9.0  # the line's x-height on a computer
MIN_LABEL_PX = 12.0  # the label's capitals on a computer
#: The tile skin's corner, ``web.radius.r-xl`` (28 px at the published size).
TILE_RADIUS = 56
SKINS = ("page", "tile")
#: A banner's copy lands where no TRADEMARKS.md is, so its header names the public one.
TRADEMARKS_URL = f"https://github.com/{sync.OWNER}/social/blob/main/TRADEMARKS.md"
HEADER = SVG_HEADER.replace("version 3: TRADEMARKS.md", f"version 3: {TRADEMARKS_URL}")


@dataclass(frozen=True)
class Row:
    """One repository's banner: its name as GitHub writes it, its label, its line, the lines it breaks into, its motif."""

    repo: str
    name: str
    label: str
    line: str
    lines: tuple[str, ...]
    motif: str
    mode: str
    card: bool


@dataclass
class Banner:
    """One published banner file, ready to write, and what it was made from."""

    row: Row
    theme: str
    skin: str
    path: Path
    drawing: source.Drawing
    svg: str
    record: Any
    slug: str
    inputs: tuple[Path, ...]


def section(data: dict[str, Any]) -> dict[str, Any]:
    """Return the banners' section of ``pack.json``."""
    return data["readme_banners"]


def rows(data: dict[str, Any]) -> list[Row]:
    """Return every banner row, in file order, its words filled in from its card row."""
    return [Row(entry["repo"], entry["name"], entry["label"] or "", entry["line"] or "", tuple(entry["lines"]),
                entry["motif"] or "", entry["mode"], entry["card"]) for entry in sync.rows(data)]


def template(data: dict[str, Any]) -> Path:
    """Return the banner template's path, relative to the repository."""
    return Path(section(data)["template"])


def path_of(data: dict[str, Any], row: Row, theme: str) -> Path:
    """Return the master of *row* for *theme*, relative to the repository."""
    return Path(sync.master(data, {"name": row.name}, theme))


def slug_of(row: Row, theme: str) -> str:
    """Return the id prefix of a banner's title, description and metadata, unlike the profile banner's ``kl-banner-*``."""
    return f"kl-readme-{row.name}-{theme}"


def compose(root: Path, data: dict[str, Any], row: Row, skin: str) -> ET.Element:
    """Return the banner of *row*: the template with the row's words, its motif and its skin."""
    if skin not in SKINS:
        raise ValueError(f"pack.json: a banner's skin is {' or '.join(SKINS)}, not {skin!r}")
    tree = source.parse(root / template(data))
    named = source.by_id(tree)
    source.set_words(named["label"], row.label)
    source.set_words(named["title"], row.repo)
    targets = [named[f"line.{index}"] for index in range(MAX_LINES)]
    if not 1 <= len(row.lines) <= len(targets):
        raise ValueError(f"the banner of {row.repo}: its line has {len(row.lines)} lines and a banner has room for one or {len(targets)}")
    for index, target in enumerate(targets):
        if index < len(row.lines):
            source.set_words(target, row.lines[index])
        else:
            source.remove(tree, target)
    holder = named["motif"]
    for child in list(holder):
        holder.remove(child)
    holder.extend(cards.motif_shapes(root, data, row.motif))
    ground = named["ground"]
    if skin == "page":
        tree.remove(ground)
    else:
        for rect in ground:
            rect.set("rx", str(TILE_RADIUS))
    return tree


def screens(root: Path, drawing: source.Drawing) -> list[ET.Element]:
    """Return each board's unlock screen as an inner PNG on its panel's active area: pixels only, no metadata."""
    brand = pack.brand_root(root)
    out = []
    for placed in drawing.fronts:
        left, top, right, bottom = placed.glass()
        pixels = meta.png_bare((brand / boards.screen_path(placed.slug)).read_bytes())
        out.append(ET.Element(f"{{{source.SVG_NS}}}image", {
            "x": _number(left), "y": _number(top), "width": _number(right - left), "height": _number(bottom - top),
            "preserveAspectRatio": "none", "href": "data:image/png;base64," + base64.b64encode(pixels).decode("ascii"),
        }))
    return out


def _number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def published(root: Path, tree: ET.Element, drawing: source.Drawing) -> str:
    """Return the outlined tree as the published file is, before its metadata: the screens on, the published size, the header's address."""
    if drawing.fronts:
        content = source.by_id(tree)["content"]
        content.extend(screens(root, drawing))
    tree.set("width", str(PUBLISHED[0]))
    tree.set("height", str(PUBLISHED[1]))
    ET.indent(tree, "  ")
    return HEADER + ET.tostring(tree, encoding="unicode") + "\n"


def banner(root: Path, data: dict[str, Any], row: Row, theme: str) -> Banner:
    """Return the banner of *row* for *theme*, ready to write."""
    skin = section(data)["themes"][theme]
    tree = compose(root, data, row, skin)
    path = path_of(data, row, theme)
    drawing = source.ready(tree, pack.brand_root(root), path.as_posix())
    described = records.readme_banner(root, data, row, theme, path, bool(drawing.fronts))
    slug = slug_of(row, theme)
    svg = meta.svg_stamp(published(root, tree, drawing), described, slug)
    inputs = (template(data), cards.motif_path(data, row.motif), pack.PACK_JSON)
    return Banner(row, theme, skin, path, drawing, svg, described, slug, inputs)


def banners(root: Path, data: dict[str, Any]) -> list[Banner]:
    """Return every banner, row by row and theme by theme."""
    return [banner(root, data, row, theme) for row in rows(data) for theme in sync.THEMES]


# --- Checks ------------------------------------------------------------------------------


def row_findings(data: dict[str, Any]) -> list[str]:
    """Return what is wrong with the banner rows: a repository twice, lines that do not spell the line, words typed twice."""
    found = []
    try:
        listed = section(data)
    except KeyError:
        return ["pack.json: has no readme_banners section"]
    if set(listed.get("themes", {})) != set(sync.THEMES) or not set(listed["themes"].values()) <= set(SKINS):
        found.append(f"pack.json: the banners' themes are {', '.join(sync.THEMES)}, each with a skin of {', '.join(SKINS)}")
    card_rows = {entry["repo"]: entry for entry in data["cards"]["repos"]}
    seen: set[str] = set()
    for entry in listed["repos"]:
        repo = entry.get("repo", "?")
        if repo in seen:
            found.append(f"pack.json: the repository {repo} is given two banners")
        seen.add(repo)
        if entry.get("mode", "copy") not in sync.MODES:
            found.append(f"pack.json: the banner of {repo} has the mode {entry.get('mode')!r}; a banner's mode is {', '.join(sync.MODES)}")
        if repo in card_rows:
            repeated = [key for key in ("label", "line", "motif") if key in entry]
            if repeated:
                found.append(f"pack.json: the banner of {repo} repeats its card row's {', '.join(repeated)}; a banner takes them from the card")
        else:
            missing = [key for key in ("label", "line", "motif") if not entry.get(key)]
            if missing:
                found.append(f"pack.json: the banner of {repo} has no card to take its {', '.join(missing)} from, and gives none")
    for row in rows(data):
        if " ".join(row.lines) != row.line:
            found.append(f"pack.json: the lines of the banner of {row.repo} do not join into its line")
        if not 1 <= len(row.lines) <= MAX_LINES:
            found.append(f"pack.json: the banner of {row.repo} has {len(row.lines)} lines; a banner has one or {MAX_LINES}")
    rule = data["rules"].get(listed.get("rule", ""))
    if rule is None or list(rule["upload_px"]) != list(PUBLISHED):
        found.append(f"pack.json: a banner answers to a rule of {PUBLISHED[0]} x {PUBLISHED[1]}")
    return found


def banner_findings(root: Path, built: Banner) -> list[str]:
    """Return what in one banner breaks the system: something outside its place, or too small to read where a README shows it."""
    drawing, row = built.drawing, built.row
    found = source.keep_findings(drawing)
    column, motif_box = drawing.guides.get("column"), drawing.guides.get("motif-box")
    if column is None or motif_box is None:
        return [*found, f"{drawing.name}: the template has no 'column' or 'motif-box' guide"]
    if drawing.size != CANVAS:
        found.append(f"{drawing.name}: is drawn on {drawing.size[0]} x {drawing.size[1]}; a banner is {CANVAS[0]} x {CANVAS[1]}")
    for name, placed in drawing.words.items():
        if name != "label" and not source.inside(placed.box(), column):
            found.append(f"{drawing.name}: the words {name!r} ({placed.line.text!r}) reach outside the text column, toward the motif")
    if drawing.motif is None:
        found.append(f"{drawing.name}: has no motif")
    else:
        if not source.inside(drawing.motif, motif_box):
            found.append(f"{drawing.name}: its motif {row.motif!r} reaches outside the motif's box")
        line = source.by_id(source.parse(root / built.inputs[0])).get("shelf")
        if line is not None:
            top = float(line.get("y1", "0")) - float(line.get("stroke-width", "0")) / 2
            if abs(drawing.motif[3] - top) > 0.01:
                found.append(f"{drawing.name}: its motif does not stand on the shelf (its lowest edge is at {drawing.motif[3]:.1f}, the shelf's top at {top:.1f})")
    brand = pack.brand_root(root)
    for name, width, least, part, what in (
        ("title", NARROW_PX, MIN_TITLE_PX, "sCapHeight", "the title's capitals"),
        ("line.0", WIDE_PX, MIN_LINE_PX, "sxHeight", "the line's x-height"),
        ("label", WIDE_PX, MIN_LABEL_PX, "sCapHeight", "the label's capitals"),
    ):
        placed = drawing.words.get(name)
        if placed is None:
            found.append(f"{drawing.name}: has no {name!r}")
            continue
        font, _ = lettering._instance(brand, placed.line.family, placed.line.axes)  # noqa: SLF001
        height = float(getattr(font["OS/2"], part)) * placed.scale * width / drawing.size[0]
        if height < least:
            found.append(f"{drawing.name}: at {width} px wide {what} are {height:.1f} px high; the least is {least:.0f}")
    if drawing.lockup is None:
        found.append(f"{drawing.name}: has no lockup")
    else:
        mark_box = (drawing.lockup[3] - drawing.lockup[1]) * NARROW_PX / drawing.size[0]
        if mark_box < MIN_MARK_PX:
            found.append(f"{drawing.name}: at {NARROW_PX} px wide the mark is {mark_box:.1f} px; the least is {MIN_MARK_PX:.0f}")
    if (built.skin == "page") != (drawing.ground is None):
        found.append(f"{drawing.name}: the {built.skin} skin {'has no' if built.skin == 'page' else 'needs a'} ground")
    return found


def pair_findings(pair: list[Banner]) -> list[str]:
    """Return a difference between a row's two files other than the ground the tile adds and their own records."""
    texts = {}
    for built in pair:
        text = built.svg
        start = text.index(f'<title id="{built.slug}-t">')
        end = text.index(meta.SVG_IGNORE_END) + len(meta.SVG_IGNORE_END)
        text = (text[:start] + text[end:]).replace(built.slug, "slug")
        if built.skin == "tile":
            begin = text.find('<g id="ground">')
            close = text.find("</g>", begin) + len("</g>")
            text = text[:begin].rstrip(" ") + text[close:].lstrip("\n") if begin >= 0 else text
        texts[built.skin] = text
    if set(texts) != set(SKINS) or texts["page"] != texts["tile"]:
        return [f"{pair[0].path.parent}: the light file is not the dark file plus its ground"]
    return []
