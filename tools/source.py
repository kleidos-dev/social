# SPDX-License-Identifier: MIT
"""An SVG source, made ready to draw, and what the checks measure on it.

A source is what brand calls one (``kleidos_brand.svg_rules``): three layers
(``ground``, ``content``, ``guides``), plain shapes, token colors, and live
words in the pinned Mona Sans, so it opens and edits in any SVG editor that
has the fonts. Here a source may also hold:

- ``<g id="lockup" data-lockup="horizontal" transform="translate(x y) scale(s)">``:
  the logo, a copy of what brand's logo files draw, filled in again from brand
  on every export so it cannot drift;
- ``<g class="mark" transform="translate(x y) scale(s)">``: the mark by itself;
- ``<g id="motif" transform="translate(x y)">``: a card's motif;
- in ``guides``, ``<rect id="safe">``: the area everything drawn must stay
  inside, and other named rects a preview or a check reads;
- ``<rect data-boards="…" fill="none">``: a shelf, where brand's board fronts
  are drawn at one true scale (``kleidos_brand.boards``), each board's unlock
  screen pasted on its panel after the drawing.

:func:`ready` turns one into a :class:`Drawing`: the words as outlines, the
guides gone, and the boxes of everything it drew.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pack  # noqa: F401  (puts brand/tools on the path)
from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path
from kleidos_brand import SVG_HEADER, boards, logo, mark, svg_rules, svgtext

SVG_NS = svgtext.SVG_NS
PLACED = re.compile(r"translate\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)(?: scale\((\d+(?:\.\d+)?)\))?")

Box = tuple[float, float, float, float]  # left, top, right, bottom
#: What an SVG says about itself rather than draws.
DESCRIPTIVE = frozenset({"title", "desc", "metadata"})


def tag(element: ET.Element) -> str:
    """Return an element's name without its namespace."""
    return element.tag.rsplit("}", 1)[-1]


def parse(path: Path) -> ET.Element:
    """Return the tree of the source at *path*."""
    ET.register_namespace("", SVG_NS)
    return ET.fromstring(path.read_text(encoding="utf-8"))


def by_id(tree: ET.Element) -> dict[str, ET.Element]:
    """Return every element of *tree* that has an id, by it."""
    return {element.get("id", ""): element for element in tree.iter() if element.get("id")}


def placement(element: ET.Element) -> tuple[float, float, float]:
    """Return where a group is put: its translation and its scale, from ``translate(x y) scale(s)``."""
    match = PLACED.fullmatch(element.get("transform", ""))
    if not match:
        raise ValueError(f"<{tag(element)} id={element.get('id')!r} class={element.get('class')!r}> is placed with"
                         f" 'translate(x y)' or 'translate(x y) scale(s)', not {element.get('transform')!r}")
    return float(match.group(1)), float(match.group(2)), float(match.group(3) or 1)


def union(boxes: list[Box]) -> Box | None:
    """Return the box that holds every box of *boxes*."""
    if not boxes:
        return None
    return (min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes))


def inside(inner: Box, outer: Box, slack: float = 0.01) -> bool:
    """Tell whether *inner* lies within *outer*."""
    return inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack


def rect_box(element: ET.Element) -> Box:
    """Return a ``<rect>``'s own box, without its line."""
    x, y = float(element.get("x", "0")), float(element.get("y", "0"))
    return x, y, x + float(element.get("width", "0")), y + float(element.get("height", "0"))


