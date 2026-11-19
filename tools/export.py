#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export the social pack, or check that what is committed is what the sources give.

    tools/export.py                     draw every image, card, README banner and preview, and write
                                        the record and the README's tables
    tools/export.py --check             draw everything again and fail on any difference, pixel for
                                        pixel; refused under a browser other than the recorded one
    tools/export.py --check --static    what needs no browser: the tables, and each picture's bytes
                                        against the record of what it was drawn from
    tools/export.py --check --tolerant  draw again under any browser and fail on gross drift only
    tools/export.py --title "One line|and another" [--art picture.png] --out dist
                                        a one-off thumbnail for a video, from the template; the
                                        pack is not touched

Everything is drawn from the sources under src/, the rows of pack.json and the
brand submodule: its mark, its lockup, its tokens and its fonts. Chromium
draws, through Playwright, from SVG that holds outlines only; Pillow encodes
again from the pixels alone, and each file then carries brand's metadata
profile, written from its record (records.py). The exact comparison belongs to the machine that
exported; the static check and the tolerant one run anywhere, and CI runs both.
The README banners are SVG files no browser draws (readme_banners.py), so every
check holds them byte for byte.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cards  # noqa: E402
import pack  # noqa: E402
import previews  # noqa: E402
import readme_banners  # noqa: E402
import records  # noqa: E402
import source  # noqa: E402
import sync_readme_banners  # noqa: E402
from kleidos_brand import boards, mark, meta, png, raster, record  # noqa: E402

ROOT = pack.ROOT
#: The share of pixels that may differ by more than a shade under another browser.
TOLERANCE = 0.005
COMMENT = ("Written by tools/export.py: the browser the pictures were drawn with, and the bytes of each picture and of"
           " what it was drawn from, the brand files included. Do not edit; run the exporter.")
GENERATED_DIRS = (Path("png/youtube"), Path("png/makertube"), Path("png/github"), pack.PREVIEWS_DIR)
#: The folder the README banners are written to, one folder per repository inside it.
BANNER_DIR = Path("svg/readme")
THUMBNAIL = Path("src/youtube/thumbnail.svg")


@dataclass(frozen=True)
class Picture:
    """A generated picture (a PNG, or a README banner's SVG): its size, its limit, what it is drawn from and how."""

    path: Path
    size: tuple[int, int]
    source: str  # the SHA-256 of what it is drawn from
    inputs: tuple[Path, ...]
    draw: Callable[[raster.Browser, dict[str, bytes]], bytes]
    what: str
    kind: str  # "image", "card", "banner" or "preview"
    meta: Any  # the metadata it carries (records.py)
    limit: int | None = None
    rule: str | None = None
    slug: str | None = None  # a banner's id prefix (kleidos_brand.meta.svg_slug's role)


@dataclass
class Collected:
    """Everything the exporter owns, and what the checks measure on it."""

    data: dict[str, Any]
    pictures: list[Picture] = field(default_factory=list)
    drawings: dict[Path, source.Drawing] = field(default_factory=dict)  # by PNG path
    sources: dict[Path, source.Drawing] = field(default_factory=dict)  # by source path
    cards: list[cards.Card] = field(default_factory=list)
    banners: list[readme_banners.Banner] = field(default_factory=list)
    references: dict[Path, tuple[str, str | None]] = field(default_factory=dict)  # a mark-alone PNG's reference drawing


def brand_inputs() -> tuple[Path, ...]:
    """Return the brand files every picture is drawn from, as paths of this repository."""
    return tuple(pack.BRAND / path for path in pack.BRAND_INPUTS)


def fit_under(image: Any, limit: int | None, described: Any) -> bytes:
    """Return *image* as a PNG under *limit* bytes, its metadata included: as it is, or with a 256-color palette, never as a JPEG."""
    from PIL import Image  # noqa: PLC0415

    data = png.encode(image, described)
    if limit is None or len(data) < limit:
        return data
    reduced = png.encode(image.quantize(colors=256, dither=Image.Dither.NONE), described)
    if len(reduced) >= limit:
        raise ValueError(f"the picture weighs {len(data):,} bytes, {len(reduced):,} with a 256-color palette; the limit is under {limit:,}")
    return reduced


