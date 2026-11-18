# SPDX-License-Identifier: MIT
"""The previews: the exported pictures as a platform shows them, on sheets to look at.

A preview is for the person who reviews the pack, not for upload: the contact
sheet of every file, the avatar in the circle each platform cuts at the sizes
it shows, the YouTube banner as each device crops it, the MakerTube banner at
both stored sizes, and every repository card at the widths a page or a chat
gives it and in the 1.91:1 crop some sites apply.

A sheet is drawn in two steps, as brand draws a picture that holds captures:
Chromium draws its ground, its tiles and its labels (outlines of the pinned
fonts), and Pillow pastes the pictures on it, resampled from the exported
files' own pixels. So a preview shows what was exported, never a second
drawing of the source.
"""
from __future__ import annotations

import hashlib
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import pack
from kleidos_brand import lettering, png, raster, record, svgtext, tokens

MARGIN = 40
GAP = 40
LABEL_BAND = 34  # a label's line and the space under it
LEDE_SIZE = 22
LEDE_AXES = (("opsz", 20.0), ("wdth", 100.0), ("wght", 400.0))
THIS_FILE = Path("tools/previews.py")

HEADING = 'font-family="Mona Sans" font-weight="650" font-stretch="112.5%" style="font-variation-settings:\'opsz\' 72" letter-spacing="-0.02em"'
LEDE = 'font-family="Mona Sans" font-weight="400" style="font-variation-settings:\'opsz\' 20" letter-spacing="0em"'
LABEL = 'font-family="Mona Sans Mono" font-weight="500" letter-spacing="0.02em"'

#: The YouTube banner's views, as crops of the 2560 x 1440 file.
BANNER_VIEWS = (
    ("TV: the whole file", (0, 0, 2560, 1440)),
    ("Computer: a band up to 2560 x 423", (0, 508, 2560, 931)),
    ("Tablet: 1855 x 423", (352, 508, 2207, 931)),
    ("Phone: 1546 x 423, the safe area", (507, 508, 2053, 931)),
)
#: The circles a platform cuts the avatar to, in pixels.
AVATAR_SIZES = {"png/youtube/avatar.png": ("YouTube", (98, 48, 32, 24)), "png/makertube/avatar.png": ("MakerTube", (120, 48))}
ENLARGED = 4
#: The widths a repository card is shown at, beside the half-size view.
CARD_WIDTHS = (640, 400, 320)
CROP_RATIO = 1.91


def _image(data: bytes) -> Any:
    from PIL import Image  # noqa: PLC0415

    with Image.open(io.BytesIO(data)) as opened:
        return opened.convert("RGBA")


def resized(image: Any, size: tuple[int, int]) -> Any:
    """Return *image* at *size*, resampled as a page resamples a picture it shrinks."""
    from PIL import Image  # noqa: PLC0415

    return image if image.size == size else image.resize(size, Image.Resampling.LANCZOS)


def fitted(image: Any, box: tuple[int, int]) -> Any:
    """Return *image* shrunk to fit *box*, never enlarged."""
    share = min(box[0] / image.width, box[1] / image.height, 1.0)
    return resized(image, (max(1, round(image.width * share)), max(1, round(image.height * share))))


def in_circle(image: Any, diameter: int) -> Any:
    """Return *image* at *diameter* pixels, cut to the circle a profile picture is shown in."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    small = resized(image, (diameter, diameter))
    over = 8
    mask = Image.new("L", (diameter * over, diameter * over), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter * over - 1, diameter * over - 1), fill=255)
    small.putalpha(mask.resize((diameter, diameter), Image.Resampling.LANCZOS))
    return small


def enlarged(image: Any, times: int) -> Any:
    """Return *image* with each pixel a square of *times* pixels."""
    from PIL import Image  # noqa: PLC0415

    return image.resize((image.width * times, image.height * times), Image.Resampling.NEAREST)


def covering(image: Any, size: tuple[int, int]) -> Any:
    """Return *image* scaled to cover *size* and cut to it around its center, as a stored smaller copy is made."""
    share = max(size[0] / image.width, size[1] / image.height)
    scaled = resized(image, (max(size[0], round(image.width * share)), max(size[1], round(image.height * share))))
    left, top = (scaled.width - size[0]) // 2, (scaled.height - size[1]) // 2
    return scaled.crop((left, top, left + size[0], top + size[1]))


def center_crop(image: Any, ratio: float) -> Any:
    """Return the centered part of *image* that is *ratio* times as wide as it is high."""
    width = round(image.height * ratio)
    left = (image.width - width) // 2
    return image.crop((left, 0, left + width, image.height))


def wrapped(words: str, width: float, brand: Path) -> list[str]:
    """Return *words* broken into the lines that fit *width* in the lede's face and size."""
    lines: list[str] = []
    for word in words.split():
        longer = f"{lines[-1]} {word}" if lines else word
        line = lettering.shape(longer, "Mona Sans", LEDE_AXES, 0.0, brand)
        if lines and line.advance * LEDE_SIZE / line.upem <= width:
            lines[-1] = longer
        else:
            lines.append(word)
    return lines


