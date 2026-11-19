# SPDX-License-Identifier: MIT
"""The repository cards: one template, one row of ``pack.json`` and one motif per repository.

``src/cards/card.svg`` is the card system: the lockup, a hairline and a label
in capitals, the repository's name as GitHub writes it, one line in two or
three short lines, a ruled shelf, and a motif standing on it. A card differs
from another in its row's words and in its motif, nothing else, so every
repository's preview is one picture family.

A motif (``src/cards/motifs/<name>.svg``) is a small source of its own, 800 by
480, drawn in the mark's line language: a 12 px line in the signal color with
round caps and joins (8 px for a fine detail), fills from the social palette,
ink for a detail. It stands on its bottom edge, which is the shelf. One motif
is real things rather than line drawings: ``shelf``, the boards repository's,
holds brand's board fronts at one true scale (``kleidos_brand.boards``), on
two rows; the upper row stands on a shelf of its own, drawn as the card's
shelf is (4 px, the rule color).
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pack
import source
from kleidos_brand import lettering, tokens

#: A motif's canvas.
MOTIF_SIZE = (800, 480)
#: What a motif is drawn with.
MOTIF_ELEMENTS = frozenset({"g", "rect", "circle", "line", "path", "text"})
MOTIF_LINES = (12.0, 8.0)
MOTIF_FILLS = ("ground", "ink", "ink-2", "signal", "select")
MOTIF_STROKES = ("signal", "ink")
#: A shelf inside a motif, for a second row of boards: a level line drawn as the card's own shelf.
MOTIF_SHELF = ("rule", 4.0)

#: The most lines a card's line breaks into.
MAX_LINES = 3
#: What a card must still show at this width, the size a chat or a search result gives it.
SMALL_WIDTH = 400
MIN_TITLE_PX = 20.0  # the height of the title's capitals
MIN_LINE_PX = 6.0  # the x-height of the line
MIN_MARK_PX = 24.0  # the mark box
#: The narrowest a page shows a card. The title and the mark hold their floors there; the line need not.
NARROW_WIDTH = 320


@dataclass
class Card:
    """One card ready to draw, and the row it was written from."""

    row: pack.Row
    drawing: source.Drawing
    inputs: tuple[Path, ...]


def template(root: Path, data: dict[str, Any]) -> Path:
    """Return the card template's path, relative to *root*."""
    return Path(data["cards"]["template"])


def motif_path(data: dict[str, Any], name: str) -> Path:
    """Return a motif's path, relative to the repository."""
    return Path(data["cards"]["motifs"]) / f"{name}.svg"


def motif_shapes(root: Path, data: dict[str, Any], name: str) -> list[ET.Element]:
    """Return the shapes of the motif *name*."""
    tree = source.parse(root / motif_path(data, name))
    holder = source.by_id(tree).get("motif")
    if holder is None:
        raise ValueError(f"{motif_path(data, name)}: has no <g id=\"motif\">")
    return [copy.deepcopy(child) for child in holder]


def compose(root: Path, data: dict[str, Any], row: pack.Row) -> ET.Element:
    """Return the card of *row*: the template with the row's words and its motif in place."""
    tree = source.parse(root / template(root, data))
    named = source.by_id(tree)
    source.set_words(named["label"], row.label)
    source.set_words(named["title"], row.repo)
    targets = [named[f"line.{index}"] for index in range(MAX_LINES)]
    if len(row.lines) > len(targets):
        raise ValueError(f"the card of {row.repo}: its line has {len(row.lines)} lines and a card has room for {len(targets)}")
    for index, target in enumerate(targets):
        if index < len(row.lines):
            source.set_words(target, row.lines[index])
        else:
            source.remove(tree, target)
    holder = named["motif"]
    for child in list(holder):
        holder.remove(child)
    holder.extend(motif_shapes(root, data, row.motif))
    return tree


def card(root: Path, data: dict[str, Any], row: pack.Row) -> Card:
    """Return the card of *row*, ready to draw."""
    drawing = source.ready(compose(root, data, row), pack.brand_root(root), f"the card of {row.repo}")
    return Card(row, drawing, (template(root, data), motif_path(data, row.motif), pack.PACK_JSON))


