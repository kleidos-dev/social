#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Hold the tree to its rules. Needs no browser; the pre-commit hook and CI run it.

    tools/check.py            check this repository
    tools/check.py --root X   check the copy of it at X (the tests plant defects in one)

What it holds:

- built:    every picture's bytes are the recorded ones, none is stale against its source, its row
            or the brand files it was drawn from, and the README's tables are current
            (tools/export.py --check --static);
- pack:     every repository has a card and every card a row; every file answers to a platform
            rule and weighs less than its limit; nothing in png/ or previews/ is unlisted;
- sources:  each source keeps brand's source rules (layers, plain shapes, token colors, the two
            families, no opacity, filter or picture) and opens with the license header; its
            lockup is the one brand's logo files draw;
- mark:     every copy of the mark is brand's, shape for shape; the keyhole is never drawn without
            its ring; an image of the mark alone holds the mark where pack.json says and nothing else;
- keep:     words, lockup, mark and motif stay inside each image's safe area, by geometry and on
            the painted pixels of every exported file; a card's safe area is inside the 1.91:1 crop;
- cards:    one template; each motif in the motifs' line language, inside its box and standing on
            the shelf; the words inside their column; the line still readable at 400 px, title and mark at 320;
- banners:  one template; each README banner's words inside their column and its motif on the shelf;
            the text block and the motif's box centred on the middle; the mark readable at 279 px,
            the line and the label at 823; the light file is the dark file plus its ground; each file
            is what its row gives, byte for byte, under the rule's weight; every file a README listed
            under readme_banners.consumers reads by its address is here, and every banner has a reader;
- brand:    TRADEMARKS.md is brand's, byte for byte; the submodule's address is brand's public
            one, https://github.com/kleidos-dev/brand.git;
- licenses: every declaration is GPL-3.0-or-later (the artwork and the pack's data) or MIT (the
            tooling and the commit-message gate); no font file and no picture out of place;
- metadata: every picture carries brand's metadata profile (kleidos_brand.meta), exactly as its
            record in tools/records.py gives it, before its pixels; its license and holders are
            REUSE.toml's for its path; no value holds an address, a path, a host, a machine's time or a
            tool's name, nor an identity pattern of the private deny-list (the KLEIDOS_DENY_EXTRA
            secret, or brand/tools/deny-local.txt; CI fails without it, a local run warns);
            tools/check_metadata.py runs this rule alone;
- public:   nothing private, no board drawing (the fronts are brand's copies, read through the
            submodule; the boards banner, svg/readme/boards/, draws them with their unlock screens as
            inner PNGs, as the boards card does in pixels), no registered-trademark sign.
"""
from __future__ import annotations

import argparse
import configparser
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cards  # noqa: E402
import export  # noqa: E402
import pack  # noqa: E402
import readme_banners  # noqa: E402
import records  # noqa: E402
import source  # noqa: E402
from kleidos_brand import SVG_HEADER, mark, meta, public_tree, svg_rules, tokens  # noqa: E402

ALLOWED_LICENSES = frozenset({"GPL-3.0-or-later", "MIT"})
#: The submodule's one address: brand's public repository.
BRAND_URL = "https://github.com/kleidos-dev/brand.git"
#: The project's contact and the supplier REUSE.toml names: the two addresses a file may hold.
ALLOWED_EMAILS = frozenset({"mail@kleidos.dev", "jmrplens@kleidos.dev"})
PICTURE_DIRS = ("png", "previews")
#: The folder of generated pictures that draw the board fronts, screens embedded: the boards banner.
BOARD_PICTURES = ("svg/readme/boards",)
#: The share of the canvas an image of the mark alone must fill with its ring, at least.
MARK_ALONE_FILL = 0.69


def tracked(root: Path) -> list[Path]:
    """Return this repository's own files: the brand submodule is its own project, with its own checks."""
    return [path for path in public_tree.tracked(root) if path.parts[0] != pack.BRAND.as_posix()]


def sources(root: Path) -> list[Path]:
    """Return every SVG source, relative to *root*."""
    return sorted(path.relative_to(root) for path in (root / pack.SRC_DIR).rglob("*.svg"))


