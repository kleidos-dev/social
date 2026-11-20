# SPDX-License-Identifier: MIT
"""What every picture of the pack says about itself: the record its metadata is written from.

Each PNG the exporter writes carries brand's metadata profile
(``kleidos_brand.meta``): a title, a description, its creator, its copyright
line, its license and where it lives. The values come from ``pack.json`` (a
rule's platform and asset, a card's repository and line, a preview's title and
lede) and from the source's ``<desc>``; nothing is typed per file here, and no
date or machine trace goes in.

The license and the holders are this repository's ``REUSE.toml`` for the
picture's path: the artwork is GPL-3.0-or-later, the work of José M. Requena
Plens. What the pictures draw from others is credited, not licensed: the words
are set in Mona Sans (SIL Open Font License 1.1), and the nine boards are
brand's copies of the boards repository's drawings (MIT, the same author), of
M5Stack's and LILYGO's products.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pack  # noqa: F401  (puts brand/tools on the path)
from kleidos_brand import meta

REPO = "social"
#: The license of everything the pack draws; REUSE.toml must agree (tools/check.py).
OWN_LICENSE = "GPL-3.0-or-later"

FONT_CREDIT = ("Lettering set in Mona Sans, © 2022 The Mona Sans Project Authors, with Reserved Font Name \"Mona\","
               " SIL Open Font License 1.1.")
BOARDS_CREDIT = ("Board drawings: the kleidos-dev/boards front drawings, as brand copies them, MIT,"
                 " © 2026 José M. Requena Plens; each panel shows its own unlock screen.")
#: The terms the GPL carries here, 7(c) and 7(e). Brand's press permission does not reach these
#: images (NOTICE.md), so the sentence names section 7 alone.
EXTRA_TERMS = f"Additional terms under GPL section 7: {meta.RIGHTS_URLS[REPO]}."
#: What every picture is: drawn with non-generative tools (IPTC digital source type).
SOURCE_TYPE = "digitalCreation"


def desc(path: Path) -> str:
    """Return the ``<desc>`` of the SVG source at *path*."""
    tree = ET.fromstring(path.read_text(encoding="utf-8"))
    for child in tree:
        if child.tag.rsplit("}", 1)[-1] == "desc" and child.text:
            return " ".join(child.text.split())
    raise ValueError(f"{path.name}: has no <desc>; every source says what it shows")


def _first_lower(text: str) -> str:
    return text[:1].lower() + text[1:]


def build(root: Path, path: Path, title: str, description: str, keywords: tuple[str, ...], boards: bool,
          alt: str | None = None) -> Any:
    """Return the metadata record of the picture at *path*.

    :param boards: Whether the picture shows the nine boards, which brings their credit and the vendors' trademark notes.
    """
    spdx, holders = meta.reuse_truth(root, path)
    credits = (FONT_CREDIT, *((BOARDS_CREDIT,) if boards else ()))
    trademarks = (meta.TRADEMARK_NOTE_KLEIDOS, *((meta.TRADEMARK_NOTE_M5, meta.TRADEMARK_NOTE_LILYGO) if boards else ()))
    return meta.MediaMeta(
        title=title,
        description=description,
        alt=alt if alt is not None else description,
        keywords=tuple(dict.fromkeys((*meta.BASE_KEYWORDS, *keywords))),
        digital_source_type=SOURCE_TYPE,
        spdx=spdx,
        own_license=OWN_LICENSE,
        holders=holders,
        credits=credits,
        trademarks=trademarks,
        extra_terms=(EXTRA_TERMS,),
        identifier_url=meta.identifier_url(REPO, path),
        rights_url=meta.RIGHTS_URLS[REPO],
        language="en",
        repo=REPO,
    )


def image(root: Path, data: dict[str, Any], source: Path, file: Path, rule_name: str, boards: bool) -> Any:
    """Return the record of a profile image: titled for its platform and use, described by its source."""
    rule = data["rules"][rule_name]
    platform = rule["platform"].split(" (")[0]
    title = f"Kleidos {platform} {_first_lower(rule['asset'])}"
    return build(root, file, title, desc(root / source), (platform, _first_lower(rule["asset"].split(" (")[0])), boards)


def card(root: Path, data: dict[str, Any], repo: str, line: str, file: Path, boards: bool) -> Any:
    """Return the record of a repository's card: its repository and its line."""
    owner = data["cards"]["owner"]
    alt = f"The social preview card of {owner}/{repo}: the Kleidos logo, the name {repo} and the line \"{line}\""
    return build(root, file, f"{owner}/{repo} social preview card", line, (f"{owner}/{repo}", "GitHub", "social preview card"),
                 boards, alt)


def preview(root: Path, spec: dict[str, Any], boards: bool) -> Any:
    """Return the record of a preview sheet: its title and its lede."""
    return build(root, Path(spec["file"]), f"Kleidos pack preview: {_first_lower(spec['title'])}", spec["lede"],
                 ("social pack", "preview"), boards)


def thumbnail(root: Path, lines: list[str]) -> Any:
    """Return the record of a one-off video thumbnail drawn from the template with the title *lines*."""
    title = " ".join(lines)
    named = f"{title} - Kleidos video thumbnail"
    return build(root, Path("src/youtube/thumbnail.svg"), named if len(named.encode()) <= 64 else title,
                 f"The thumbnail of the Kleidos video \"{title}\": the horizontal logo and the video's title.",
                 ("YouTube", "video thumbnail"), False)


def readme_banner(root: Path, data: dict[str, Any], row: Any, theme: str, file: Path, boards: bool) -> Any:
    """Return the record of a README banner: its repository, its label, its line and its theme.

    Every README reads the master itself, by its address on this repository's main branch, so its
    identifier names the master here, the one public address it has.
    """
    owner = data["cards"]["owner"]
    description = (f"The README banner of {owner}/{row.repo}: the Kleidos logo, the label \"{row.label}\""
                   f" and the line \"{row.line}\"")
    return build(root, file, f"{owner}/{row.repo} README banner, {theme} theme", description,
                 (f"{owner}/{row.repo}", "GitHub", "README banner"), boards, f"Kleidos {row.label}: {row.line}")