def cards(root: Path, data: dict[str, Any]) -> list[Card]:
    """Return every repository's card, in the order ``pack.json`` lists them."""
    return [card(root, data, row) for row in pack.rows(data)]


# --- Checks ------------------------------------------------------------------------------


def row_findings(data: dict[str, Any]) -> list[str]:
    """Return what is wrong with the rows themselves: a name twice, a line that its lines do not spell."""
    found = []
    seen: dict[str, str] = {}
    for row in [*pack.rows(data), pack.template_row(data)]:
        if " ".join(row.lines) != row.line:
            found.append(f"pack.json: the lines of the card of {row.repo} do not join into its line")
        if not 1 <= len(row.lines) <= MAX_LINES:
            found.append(f"pack.json: the card of {row.repo} has {len(row.lines)} lines; a card has one to {MAX_LINES}")
        if row.label != row.label.strip() or not row.label:
            found.append(f"pack.json: the card of {row.repo} has no label")
    for row in pack.rows(data):
        for key, value in (("repository", row.repo), ("file", str(row.file))):
            if value in seen:
                found.append(f"pack.json: the {key} {value} is given to two cards")
            seen[value] = row.repo
        expected = pack.PNG_DIR / "github" / f"{row.repo.replace('.', 'dot-') if row.repo.startswith('.') else row.repo}.png"
        if row.file != expected:
            found.append(f"pack.json: the card of {row.repo} is written to {row.file}; a card's file is {expected}")
    return found


def motif_findings(root: Path, data: dict[str, Any]) -> list[str]:
    """Return what in a motif is not the motifs' line language, or does not stand on the shelf."""
    values = tokens.resolve(tokens.load(pack.brand_root(root)))
    fills = {values[f"social.{name}"] for name in MOTIF_FILLS}
    strokes = {values[f"social.{name}"] for name in MOTIF_STROKES}
    shelf_ink = values[f"social.{MOTIF_SHELF[0]}"]
    width, height = MOTIF_SIZE
    found = []
    folder = root / data["cards"]["motifs"]
    used = {row.motif for row in [*pack.rows(data), pack.template_row(data)]}
    used |= {entry["motif"] for entry in data.get("readme_banners", {}).get("repos", []) if entry.get("motif")}
    for name in sorted(used - {path.stem for path in folder.glob("*.svg")}):
        found.append(f"pack.json: a card or a banner asks for the motif {name!r}, and {data['cards']['motifs']}/{name}.svg does not exist")
    for path in sorted(folder.glob("*.svg")):
        name = path.relative_to(root).as_posix()
        if path.stem not in used:
            found.append(f"{name}: no card and no banner uses this motif")
        try:
            tree = source.parse(path)
            holder = source.by_id(tree).get("motif")
            if holder is None:
                found.append(f"{name}: has no <g id=\"motif\">")
                continue
            if holder.get("transform") != "translate(0 0)":
                found.append(f"{name}: its motif group is placed with 'translate(0 0)'; the card moves it")
            for element in holder.iter():
                tag = source.tag(element)
                if element is holder or tag == "tspan":
                    continue
                if tag not in MOTIF_ELEMENTS:
                    found.append(f"{name}: holds a <{tag}>; a motif is drawn with {', '.join(sorted(MOTIF_ELEMENTS - {'g'}))}")
                if element.get("transform"):
                    found.append(f"{name}: a <{tag}> carries a transform; a motif's shapes are written where they are drawn")
                fill, stroke = element.get("fill", "none"), element.get("stroke", "none")
                if fill != "none" and fill.lower() not in fills:
                    found.append(f"{name}: a <{tag}> is filled with {fill}; a motif's fills are the social palette's")
                if stroke == "none":
                    continue
                if (tag == "line" and stroke.lower() == shelf_ink and float(element.get("stroke-width", "1")) == MOTIF_SHELF[1]
                        and element.get("y1") == element.get("y2")):
                    continue  # a shelf for an upper row of boards
                if stroke.lower() not in strokes:
                    found.append(f"{name}: a <{tag}> is lined with {stroke}; a motif's lines are the signal color, or ink for a detail")
                if float(element.get("stroke-width", "1")) not in MOTIF_LINES:
                    found.append(f"{name}: a <{tag}> has a {element.get('stroke-width')} px line; a motif's lines are 12 px, or 8 px for a fine detail")
                if tag in ("line", "path") and element.get("stroke-linecap") != "round":
                    found.append(f"{name}: a <{tag}> has no round caps")
                if tag == "path" and element.get("stroke-linejoin") != "round":
                    found.append(f"{name}: a <path> has no round joins")
            drawing = source.ready(tree, pack.brand_root(root), name)
            if drawing.size != MOTIF_SIZE:
                found.append(f"{name}: is {drawing.size[0]} x {drawing.size[1]}; a motif is {width} x {height}")
            box = drawing.motif
            if box is None:
                found.append(f"{name}: draws nothing")
                continue
            if not source.inside(box, (0.0, 0.0, float(width), float(height))):
                found.append(f"{name}: reaches outside its {width} x {height} box ({box[0]:.1f}, {box[1]:.1f}, {box[2]:.1f}, {box[3]:.1f})")
            if abs(box[3] - height) > 0.01:
                found.append(f"{name}: does not stand on the shelf: its lowest edge is at {box[3]:.1f}, and the shelf is at {height}")
        except (ValueError, KeyError, ET.ParseError) as error:
            found.append(f"{name}: {error}")
    return found