def pack_findings(root: Path, data: dict[str, Any]) -> list[str]:
    found = cards.row_findings(data)
    found += readme_banners.row_findings(data)
    found += readme_banners.consumer_findings(root, data)
    listed: dict[str, str] = {}
    for image in pack.images(data):
        if not (root / image.source).is_file():
            found.append(f"pack.json: {image.source} does not exist")
        for output in image.outputs:
            name = output.file.as_posix()
            if name in listed:
                found.append(f"pack.json: {name} is listed twice")
            listed[name] = output.rule
            rule = data["rules"].get(output.rule)
            if rule is None:
                found.append(f"pack.json: {name} answers to the rule {output.rule!r}, which pack.json does not hold")
            elif list(output.px) != rule["upload_px"]:
                found.append(f"pack.json: {name} is {output.px[0]} x {output.px[1]}, and its rule asks for {rule['upload_px'][0]} x {rule['upload_px'][1]}")
    card_rule = data["rules"].get(data["cards"]["rule"])
    if card_rule is None or card_rule["upload_px"] != data["cards"]["px"] or card_rule["max_bytes"] > 1_000_000:
        found.append("pack.json: a card is drawn at its rule's size and weighs less than 1,000,000 bytes, GitHub's limit")
    used = {image.source for image in pack.images(data)} | {Path(data["cards"]["template"]), readme_banners.template(data)}
    used |= {cards.motif_path(data, row.motif) for row in [*pack.rows(data), pack.template_row(data)]}
    for path in sources(root):
        if path not in used and path.parent != Path(data["cards"]["motifs"]):
            found.append(f"{path}: no image of pack.json is drawn from this source")
    for rule in data["rules"].values():
        for key in ("platform", "asset", "upload_px", "max_bytes", "formats", "crop", "safe_zone", "where", "source", "read"):
            if key not in rule:
                found.append(f"pack.json: the rule for {rule.get('asset', '?')} does not say its {key}")
    return found


def source_findings(root: Path, files: list[Path]) -> list[str]:
    brand = pack.brand_root(root)
    values = tokens.resolve(tokens.load(brand))
    colors = tokens.palette(tokens.load(brand))
    inks = frozenset({values["social.ink"], values["social.light.ink"]})
    shapes = mark.shapes(brand)
    found = []
    # The mark's rule holds in every SVG of the tree, not only in the sources.
    for path in sorted({*files, *sources(root)}):
        if path.suffix == ".svg":
            found += mark.findings(root / path, shapes, inks, path.as_posix())
    for path in sources(root):
        name = path.as_posix()
        found += svg_rules.findings(root / path, colors, brand, name)
        if not (root / path).read_text(encoding="utf-8").startswith(SVG_HEADER):
            found.append(f"{name}: does not open with the license header")
        try:
            if not source.lockup_matches(source.parse(root / path), brand):
                found.append(f"{name}: its lockup is not the one brand's logo files draw; paste the group again from brand/logo/svg/kleidos-lockup-horizontal-for-dark.svg")
        except ET.ParseError:
            continue
    return found


def mark_alone_findings(collected: export.Collected) -> list[str]:
    found = []
    for image in pack.images(collected.data):
        if image.mark_alone is None:
            continue
        drawing = collected.sources[image.source]
        expected = (float(image.mark_alone["center"][0]), float(image.mark_alone["center"][1]), float(image.mark_alone["scale"]))
        if drawing.marks != [expected]:
            found.append(f"{image.source}: an image of the mark alone holds the mark once, at {expected}; it holds {drawing.marks}")
            continue
        if drawing.words or drawing.lockup is not None or drawing.motif is not None or drawing.shapes is not None:
            found.append(f"{image.source}: an image of the mark alone holds the mark and nothing else")
        ring = drawing.mark_boxes()[0]
        if (ring[2] - ring[0]) / drawing.size[0] < MARK_ALONE_FILL:
            found.append(f"{image.source}: the ring fills {(ring[2] - ring[0]) / drawing.size[0]:.0%} of the picture; alone, it fills at least {MARK_ALONE_FILL:.0%}")
    return found


def keep_findings(root: Path, collected: export.Collected) -> list[str]:
    found = []
    for drawing in collected.sources.values():
        found += source.keep_findings(drawing)
    for built in collected.cards:
        found += cards.card_findings(root, built)
    template = cards.card(root, collected.data, pack.template_row(collected.data))
    found += cards.card_findings(root, template)
    for built in collected.banners:
        found += readme_banners.banner_findings(root, built)
    for index in range(0, len(collected.banners), 2):
        found += readme_banners.pair_findings(collected.banners[index:index + 2])
    for path, drawing in collected.drawings.items():
        if (root / path).is_file():
            found += source.painted_findings(path.as_posix(), (root / path).read_bytes(), drawing)
    return found


