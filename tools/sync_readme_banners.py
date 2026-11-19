#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Copy a repository's README banner into its clone, or check that the copy there is current.

    tools/sync_readme_banners.py --write REPO              copy that repository's two banners into
                                                           REPO/.github/readme/, write SHA256SUMS beside
                                                           them, and put the banner's block at the top of
                                                           REPO/README.md
    tools/sync_readme_banners.py --check REPO [REPO ...]   exit 1 when a copy, its SHA256SUMS or the
                                                           README's block is stale or missing
    --repo NAME                                            the row to use, for a clone whose origin does
                                                           not name it (one REPO only)

The banners are drawn here (``tools/export.py``, rows under ``readme_banners``
in ``pack.json``) and land in each repository as byte copies, so a private
repository, a clone and a fork all show them. The README's block stands
between two generated markers, right above the first level-1 heading, which
stays the page's title. A row whose mode is ``linked`` gets the block with
this repository's public addresses and no file; social's own README is
written by the exporter (mode ``self``).

Standard library only: it runs with no virtual environment and no submodule.
The row is found from the clone's ``origin`` address (``.../boards.git`` is
``boards``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

#: This repository: the masters and pack.json are read from it.
SOCIAL = Path(__file__).resolve().parents[1]
OWNER = "kleidos-dev"
#: Where a linked README reads the masters from: this repository is public.
RAW = f"https://github.com/{OWNER}/social/raw/main/"
THEMES = ("dark", "light")
BEGIN = "<!-- BEGIN GENERATED: banner (kleidos-dev/social, tools/sync_readme_banners.py); do not edit by hand -->"
END = "<!-- END GENERATED: banner -->"
SUMS = "SHA256SUMS"
MODES = ("copy", "linked", "self")
HEADING = re.compile(r"^# \S")
FENCE = re.compile(r"^(```|~~~)")


def load_pack(root: Path = SOCIAL) -> dict[str, Any]:
    """Return ``pack.json`` of the social tree at *root*."""
    return json.loads((root / "pack.json").read_text(encoding="utf-8"))


def name_of(repo: str) -> str:
    """Return the folder a repository's files take its name as: ``.github`` is ``dot-github``."""
    return repo.replace(".", "dot-", 1) if repo.startswith(".") else repo


def rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every banner row, with its label, line and motif taken from its card row when it has one."""
    cards = {entry["repo"]: entry for entry in data["cards"]["repos"]}
    out = []
    for entry in data["readme_banners"]["repos"]:
        card = cards.get(entry["repo"], {})
        merged = {key: entry.get(key, card.get(key)) for key in ("label", "line", "motif")}
        out.append({"repo": entry["repo"], "name": name_of(entry["repo"]), "lines": list(entry["lines"]),
                    "mode": entry.get("mode", "copy"), "card": bool(card), **merged})
    return out


def row(data: dict[str, Any], repo: str) -> dict[str, Any]:
    """Return the banner row of *repo*."""
    for found in rows(data):
        if found["repo"] == repo:
            return found
    raise ValueError(f"pack.json has no README banner for the repository {repo!r}")


def master(data: dict[str, Any], entry: dict[str, Any], theme: str) -> str:
    """Return the path, in this repository, of a row's banner for *theme*."""
    return f"{data['readme_banners']['out']}/{entry['name']}/banner-{theme}.svg"


def copy_path(data: dict[str, Any], theme: str) -> str:
    """Return where a banner's copy lands in its repository."""
    return f"{data['readme_banners']['dest']}/banner-{theme}.svg"


def alt(entry: dict[str, Any]) -> str:
    """Return a banner's alt text: what it is for, not the shapes it holds."""
    return f"Kleidos {entry['label']}: {entry['line']}"