def ink_box(element: ET.Element) -> Box | None:
    """Return the box a plain shape paints, its line's half width included on every side.

    The half width on every side is exact for a closed shape and for a line
    with round caps, which is what a motif is drawn with; a straight line with
    flat ends grows across only.
    """
    name = tag(element)
    if name == "rect":
        box: Box | None = rect_box(element)
    elif name == "circle":
        cx, cy, r = (float(element.get(key, "0")) for key in ("cx", "cy", "r"))
        box = (cx - r, cy - r, cx + r, cy + r)
    elif name == "ellipse":
        cx, cy, rx, ry = (float(element.get(key, "0")) for key in ("cx", "cy", "rx", "ry"))
        box = (cx - rx, cy - ry, cx + rx, cy + ry)
    elif name == "line":
        x1, y1, x2, y2 = (float(element.get(key, "0")) for key in ("x1", "y1", "x2", "y2"))
        box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    elif name in ("polyline", "polygon"):
        numbers = [float(part) for part in re.split(r"[\s,]+", element.get("points", "").strip()) if part]
        xs, ys = numbers[0::2], numbers[1::2]
        box = (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None
    elif name == "path":
        pen = BoundsPen(None)
        parse_path(element.get("d", ""), pen)
        box = pen.bounds
    else:
        return None
    if box is None:
        return None
    grow = float(element.get("stroke-width", "1")) / 2 if element.get("stroke", "none") != "none" else 0.0
    along_x = along_y = grow
    if name == "line" and element.get("stroke-linecap", "butt") == "butt":
        # A line with flat ends is no longer than it is written.
        if box[1] == box[3]:
            along_x = 0.0
        elif box[0] == box[2]:
            along_y = 0.0
    return box[0] - along_x, box[1] - along_y, box[2] + along_x, box[3] + along_y


def lockup_children(brand: Path, kind: str = "horizontal") -> tuple[list[ET.Element], logo.Logo]:
    """Return the shapes of brand's lockup for a dark ground, and the logo file they come from.

    The logo file's own title, description and metadata describe that file, not a lockup pasted
    into a picture, so they are left behind.
    """
    chosen = next(item for item in logo.build(brand) if item.stem == f"kleidos-lockup-{kind}-for-dark")
    return [child for child in ET.fromstring(chosen.svg) if tag(child) not in DESCRIPTIVE], chosen


def _canon(elements: list[ET.Element]) -> list[Any]:
    return [(tag(element), tuple(sorted(element.attrib.items())), _canon(list(element))) for element in elements]


def lockup_matches(tree: ET.Element, brand: Path) -> bool:
    """Tell whether a source's own copy of the lockup is the one brand's logo files draw."""
    holder = by_id(tree).get("lockup")
    if holder is None:
        return True
    children, _ = lockup_children(brand, holder.get("data-lockup", "horizontal"))
    return _canon(list(holder)) == _canon(children)


def set_words(element: ET.Element, text: str, accent: str | None = None, accent_fill: str | None = None) -> None:
    """Write *text* into a ``<text>``, its *accent* words in a ``<tspan>`` of their own color."""
    for child in list(element):
        element.remove(child)
    if accent and accent_fill and accent in text:
        before, after = text.split(accent, 1)
        element.text = before
        span = ET.SubElement(element, f"{{{SVG_NS}}}tspan", {"fill": accent_fill})
        span.text = accent
        span.tail = after
    else:
        element.text = text


def remove(tree: ET.Element, target: ET.Element) -> None:
    """Take *target* out of *tree*."""
    for parent in tree.iter():
        if target in list(parent):
            parent.remove(target)
            return
    raise ValueError("the element is not in the tree")


@dataclass
class Drawing:
    """A source ready to draw: its outlined SVG, and the box of everything it draws."""

    name: str
    svg: str
    size: tuple[int, int]
    ground: str | None  # the ground's color, or None on transparency
    words: dict[str, svgtext.Set] = field(default_factory=dict)
    lockup: Box | None = None
    lockup_scale: float = 0.0
    marks: list[tuple[float, float, float]] = field(default_factory=list)  # each bare mark's center and scale
    motif: Box | None = None
    motif_origin: tuple[float, float] | None = None
    shapes: Box | None = None  # everything else the content layer draws
    guides: dict[str, Box] = field(default_factory=dict)
    fronts: list[boards.Placement] = field(default_factory=list)  # the board fronts on its shelves

    def mark_boxes(self) -> list[Box]:
        """Return the box of each bare mark's ring, its line included."""
        radius = mark.BOX / 2 - mark.RING_INSET
        return [(x - radius * s, y - radius * s, x + radius * s, y + radius * s) for x, y, s in self.marks]

    def drawn(self) -> dict[str, Box]:
        """Return the box of everything drawn, by what it is."""
        boxes: dict[str, Box] = {f"the words {name!r} ({placed.line.text!r})": placed.box() for name, placed in self.words.items()}
        if self.lockup is not None:
            boxes["the lockup"] = self.lockup
        for index, box in enumerate(self.mark_boxes()):
            boxes[f"the mark{'' if index == 0 else f' {index + 1}'}"] = box
        if self.motif is not None:
            boxes["the motif"] = self.motif
        if self.shapes is not None:
            boxes["its shapes"] = self.shapes
        for placed in self.fronts:
            boxes[f"the board {placed.front.name}"] = placed.box()
        return boxes


def ready(tree: ET.Element, brand: Path, name: str) -> Drawing:
    """Return the source *tree* ready to draw. The tree is changed in place.

    :param brand: The brand repository the lockup and the fonts come from.
    :param name: What to call the drawing in a finding.
    """
    size = svg_rules.canvas(tree)
    if size is None:
        raise ValueError(f"{name}: its root has no viewBox of the form '0 0 W H'")
    named = by_id(tree)
    drawing = Drawing(name, "", size, None)

    ground = named.get("ground")
    if ground is not None:
        full = [child for child in ground if tag(child) == "rect" and rect_box(child) == (0.0, 0.0, float(size[0]), float(size[1]))]
        if full:
            drawing.ground = full[0].get("fill", "").lower()

    # The lockup, as brand's logo files draw it.
    holder = named.get("lockup")
    inside_lockup: set[ET.Element] = set()
    if holder is not None:
        children, chosen = lockup_children(brand, holder.get("data-lockup", "horizontal"))
        for child in list(holder):
            holder.remove(child)
        holder.extend(children)
        x, y, scale = placement(holder)
        drawing.lockup = (x, y, x + chosen.width * scale, y + chosen.height * scale)
        drawing.lockup_scale = scale
        inside_lockup = set(holder.iter())

    # The marks that stand by themselves.
    for element in tree.iter():
        if tag(element) == "g" and "mark" in element.get("class", "").split() and element not in inside_lockup:
            drawing.marks.append(placement(element))

    # The guides, read before they go.
    guides = named.get("guides")
    if guides is not None:
        for element in guides.iter():
            if tag(element) == "rect" and element.get("id"):
                drawing.guides[element.get("id", "")] = rect_box(element)

    # The motif's shapes, and whatever else the content draws, measured before the words become paths.
    motif = named.get("motif")
    inside_motif: set[ET.Element] = set(motif.iter()) if motif is not None else set()
    motif_words: list[str] = []
    if motif is not None:
        dx, dy, _ = placement(motif)
        drawing.motif_origin = (dx, dy)
        boxes = []
        for element in motif.iter():
            if tag(element) == "text":
                if not element.get("id"):
                    raise ValueError(f"{name}: a motif's words need an id, to be measured")
                motif_words.append(element.get("id", ""))
                continue
            box = ink_box(element)
            if box is not None:
                boxes.append((box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy))
        drawing.motif = union(boxes)
    content = named.get("content")
    if content is not None:
        marks = {inner for element in content.iter() if "mark" in element.get("class", "").split() for inner in element.iter()}
        loose = [ink_box(element) for element in content.iter() if element not in inside_lockup and element not in inside_motif and element not in marks]
        drawing.shapes = union([box for box in loose if box is not None])

    placed = svgtext.outline(tree, brand)
    drawing.fronts = boards.fill(tree, brand)
    for key, value in placed.items():
        if key in motif_words:
            dx, dy = drawing.motif_origin or (0.0, 0.0)
            box = value.box()
            moved = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
            drawing.motif = union([moved, *([drawing.motif] if drawing.motif else [])])
        else:
            drawing.words[key] = value
    if guides is not None:
        tree.remove(guides)
    for element in tree.iter():
        for key in [key for key in element.attrib if key.startswith("data-")]:
            del element.attrib[key]
    ET.indent(tree, "  ")
    drawing.svg = SVG_HEADER + ET.tostring(tree, encoding="unicode") + "\n"
    return drawing


def keep_findings(drawing: Drawing) -> list[str]:
    """Return what in *drawing* leaves its safe area, by geometry."""
    safe = drawing.guides.get("safe")
    if safe is None:
        return [f"{drawing.name}: has no 'safe' guide to measure against"]
    found = []
    for what, box in drawing.drawn().items():
        if not inside(box, safe):
            found.append(f"{drawing.name}: {what} reaches outside the safe area"
                         f" ({box[0]:.0f}, {box[1]:.0f}, {box[2]:.0f}, {box[3]:.0f} against {safe[0]:.0f}, {safe[1]:.0f}, {safe[2]:.0f}, {safe[3]:.0f})")
    crop = drawing.guides.get("crop")
    if crop is not None and not inside(safe, crop):
        found.append(f"{drawing.name}: its safe area reaches outside the crop some sites apply")
    return found


def painted_findings(name: str, data: bytes, drawing: Drawing) -> list[str]:
    """Return what the pixels of an exported PNG say: nothing is painted outside the safe area.

    Every pixel that is not the ground (or, on transparency, not clear) must
    fall inside the ``safe`` guide, scaled to the file's own pixels and
    widened by one pixel for the edge a curve is smoothed with.
    """
    import io  # noqa: PLC0415

    from PIL import Image, ImageChops  # noqa: PLC0415

    safe = drawing.guides.get("safe")
    if safe is None:
        return []
    with Image.open(io.BytesIO(data)) as opened:
        if drawing.ground is None:
            painted = opened.convert("RGBA").getchannel("A").getbbox()
        else:
            pixels = opened.convert("RGB")
            painted = ImageChops.difference(pixels, Image.new("RGB", pixels.size, drawing.ground)).getbbox()
        scale_x, scale_y = opened.size[0] / drawing.size[0], opened.size[1] / drawing.size[1]
    if painted is None:
        return [f"{name}: nothing is painted on it"]
    allowed = (safe[0] * scale_x - 1, safe[1] * scale_y - 1, safe[2] * scale_x + 1, safe[3] * scale_y + 1)
    if not inside((float(painted[0]), float(painted[1]), float(painted[2]), float(painted[3])), allowed):
        return [f"{name}: pixels are painted at {painted}, outside its safe area"
                f" ({allowed[0] + 1:.0f}, {allowed[1] + 1:.0f}, {allowed[2] - 1:.0f}, {allowed[3] - 1:.0f})"]
    return []