def drawn_from(svg: str, described: Any) -> str:
    """Return the digest of what a picture is drawn from: its outlined SVG, and the metadata it carries under brand's profile."""
    return record.sha256("\n".join((svg, meta.META_PROFILE, repr(described))).encode())


def board_inputs(drawing: source.Drawing) -> tuple[Path, ...]:
    """Return brand's board files a drawing with shelves is drawn from, as paths of this repository."""
    return tuple(pack.BRAND / path for path in boards.inputs(pack.brand_root())) if drawing.fronts else ()


def _drawer(drawing: source.Drawing, size: tuple[int, int], limit: int | None, name: str, described: Any) -> Callable[[raster.Browser, dict[str, bytes]], bytes]:
    def draw(browser: raster.Browser, _: dict[str, bytes]) -> bytes:
        image = png.clean(browser.draw(drawing.svg, size, name), flatten=drawing.ground)
        image = boards.paste_glass(image, drawing.fronts, pack.brand_root(), size[0] / drawing.size[0])
        return fit_under(image, limit, described)

    return draw


def mark_alone_reference(root: Path, drawing: source.Drawing, placed: dict[str, Any]) -> tuple[str, str | None]:
    """Return brand's mark drawn by itself where a mark-alone image puts it, and the ground under it."""
    width, height = drawing.size
    cx, cy = placed["center"]
    group = mark.group(mark.shapes(pack.brand_root(root)), f"translate({cx} {cy}) scale({placed['scale']})")
    # The ground is painted by the browser, as in the image itself: a mark smoothed against
    # transparency and laid on the ground afterwards differs in the last bit of an edge.
    under = f'  <rect x="0" y="0" width="{width}" height="{height}" fill="{drawing.ground}"/>\n' if drawing.ground else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">\n{under}{group}\n</svg>\n',
            drawing.ground)


def collect(root: Path = ROOT) -> Collected:
    """Return every picture the exporter owns, with its recipe."""
    data = pack.load(root)
    brand = pack.brand_root(root)
    out = Collected(data)

    # --- The profile images --------------------------------------------------------------
    for image in pack.images(data):
        drawing = source.ready(source.parse(root / image.source), brand, image.source.as_posix())
        out.sources[image.source] = drawing
        for output in image.outputs:
            limit = pack.limit(data, output.rule)
            described = records.image(root, data, image.source, output.file, output.rule, bool(drawing.fronts))
            out.drawings[output.file] = drawing
            if image.mark_alone is not None:
                out.references[output.file] = mark_alone_reference(root, drawing, image.mark_alone)
            out.pictures.append(Picture(
                output.file, output.px, drawn_from(drawing.svg, described), (image.source, pack.PACK_JSON, *brand_inputs(), *board_inputs(drawing)),
                _drawer(drawing, output.px, limit, output.file.stem, described), image.what, "image", described, limit, output.rule))

    # --- The repository cards ------------------------------------------------------------
    size = pack.card_size(data)
    rule = data["cards"]["rule"]
    for built in cards.cards(root, data):
        assert built.row.file is not None
        out.cards.append(built)
        out.drawings[built.row.file] = built.drawing
        described = records.card(root, data, built.row.repo, built.row.line, built.row.file, bool(built.drawing.fronts))
        out.pictures.append(Picture(
            built.row.file, size, drawn_from(built.drawing.svg, described), (*built.inputs, *brand_inputs(), *board_inputs(built.drawing)),
            _drawer(built.drawing, size, pack.limit(data, rule), built.row.file.stem, described),
            f"the card of {data['cards']['owner']}/{built.row.repo}", "card", described, pack.limit(data, rule), rule))

    # --- The README banners --------------------------------------------------------------
    banner_rule = readme_banners.section(data)["rule"]
    for built in readme_banners.banners(root, data):
        out.banners.append(built)
        body = built.svg.encode()
        out.pictures.append(Picture(
            built.path, readme_banners.PUBLISHED, drawn_from(built.svg, built.record), (*built.inputs, *brand_inputs(), *board_inputs(built.drawing)),
            lambda _browser, _drawn, body=body: body, f"the README banner of {data['cards']['owner']}/{built.row.repo}, {built.theme} theme",
            "banner", built.record, pack.limit(data, banner_rule), banner_rule, built.slug))

    # --- The previews --------------------------------------------------------------------
    shown = [picture for picture in out.pictures]
    for spec in data["previews"]:
        template = cards.card(root, data, pack.template_row(data))
        sheet = previews.Sheet(root, data, spec, shown, template)
        boards_shown = any(bool(out.drawings[picture.path].fronts) for picture in sheet.shown if picture.path in out.drawings)
        sheet.record = records.preview(root, spec, boards_shown or (sheet.kind == "cards" and bool(template.drawing.fronts)))
        out.pictures.append(Picture(
            Path(spec["file"]), (0, 0), drawn_from(sheet.digest, sheet.record), (pack.PACK_JSON, *sheet.inputs, *brand_inputs()),
            sheet.draw, spec["title"], "preview", sheet.record))
    return out