def _attribute(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def picture(entry: dict[str, Any], sources: dict[str, str]) -> str:
    """Return the ``<picture>`` a README shows a banner with: a source per theme, the light file as the fallback."""
    return "\n".join([
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="{sources["dark"]}">',
        f'  <source media="(prefers-color-scheme: light)" srcset="{sources["light"]}">',
        f'  <img src="{sources["light"]}" width="100%" alt="{_attribute(alt(entry))}">',
        "</picture>",
    ])


def sources_for(data: dict[str, Any], entry: dict[str, Any]) -> dict[str, str]:
    """Return the addresses a repository's README reads its banner from."""
    if entry["mode"] == "linked":
        return {theme: RAW + master(data, entry, theme) for theme in THEMES}
    return {theme: copy_path(data, theme) for theme in THEMES}


def block(data: dict[str, Any], entry: dict[str, Any]) -> str:
    """Return the whole generated block of a repository's README, markers included."""
    return f"{BEGIN}\n\n{picture(entry, sources_for(data, entry))}\n\n{END}"


def with_block(text: str, generated: str) -> str:
    """Return a README with *generated* between its markers, or, the first time, right above its first level-1 heading."""
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        return pattern.sub(lambda _: generated, text, count=1)
    if BEGIN in text or END in text:
        raise ValueError("README.md holds one of the banner's markers without the other")
    fenced = False
    offset = 0
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and HEADING.match(line):
            return text[:offset] + generated + "\n\n" + text[offset:]
        offset += len(line)
    raise ValueError("README.md has no level-1 heading to put the banner above, and no banner block")


def digest(data: bytes) -> str:
    """Return the SHA-256 of *data*, in hexadecimal."""
    return hashlib.sha256(data).hexdigest()


def expected(data: dict[str, Any], entry: dict[str, Any], social: Path = SOCIAL) -> dict[str, bytes]:
    """Return the files a repository's banner gives it (README excepted), by path in that repository."""
    if entry["mode"] != "copy":
        return {}
    files = {copy_path(data, theme): (social / master(data, entry, theme)).read_bytes() for theme in THEMES}
    sums = "".join(f"{digest(body)}  {path}\n" for path, body in files.items())
    files[f"{data['readme_banners']['dest']}/{SUMS}"] = sums.encode()
    return files


def origin_name(clone: Path) -> str:
    """Return the repository a clone's ``origin`` names: ``.../boards.git`` is ``boards``."""
    try:
        url = subprocess.run(["git", "-C", str(clone), "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"{clone}: no origin to read the repository's name from; pass --repo NAME") from error
    name = re.sub(r"\.git$", "", url.rstrip("/")).rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if not name:
        raise ValueError(f"{clone}: cannot read a repository's name from {url!r}; pass --repo NAME")
    return name


def resolve(data: dict[str, Any], clone: Path, repo: str | None) -> dict[str, Any]:
    """Return the row of the repository at *clone*."""
    entry = row(data, repo or origin_name(clone))
    if entry["mode"] == "self":
        raise ValueError(f"{entry['repo']}: its README's banner is written by tools/export.py, not by this tool")
    return entry


def write(clone: Path, repo: str | None = None, social: Path = SOCIAL) -> list[str]:
    """Bring the banner of the repository at *clone* up to date, and return what was written."""
    data = load_pack(social)
    entry = resolve(data, clone, repo)
    written = []
    for path, body in expected(data, entry, social).items():
        target = clone / path
        if not target.is_file() or target.read_bytes() != body:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            written.append(path)
    readme = clone / "README.md"
    text = readme.read_text(encoding="utf-8")
    updated = with_block(text, block(data, entry))
    if updated != text:
        readme.write_text(updated, encoding="utf-8")
        written.append("README.md")
    return written


def findings(clone: Path, repo: str | None = None, social: Path = SOCIAL) -> list[str]:
    """Return how the banner of the repository at *clone* differs from what social gives it."""
    data = load_pack(social)
    try:
        entry = resolve(data, clone, repo)
    except ValueError as error:
        return [str(error)]
    where = entry["repo"]
    found = []
    for path, body in expected(data, entry, social).items():
        target = clone / path
        if not target.is_file():
            found.append(f"{where}: {path} is missing; run tools/sync_readme_banners.py --write")
        elif target.read_bytes() != body:
            found.append(f"{where}: {path} is not social's; run tools/sync_readme_banners.py --write")
    if entry["mode"] == "linked":
        stray = [path for path in (copy_path(data, theme) for theme in THEMES) if (clone / path).exists()]
        found += [f"{where}: {path} exists, and a linked banner has no copy" for path in stray]
    readme = clone / "README.md"
    if not readme.is_file():
        return [*found, f"{where}: README.md is missing"]
    text = readme.read_text(encoding="utf-8")
    try:
        current = with_block(text, block(data, entry)) == text
    except ValueError as error:
        current = False
        found.append(f"{where}: README.md: {error}")
    if not current and BEGIN in text:
        found.append(f"{where}: README.md: its banner block is not the one social gives; run tools/sync_readme_banners.py --write")
    elif not current and BEGIN not in text:
        found.append(f"{where}: README.md has no banner block; run tools/sync_readme_banners.py --write")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", metavar="REPO", type=Path, help="copy the banner into the clone at REPO")
    mode.add_argument("--check", metavar="REPO", type=Path, nargs="+", help="check the clones at REPO ...")
    parser.add_argument("--repo", help="the row to use, when a clone's origin does not name it")
    args = parser.parse_args(argv)
    if args.write is not None:
        try:
            written = write(args.write.resolve(), args.repo)
        except (ValueError, OSError) as error:
            print(error)
            return 1
        print("\n".join(f"wrote {path}" for path in written) or "already current")
        return 0
    if args.repo and len(args.check) > 1:
        parser.error("--repo names the row of one clone")
    found = [line for clone in args.check for line in findings(clone.resolve(), args.repo)]
    for line in found:
        print(line)
    if found:
        print(f"\n{len(found)} finding(s).")
        return 1
    print(f"banners: {len(args.check)} clone(s) current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