def card_findings(root: Path, built: Card) -> list[str]:
    """Return what in one card breaks the system: something outside its place, or too small to read at 400 px (the title and the mark, at 320 px)."""
    drawing, row = built.drawing, built.row
    found = source.keep_findings(drawing)
    column, motif_box = drawing.guides.get("column"), drawing.guides.get("motif-box")
    if column is None or motif_box is None:
        return [*found, f"{drawing.name}: the template has no 'column' or 'motif-box' guide"]
    for name, placed in drawing.words.items():
        if name != "label" and not source.inside(placed.box(), column):
            found.append(f"{drawing.name}: the words {name!r} ({placed.line.text!r}) reach outside the text column, toward the motif")
    if drawing.motif is not None and not source.inside(drawing.motif, motif_box):
        found.append(f"{drawing.name}: its motif {row.motif!r} reaches outside the motif's box")
    shelf = drawing.guides.get("safe")
    if drawing.motif is not None and drawing.shapes is not None and shelf is not None:
        tree = source.parse(root / built.inputs[0])
        line = source.by_id(tree).get("shelf")
        if line is not None:
            top = float(line.get("y1", "0")) - float(line.get("stroke-width", "0")) / 2
            if abs(drawing.motif[3] - top) > 0.01:
                found.append(f"{drawing.name}: its motif does not stand on the shelf (its lowest edge is at {drawing.motif[3]:.1f}, the shelf's top at {top:.1f})")

    # What is left of it at 400 px wide, and of its title and its mark at 320.
    brand = pack.brand_root(root)
    for name, width, least, part, what in (
        ("title", NARROW_WIDTH, MIN_TITLE_PX, "sCapHeight", "the title's capitals"),
        ("line.0", SMALL_WIDTH, MIN_LINE_PX, "sxHeight", "the line's x-height"),
    ):
        placed = drawing.words.get(name)
        if placed is None:
            found.append(f"{drawing.name}: has no {name!r}")
            continue
        font, _ = lettering._instance(brand, placed.line.family, placed.line.axes)  # noqa: SLF001
        height = float(getattr(font["OS/2"], part)) * placed.scale * width / drawing.size[0]
        if height < least:
            found.append(f"{drawing.name}: at {width} px wide {what} are {height:.1f} px high; the least is {least:.0f}")
    if drawing.lockup is not None:
        mark_box = (drawing.lockup[3] - drawing.lockup[1]) * NARROW_WIDTH / drawing.size[0]
        if mark_box < MIN_MARK_PX:
            found.append(f"{drawing.name}: at {NARROW_WIDTH} px wide the mark is {mark_box:.1f} px; the least is {MIN_MARK_PX:.0f}")
    return found