# --- The README's tables -----------------------------------------------------------------


def block_markers(name: str) -> tuple[str, str]:
    """Return the two comment lines a generated block of the README stands between."""
    return (f"<!-- BEGIN GENERATED: {name} (tools/export.py); do not edit by hand -->", f"<!-- END GENERATED: {name} -->")


def with_block(text: str, name: str, body: str) -> str:
    """Return *text* with its generated block *name* holding *body*."""
    begin, end = block_markers(name)
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise ValueError(f"README.md has no generated block {name!r}")
    return pattern.sub(lambda _: f"{begin}\n\n{body}\n\n{end}", text)


def blocks(collected: Collected, files: dict[str, Any]) -> dict[str, str]:
    """Return every generated block of the README, by name."""
    data = collected.data

    def weight(path: Path) -> str:
        entry = files.get(path.as_posix())
        return record.human_bytes(entry["bytes"]) if entry else "not built"

    def pixels(path: Path, size: tuple[int, int]) -> str:
        entry = files.get(path.as_posix())
        width, height = entry["size"] if entry else size
        return f"{width} x {height}"

    images = ["| File | Pixels | Weight | Where it goes | What it shows |", "| --- | --- | --- | --- | --- |"]
    for picture in collected.pictures:
        if picture.kind == "image":
            rule = data["rules"][picture.rule]
            images.append(f"| [`{picture.path}`]({picture.path}) | {pixels(picture.path, picture.size)} | {weight(picture.path)} |"
                          f" {rule['platform']}: {rule['where']} | {picture.what} |")

    card_rows = ["| Repository | File | Weight | Label | Line | Motif |", "| --- | --- | --- | --- | --- | --- |"]
    for built in collected.cards:
        row = built.row
        assert row.file is not None
        card_rows.append(f"| `{data['cards']['owner']}/{row.repo}` | [`{row.file}`]({row.file}) | {weight(row.file)} |"
                         f" {row.label.upper()} | {row.line} | [`{row.motif}`]({cards.motif_path(data, row.motif)}) |")

    rules = ["| Platform | Image | Upload | Limit | Formats | Crop | Keep inside | Read |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for rule in data["rules"].values():
        width, height = rule["upload_px"]
        rules.append(f"| {rule['platform']} | {rule['asset']} | {width} x {height}, {rule['ratio']} | under {record.human_bytes(rule['max_bytes'])} |"
                     f" {rule['formats']} | {rule['crop']} | {rule['safe_zone']} | [{rule['read']}]({rule['source']}). {rule['notes']} |")

    not_made = ["| Platform | Image | Why not |", "| --- | --- | --- |"]
    for entry in data["not_made"]:
        not_made.append(f"| {entry['platform']} | {entry['asset']} | {entry['why']} |")

    banner_rows = ["| Repository | Dark theme | Light theme | Label | Line | Motif | In its README |", "| --- | --- | --- | --- | --- | --- | --- |"]
    by_row: dict[str, dict[str, Picture]] = {}
    for picture in collected.pictures:
        if picture.kind == "banner":
            by_row.setdefault(picture.path.parent.name, {})[picture.path.stem.removeprefix("banner-")] = picture
    where = {"copy": "a copy in `.github/readme/`", "linked": "linked from here", "self": "read from here"}
    for row in readme_banners.rows(data):
        files_of = by_row.get(row.name, {})
        cells = [f"[{weight(files_of[theme].path)}]({files_of[theme].path})" if theme in files_of else "not built" for theme in sync_readme_banners.THEMES]
        banner_rows.append(f"| `{data['cards']['owner']}/{row.repo}` | {cells[0]} | {cells[1]} | {row.label.upper()} | {row.line} |"
                           f" [`{row.motif}`]({cards.motif_path(data, row.motif)}) | {where[row.mode]} |")

    preview_rows = ["| File | What it shows |", "| --- | --- |"]
    for spec in data["previews"]:
        preview_rows.append(f"| [`{spec['file']}`]({spec['file']}) | {spec['title']}. {spec['lede']} |")
    own = sync_readme_banners.row(data, readme_banners.REPO)
    banner = sync_readme_banners.picture(own, {theme: sync_readme_banners.master(data, own, theme) for theme in sync_readme_banners.THEMES})
    return {"banner": banner, "images": "\n".join(images), "cards": "\n".join(card_rows), "readme-banners": "\n".join(banner_rows),
            "rules": "\n".join(rules), "not-made": "\n".join(not_made), "previews": "\n".join(preview_rows)}


def readme(root: Path, collected: Collected, files: dict[str, Any]) -> str:
    """Return the README as it reads with its generated blocks current."""
    text = (root / pack.README).read_text(encoding="utf-8")
    for name, body in blocks(collected, files).items():
        text = with_block(text, name, body)
    return text


# --- Writing -----------------------------------------------------------------------------


def stale(root: Path, pictures: list[Picture]) -> list[Path]:
    """Return the files in the generated folders that nothing generates any more."""
    owned = {picture.path for picture in pictures}
    found = []
    for folder in GENERATED_DIRS:
        if (root / folder).is_dir():
            found += [path.relative_to(root) for path in sorted((root / folder).iterdir()) if path.is_file() and path.relative_to(root) not in owned]
    if (root / BANNER_DIR).is_dir():
        found += [path.relative_to(root) for path in sorted((root / BANNER_DIR).rglob("*")) if path.is_file() and path.relative_to(root) not in owned]
    return found


def dump(recorded: dict[str, Any]) -> str:
    """Return the record as the text of ``exports.json``."""
    return json.dumps({"$comment": COMMENT, **{key: value for key, value in recorded.items() if key != "$comment"}}, indent=2, ensure_ascii=False) + "\n"


def load_record(root: Path) -> dict[str, Any]:
    """Return the record at *root*, or an empty one."""
    path = root / pack.EXPORTS_JSON
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"files": {}}