class Layout:
    """A sheet being laid out: its tiles, its labels and the pictures pasted on it."""

    def __init__(self, width: int, values: dict[str, Any]) -> None:
        self.width = width
        self.values = values
        self.height = 0
        self.tiles: list[str] = []
        self.texts: list[str] = []
        self.plates: list[tuple[int, int, Any]] = []
        self._ids = 0

    def text(self, x: float, y: float, words: str, style: str, size: int, fill: str) -> None:
        """Set *words* with their baseline starting at (*x*, *y*)."""
        self._ids += 1
        self.texts.append(f'<text id="t{self._ids}" x="{x}" y="{y}" font-size="{size}" {style} fill="{fill}">{escape(words)}</text>')
        self.height = max(self.height, int(y) + size)

    def label(self, x: float, y: float, words: str, fill: str | None = None) -> None:
        """Set a label in the band that starts at *y*."""
        self.text(x, y + 22, words, LABEL, 20, fill or self.values["social.ink-2"])

    def tile(self, x: int, y: int, width: int, height: int, fill: str, line: bool = True) -> None:
        """Paint a tile, with the hairline that shows where a picture on the sheet's own ground ends."""
        stroke = f' stroke="{self.values["social.rule"]}" stroke-width="2"' if line else ""
        self.tiles.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{fill}"{stroke}/>')
        self.height = max(self.height, y + height)

    def plate(self, x: int, y: int, image: Any, frame: bool = True) -> None:
        """Paste *image* with its top left corner at (*x*, *y*)."""
        if frame:
            self.tile(x - 1, y - 1, image.width + 2, image.height + 2, self.values["social.ground"])
        self.plates.append((x, y, image))
        self.height = max(self.height, y + image.height)

    def head(self, spec: dict[str, Any], brand: Path) -> int:
        """Set the sheet's title and what it shows, and return where the sheet's body starts."""
        self.text(MARGIN, 78, spec["title"], HEADING, 44, self.values["social.ink"])
        y = 118
        for line in wrapped(spec["lede"], self.width - 2 * MARGIN, brand):
            self.text(MARGIN, y, line, LEDE, LEDE_SIZE, self.values["social.ink-2"])
            y += LEDE_SIZE + 8
        return y + 2

    def render(self, browser: raster.Browser, brand: Path, name: str) -> bytes:
        """Return the sheet as a PNG."""
        height = self.height + MARGIN
        ground = self.values["social.ground"]
        body = "\n".join([f'<rect x="0" y="0" width="{self.width}" height="{height}" fill="{ground}"/>', *self.tiles, *self.texts])
        tree = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {height}" width="{self.width}" height="{height}">\n{body}\n</svg>')
        ET.register_namespace("", svgtext.SVG_NS)
        svgtext.outline(tree, brand)
        sheet = png.clean(browser.draw(ET.tostring(tree, encoding="unicode"), (self.width, height), name), flatten=ground)
        for x, y, image in self.plates:
            sheet.paste(image, (x, y), image)
        return png.encode(sheet)


