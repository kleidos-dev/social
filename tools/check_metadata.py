#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the embedded metadata of every picture of the pack, alone (tools/check.py runs it too).

    tools/check_metadata.py              every media file of the tree
    tools/check_metadata.py PATH ...     these files only
    tools/check_metadata.py --json       the findings as [{"path", "rule", "message"}]

Each finding reads ``path: Mxxx: message``, with the codes of brand's checker
(brand/tools/check_metadata.py): M001 a field missing, M002 a field that is not the
record's, M003 a license or holders REUSE does not give, M004 a deny-list hit, M005 a
chunk outside the profile, M006 an order error, M008 a media file with neither a record
nor a reason in METADATA_EXEMPT, M009 the wrong profile for the size, M012 the wrong
digital source type.

Exit status: 0 clean, 1 findings, 2 a usage or internal error. The private deny-list
comes from KLEIDOS_DENY_EXTRA or brand/tools/deny-local.txt (one pattern per line, never
committed); in CI a missing list is a finding, locally a warning.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check  # noqa: E402
import export  # noqa: E402
import pack  # noqa: E402
from kleidos_brand import meta  # noqa: E402

#: Every kind of file the metadata rule looks at, as brand's checker lists them.
MEDIA_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg", ".pdf", ".mp4", ".webm", ".mkv", ".glb", ".gltf",
                            ".obj", ".mtl", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".stl", ".ksm", ".wav", ".mp3", ".vtt", ".srt"})
#: The media files that carry no record of their own, and why.
METADATA_EXEMPT = (
    ("src/**", "the SVG sources the exporter reads, never published as they are: tools/check.py holds each to the source"
               " rules, its license header, a <title> and a <desc>"),
)
FINDING = re.compile(r"^(?P<path>[^:]+): (?P<rule>M\d{3}): (?P<message>.*)$")


def findings(root: Path, only: set[str] | None = None) -> list[str]:
    """Return every media file of the tree at *root* whose metadata is not what its record gives, or that has no record."""
    collected = export.collect(root)
    found = []
    pictures = {picture.path.as_posix(): picture for picture in collected.pictures}
    for name, picture in pictures.items():
        if only is not None and name not in only:
            continue
        path = root / picture.path
        if not path.is_file():
            found.append(f"{name}: M001: missing; run tools/export.py")
            continue
        if picture.kind == "banner":
            found += meta.svg_findings(name, path.read_text(encoding="utf-8"), picture.meta, picture.slug or "")
        else:
            found += meta.png_findings(name, path.read_bytes(), picture.meta)
    found += check.metadata_findings(root, collected, only)
    exempt = tuple(pattern for pattern, _ in METADATA_EXEMPT)
    for path in check.tracked(root):
        name = path.as_posix()
        if path.suffix.lower() not in MEDIA_SUFFIXES or (only is not None and name not in only) or meta.matches(name, exempt):
            continue
        if name not in pictures:
            found.append(f"{name}: M008: a media file with no metadata record and no reason in METADATA_EXEMPT")
    return list(dict.fromkeys(found))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("paths", nargs="*", help="files to check, relative to the repository (default: all)")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    parser.add_argument("--root", type=Path, default=pack.ROOT, help="the tree to check (default: this repository)")
    args = parser.parse_args(argv)
    try:
        only = {Path(path).as_posix() for path in args.paths} or None
        found = findings(args.root.resolve(), only)
    except Exception as error:  # noqa: BLE001 - any failure here is the checker's, reported as such
        print(f"check_metadata: internal error: {error}", file=sys.stderr)
        return 2
    if args.json:
        rows = []
        for line in found:
            match = FINDING.match(line)
            rows.append(match.groupdict() if match else {"path": "", "rule": "", "message": line})
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for line in found:
            print(line)
        print(f"\n{len(found)} finding(s)." if found else "metadata: every picture of the pack carries its record.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