def write(root: Path = ROOT) -> int:
    """Draw every picture and write the record and the README's tables."""
    collected = collect(root)
    for path in stale(root, collected.pictures):
        (root / path).unlink()
        print(f"removed {path}: nothing generates it")
    files: dict[str, Any] = {}
    drawn: dict[str, bytes] = {}
    with raster.Browser() as browser:
        for picture in collected.pictures:
            data = picture.draw(browser, drawn)
            drawn[picture.path.as_posix()] = data
            (root / picture.path).parent.mkdir(parents=True, exist_ok=True)
            (root / picture.path).write_bytes(data)
            files[picture.path.as_posix()] = {
                "sha256": record.sha256(data),
                "bytes": len(data),
                "size": list(picture.size if picture.kind == "banner" else png.size(data)),
                "drawn_from": picture.source,
                "inputs": {path.as_posix(): record.file_sha256(root / path) for path in picture.inputs},
            }
        version = browser.version
    (root / pack.EXPORTS_JSON).write_text(dump({"chromium": version, "files": files}), encoding="utf-8")
    (root / pack.README).write_text(readme(root, collected, files), encoding="utf-8")
    print(f"wrote {len(collected.pictures)} pictures, drawn with Chromium {version}")
    return 0


# --- Checking ----------------------------------------------------------------------------