def metadata_findings(root: Path, collected: export.Collected, only: set[str] | None = None) -> list[str]:
    """Return what in the pictures' metadata breaks the profile beyond its bytes (those are export.static_findings').

    :param only: Check these pictures alone (as the repository names them).
    """
    found = []
    identity, loaded = meta.identity_patterns()
    if loaded == "missing":
        if os.environ.get("GITHUB_ACTIONS") == "true":
            found.append(f"tools/check.py: M004: the private deny-list is not loaded; set the {meta.DENY_ENV} secret")
        else:
            print(f"warning: no private deny-list ({meta.DENY_ENV}, or {meta.DENY_LOCAL.name} in brand/tools/); identity patterns not checked",
                  file=sys.stderr)
    for picture in collected.pictures:
        name = picture.path.as_posix()
        if only is not None and name not in only:
            continue
        spdx, holders = meta.reuse_truth(root, picture.path)
        if (picture.meta.spdx, picture.meta.holders) != (spdx, holders):
            found.append(f"{name}: M003: its record says {picture.meta.spdx} by {picture.meta.holders}; REUSE.toml says {spdx} by {holders}")
        if picture.meta.own_license != records.OWN_LICENSE or records.OWN_LICENSE not in meta.spdx_ids(spdx):
            found.append(f"{name}: M003: the license of the artwork, {records.OWN_LICENSE}, is not in REUSE.toml's expression {spdx!r}")
        if picture.meta.digital_source_type != records.SOURCE_TYPE:
            found.append(f"{name}: M012: a picture of this pack is a digitalCreation, not a {picture.meta.digital_source_type}")
        found += meta.deny_findings(name, meta.xmp_values(picture.meta), identity)
    return found


def brand_findings(root: Path) -> list[str]:
    found = []
    ours, theirs = root / "TRADEMARKS.md", pack.brand_root(root) / "TRADEMARKS.md"
    if not ours.is_file() or ours.read_bytes() != theirs.read_bytes():
        found.append("TRADEMARKS.md: is not brand/TRADEMARKS.md, byte for byte; copy it again")
    modules = configparser.ConfigParser()
    modules.read(root / ".gitmodules", encoding="utf-8")
    section = 'submodule "brand"'
    if not modules.has_section(section) or modules.get(section, "url", fallback="") != BRAND_URL or modules.get(section, "path", fallback="") != "brand":
        found.append(f".gitmodules: brand is the submodule at brand/, with the address {BRAND_URL} and no other")
    text, copy = root / "LICENSE", root / "LICENSES" / "GPL-3.0-or-later.txt"
    if not text.is_file() or not copy.is_file() or text.read_bytes() != copy.read_bytes():
        found.append("LICENSE: is not the text of LICENSES/GPL-3.0-or-later.txt")
    return found


def findings(root: Path = pack.ROOT) -> list[str]:
    """Return everything in the tree at *root* that breaks a rule."""
    files = tracked(root)
    found: list[str] = []
    try:
        data = pack.load(root)
        found += pack_findings(root, data)
        found += cards.motif_findings(root, data)
    except (ValueError, KeyError, OSError) as error:
        return [f"pack.json cannot be read, so nothing else was checked: {error!r}"]
    found += source_findings(root, files)
    try:
        found += export.static_findings(root)
        collected = export.collect(root)
        found += mark_alone_findings(collected)
        found += keep_findings(root, collected)
        found += metadata_findings(root, collected)
    except (ValueError, KeyError, ET.ParseError, OSError, StopIteration) as error:
        found.append(f"the sources cannot be made ready, so nothing drawn was compared: {error}")
    found += brand_findings(root)
    found += public_tree.license_findings(root, files, ALLOWED_LICENSES)
    found += public_tree.font_findings(root, files, {})
    found += [line for line in public_tree.findings(root, files, PICTURE_DIRS, ALLOWED_EMAILS, board_dirs=BOARD_PICTURES)
              if not (line.endswith(": embeds a picture") and line.startswith(tuple(f"{folder}/" for folder in BOARD_PICTURES)))]
    return list(dict.fromkeys(found))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=pack.ROOT, help="the tree to check (default: this repository)")
    args = parser.parse_args(argv)
    found = findings(args.root.resolve())
    for line in found:
        print(line)
    if found:
        print(f"\n{len(found)} finding(s).")
        return 1
    print("check: the tree keeps its rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