class Sheet:
    """One preview: what it shows, what it is drawn from, and how."""

    def __init__(self, root: Path, data: dict[str, Any], spec: dict[str, Any], shown: list[Any], template: Any) -> None:
        self.root = root
        self.data = data
        self.spec = spec
        self.kind = spec["kind"]
        self.template = template
        if self.kind == "contact-sheet":
            self.shown = list(shown)
        elif self.kind == "avatars":
            self.shown = [picture for picture in shown if picture.path.as_posix() in AVATAR_SIZES]
        elif self.kind == "youtube-banner":
            self.shown = [picture for picture in shown if picture.path.as_posix() == "png/youtube/banner.png"]
        elif self.kind == "makertube-banner":
            self.shown = [picture for picture in shown if picture.path.as_posix() == "png/makertube/banner.png"]
        elif self.kind == "cards":
            self.shown = [picture for picture in shown if picture.kind == "card"]
        else:
            raise ValueError(f"pack.json: {spec['file']} is of the kind {self.kind!r}, which no preview draws")
        if not self.shown:
            raise ValueError(f"pack.json: the preview {spec['file']} has nothing to show")
        extra = template.inputs if self.kind == "cards" else ()
        self.inputs: tuple[Path, ...] = tuple(dict.fromkeys((THIS_FILE, *extra, *(picture.path for picture in self.shown))))
        stated = json.dumps([spec, [[picture.path.as_posix(), list(picture.size)] for picture in self.shown],
                             template.drawing.svg if self.kind == "cards" else ""], sort_keys=True)
        self.digest = hashlib.sha256(stated.encode()).hexdigest()

    def _bytes(self, picture: Any, drawn: dict[str, bytes]) -> bytes:
        name = picture.path.as_posix()
        return drawn[name] if name in drawn else (self.root / picture.path).read_bytes()

    def draw(self, browser: raster.Browser, drawn: dict[str, bytes]) -> bytes:
        """Return the preview, drawn from the pictures in *drawn* or, failing that, from the tree's."""
        values = tokens.resolve(tokens.load(pack.brand_root(self.root)))
        layout = getattr(self, f"_{self.kind.replace('-', '_')}")(browser, drawn, values)
        return layout.render(browser, pack.brand_root(self.root), Path(self.spec["file"]).stem)

    # --- The sheets ----------------------------------------------------------------------

    def _contact_sheet(self, _: raster.Browser, drawn: dict[str, bytes], values: dict[str, Any]) -> Layout:
        columns, cell = 4, (350, 230)
        layout = Layout(MARGIN + columns * (cell[0] + GAP), values)
        top = layout.head(self.spec, pack.brand_root(self.root))
        for index, picture in enumerate(self.shown):
            data = self._bytes(picture, drawn)
            x = MARGIN + (index % columns) * (cell[0] + GAP)
            y = top + (index // columns) * (cell[1] + 2 * LABEL_BAND + GAP)
            layout.tile(x, y, cell[0], cell[1], values["web.dark.raised"])
            small = fitted(_image(data), (cell[0] - 24, cell[1] - 24))
            layout.plate(x + (cell[0] - small.width) // 2, y + (cell[1] - small.height) // 2, small, frame=False)
            width, height = png.size(data)
            layout.label(x, y + cell[1] + 8, picture.path.as_posix(), values["social.ink"])
            layout.label(x, y + cell[1] + 8 + LABEL_BAND - 6, f"{width} x {height}, {record.human_bytes(len(data))}")
        return layout

    def _avatars(self, _: raster.Browser, drawn: dict[str, bytes], values: dict[str, Any]) -> Layout:
        page = 620
        layout = Layout(MARGIN + 2 * (page + GAP), values)
        top = layout.head(self.spec, pack.brand_root(self.root))
        pages = (("a dark page", values["web.dark.surface"], values["social.ink-2"]),
                 ("a light page", values["social.light.ground"], values["social.light.ink-2"]))
        for column, (what, ground, ink) in enumerate(pages):
            x0, y = MARGIN + column * (page + GAP), top
            rows = len(self.shown) * (120 + 2 * LABEL_BAND + GAP) + LABEL_BAND + 48 * ENLARGED
            layout.tile(x0, y, page, rows + GAP, ground)
            y += GAP // 2
            small: list[tuple[int, Any]] = []
            for picture in self.shown:
                platform, sizes = AVATAR_SIZES[picture.path.as_posix()]
                avatar = _image(self._bytes(picture, drawn))
                layout.label(x0 + GAP, y, f"{platform}, on {what}", ink)
                x = x0 + GAP
                for diameter in sizes:
                    cut = in_circle(avatar, diameter)
                    layout.plate(x, y + LABEL_BAND + (120 - diameter) // 2, cut, frame=False)
                    layout.label(x, y + LABEL_BAND + 120 + 6, f"{diameter} px", ink)
                    if platform == "YouTube" and diameter <= 48:
                        small.append((diameter, cut))
                    x += max(diameter, 80) + GAP
                y += 120 + 2 * LABEL_BAND + GAP
            layout.label(x0 + GAP, y, f"The small ones, each pixel {ENLARGED} times its size", ink)
            x = x0 + GAP
            for diameter, cut in small:
                layout.plate(x, y + LABEL_BAND + (48 - diameter) * ENLARGED // 2, enlarged(cut, ENLARGED), frame=False)
                x += diameter * ENLARGED + GAP
        return layout

    def _youtube_banner(self, _: raster.Browser, drawn: dict[str, bytes], values: dict[str, Any]) -> Layout:
        banner = _image(self._bytes(self.shown[0], drawn))
        layout = Layout(2 * MARGIN + banner.width // 2, values)
        top = layout.head(self.spec, pack.brand_root(self.root))
        y = top
        for what, box in BANNER_VIEWS:
            view = banner.crop(box)
            layout.label(MARGIN, y, what)
            layout.plate(MARGIN, y + LABEL_BAND, resized(view, (view.width // 2, view.height // 2)))
            y += LABEL_BAND + view.height // 2 + GAP
        return layout

    def _makertube_banner(self, _: raster.Browser, drawn: dict[str, bytes], values: dict[str, Any]) -> Layout:
        banner = _image(self._bytes(self.shown[0], drawn))
        wide = (banner.width * 2 // 3, banner.height * 2 // 3)
        layout = Layout(2 * MARGIN + wide[0], values)
        top = layout.head(self.spec, pack.brand_root(self.root))
        y = top
        layout.label(MARGIN, y, f"{banner.width} x {banner.height}, at two thirds")
        layout.plate(MARGIN, y + LABEL_BAND, resized(banner, wide))
        y += LABEL_BAND + wide[1] + GAP
        layout.label(MARGIN, y, "600 x 100, the smaller copy, pixel for pixel")
        small = covering(banner, (600, 100))
        layout.plate(MARGIN, y + LABEL_BAND, small)
        layout.label(MARGIN + 600 + GAP, y, "the same, each pixel twice its size")
        layout.plate(MARGIN + 600 + GAP, y + LABEL_BAND, enlarged(small.crop((0, 0, 300, 100)), 2))
        return layout

    def _cards(self, browser: raster.Browser, drawn: dict[str, bytes], values: dict[str, Any]) -> Layout:
        size = pack.card_size(self.data)
        half = (size[0] // 2, size[1] // 2)
        crop_width = round(320 * CROP_RATIO)
        layout = Layout(MARGIN + half[0] + GAP + CARD_WIDTHS[0] + GAP + crop_width + MARGIN, values)
        top = layout.head(self.spec, pack.brand_root(self.root))
        owner = self.data["cards"]["owner"]
        shown = [(f"{owner}/{picture.path.stem.replace('dot-', '.')}", _image(self._bytes(picture, drawn))) for picture in self.shown]
        blank = png.clean(browser.draw(self.template.drawing.svg, size, "card-template"), flatten=self.template.drawing.ground)
        shown.append(("the template, with a placeholder row", blank.convert("RGBA")))
        y = top
        for name, image in shown:
            layout.label(MARGIN, y, f"{name}, at {half[0]} x {half[1]}", values["social.ink"])
            layout.plate(MARGIN, y + LABEL_BAND, resized(image, half))
            x = MARGIN + half[0] + GAP
            layout.label(x, y, f"{CARD_WIDTHS[0]} x {CARD_WIDTHS[0] // 2}")
            layout.plate(x, y + LABEL_BAND, resized(image, (CARD_WIDTHS[0], CARD_WIDTHS[0] // 2)))
            layout.label(x + CARD_WIDTHS[0] + GAP, y, f"cropped to {CROP_RATIO}:1, at {crop_width} x 320")
            layout.plate(x + CARD_WIDTHS[0] + GAP, y + LABEL_BAND, resized(center_crop(image, CROP_RATIO), (crop_width, 320)))
            below = y + LABEL_BAND + 320 + GAP // 2
            for width in CARD_WIDTHS[1:]:
                layout.label(x, below, f"{width} x {width // 2}")
                layout.plate(x, below + LABEL_BAND, resized(image, (width, width // 2)))
                x += width + GAP
            y += LABEL_BAND + half[1] + GAP
        return layout