def static_findings(root: Path = ROOT) -> list[str]:
    """Return every difference between the tree and what its sources give, found without a browser."""
    collected = collect(root)
    recorded = load_record(root)
    files = recorded.get("files", {})
    found = []
    page = root / pack.README
    if not page.is_file():
        found.append("README.md: missing")
    elif page.read_text(encoding="utf-8") != readme(root, collected, files):
        found.append("README.md: its tables are not what pack.json and the record give; run tools/export.py")
    for path in stale(root, collected.pictures):
        found.append(f"{path}: nothing generates it; run tools/export.py or remove it")
    for picture in collected.pictures:
        name = picture.path.as_posix()
        entry = files.get(name)
        path = root / picture.path
        if not path.is_file():
            found.append(f"{name}: missing; run tools/export.py")
            continue
        data = path.read_bytes()
        if picture.kind == "banner":
            found += banner_file_findings(name, data, picture)
        else:
            found += png.findings(name, data, picture.size if picture.kind != "preview" else None, picture.limit, picture.meta)
        if entry is None:
            found.append(f"{name}: exports.json has no record of it; run tools/export.py")
            continue
        if entry["sha256"] != record.sha256(data):
            found.append(f"{name}: its bytes are not the ones exports.json records; run tools/export.py")
        if entry["drawn_from"] != picture.source:
            found.append(f"{name}: stale: what it is drawn from changed since it was drawn; run tools/export.py")
        for origin, digest in entry["inputs"].items():
            if not (root / origin).is_file() or record.file_sha256(root / origin) != digest:
                found.append(f"{name}: stale: {origin} changed since it was drawn; run tools/export.py")
        if set(entry["inputs"]) != {path.as_posix() for path in picture.inputs}:
            found.append(f"{name}: stale: it is drawn from other files than the record names; run tools/export.py")
    for name in sorted(set(files) - {picture.path.as_posix() for picture in collected.pictures}):
        found.append(f"exports.json: records {name}, which nothing generates; run tools/export.py")
    return found


def banner_file_findings(name: str, data: bytes, picture: Picture) -> list[str]:
    """Return how a README banner's committed file differs from what its row gives: its weight, its metadata, its bytes."""
    found = []
    if picture.limit is not None and len(data) >= picture.limit:
        found.append(f"{name}: weighs {len(data):,} bytes; the limit is under {picture.limit:,}")
    found += meta.svg_findings(name, data.decode("utf-8", errors="replace"), picture.meta, picture.slug or "")
    if data != picture.draw(None, {}):  # type: ignore[arg-type]  # a banner needs no browser
        found.append(f"{name}: is not what its row, the template, its motif and brand give; run tools/export.py")
    return found


def drawn_findings(root: Path = ROOT, tolerant: bool = False, only: frozenset[str] | None = None,
                   browser: raster.Browser | None = None) -> list[str]:
    """Return every picture that, drawn again, is not the committed one.

    :param only: The pictures to draw again, by path; every one when ``None``.
    :param browser: A browser that is already open; one is opened for the run otherwise.
    """
    if browser is None:
        with raster.Browser() as opened:
            return drawn_findings(root, tolerant, only, opened)
    collected = collect(root)
    recorded = load_record(root)
    if not tolerant and browser.version != recorded.get("chromium"):
        return [
            f"this machine draws with Chromium {browser.version} and the pictures were drawn with {recorded.get('chromium')}:"
            " an exact comparison would report the browser, not the pictures. Install the pinned Playwright"
            " (requirements.txt, then 'python -m playwright install chromium'), or run --check --tolerant."
        ]
    found = []
    drawn: dict[str, bytes] = {}
    for picture in collected.pictures:
        path = root / picture.path
        if not path.is_file():
            continue
        kept = path.read_bytes()
        # A preview is drawn from the committed pictures, so one difference is reported once.
        drawn[picture.path.as_posix()] = kept
        if only is not None and picture.path.as_posix() not in only:
            continue
        again = picture.draw(browser, drawn)
        if picture.kind == "banner":
            # No browser draws a banner: its bytes are exact under any Chromium.
            if again != kept:
                found.append(f"{picture.path}: written again, it is not the committed file; run tools/export.py")
            continue
        if tolerant:
            share = png.drift(again, kept)
            if share is None or share > TOLERANCE:
                how = "is another size" if share is None else f"differs in {share:.2%} of its pixels"
                found.append(f"{picture.path}: drawn again under Chromium {browser.version}, it {how}; the limit is {TOLERANCE:.1%}")
            continue
        count = png.differing(again, kept)
        if count != 0:
            how = "is another size" if count is None else f"differs in {count} pixels"
            found.append(f"{picture.path}: drawn again, it {how}; run tools/export.py and look at it")
        reference = collected.references.get(picture.path)
        if reference is not None:
            alone = png.encode(png.clean(browser.draw(reference[0], picture.size, f"{picture.path.stem}-mark"), flatten=reference[1]))
            count = png.differing(alone, kept)
            if count != 0:
                how = "is another size" if count is None else f"differs in {count} pixels"
                found.append(f"{picture.path}: is not brand's mark drawn by itself: it {how}")
    return found


# --- A video's thumbnail, from the template ----------------------------------------------


def thumbnail(root: Path, lines: list[str], art: Path | None, browser: raster.Browser) -> bytes:
    """Return a one-off thumbnail: the template with *lines* as its title, and *art* in the room at its right."""
    from PIL import Image  # noqa: PLC0415

    tree = source.parse(root / THUMBNAIL)
    named = source.by_id(tree)
    targets = [named[key] for key in sorted(key for key in named if key.startswith("title."))]
    if not lines or len(lines) > len(targets):
        raise ValueError(f"a thumbnail's title has one to {len(targets)} lines, separated by '|'; this one has {len(lines)}")
    for index, target in enumerate(targets):
        if index < len(lines):
            source.set_words(target, lines[index])
        else:
            source.remove(tree, target)
    drawing = source.ready(tree, pack.brand_root(root), "the thumbnail")
    found = source.keep_findings(drawing)
    room = drawing.guides["art"]
    if art is not None:
        found += [f"the thumbnail: the words {name!r} ({placed.line.text!r}) reach into the picture's room; shorten the line or break it"
                  for name, placed in drawing.words.items() if placed.box()[2] > room[0]]
    if found:
        raise ValueError("\n".join(found))
    image = png.clean(browser.draw(drawing.svg, drawing.size, "thumbnail"), flatten=drawing.ground)
    if art is not None:
        with Image.open(art) as opened:
            picture = opened.convert("RGBA")
        width, height = int(room[2] - room[0]), int(room[3] - room[1])
        share = min(width / picture.width, height / picture.height)
        fitted = picture.resize((round(picture.width * share), round(picture.height * share)), Image.Resampling.LANCZOS)
        image.paste(fitted, (int(room[0]) + (width - fitted.width) // 2, int(room[1]) + (height - fitted.height) // 2), fitted)
    return fit_under(image, pack.limit(pack.load(root), "youtube-thumbnail"), records.thumbnail(root, lines))


def slug(lines: list[str]) -> str:
    """Return a file name made of a title's words."""
    return re.sub(r"[^a-z0-9]+", "-", " ".join(lines).lower()).strip("-")[:60] or "thumbnail"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    parser.add_argument("--static", action="store_true", help="with --check: only what needs no browser")
    parser.add_argument("--tolerant", action="store_true", help="with --check: draw again and fail on gross drift only")
    parser.add_argument("--title", help="draw a one-off thumbnail with this title; '|' breaks a line")
    parser.add_argument("--art", type=Path, help="with --title: a picture for the room at the thumbnail's right")
    parser.add_argument("--out", type=Path, default=Path("dist"), help="with --title: the folder to write to (default: dist)")
    args = parser.parse_args(argv)
    if args.title:
        lines = [part.strip() for part in args.title.split("|") if part.strip()]
        try:
            with raster.Browser() as browser:
                data = thumbnail(ROOT, lines, args.art, browser)
        except ValueError as error:
            print(error)
            return 1
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / f"{slug(lines)}.png"
        target.write_bytes(data)
        print(f"wrote {target} ({len(data):,} bytes)")
        return 0
    if not args.check:
        return write()
    found = static_findings()
    if not args.static:
        found += drawn_findings(tolerant=args.tolerant)
    for line in found:
        print(line)
    if found:
        print(f"\n{len(found)} finding(s).")
        return 1
    print("export check: every picture is what its sources give.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
