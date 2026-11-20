#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check that a repository's README shows its banner straight from social, or print the block it needs.

    tools/sync_readme_banners.py --check REPO [REPO ...]   exit 1 when a clone's README has no banner block,
                                                           a block with other addresses or another alt text,
                                                           or still keeps a copy of the banner
    tools/sync_readme_banners.py --print NAME              print the block for the banner row NAME, to paste
                                                           above the README's first level-1 heading
    --repo NAME                                            the row to use, for a clone whose origin does
                                                           not name it (one REPO only)

The banners are drawn here (``tools/export.py``, rows under
``readme_banners`` in ``pack.json``) and no repository keeps a copy: every
README reads the two files by their absolute address on this repository's
``main`` (``RAW``), so a change made here shows in every README at once,
private repositories included, as soon as GitHub's caches let it (about five
minutes; ``?v=N`` after an address forces a fresh read and is accepted
here). Those paths are a public contract: ``readme_banners.consumers`` in
``pack.json`` lists every README that reads them, and ``tools/check.py``
fails when a file one of them needs is missing.

The README's block stands between two markers, right above the first
level-1 heading, which stays the page's title. This tool never writes a
clone: a README changes in its own repository, by its own commit. Social's
own README is written by the exporter, with relative paths.

Standard library only: it runs with no virtual environment and no submodule.
A clone's row is found from its ``origin`` address through the consumers
(``jmrplens/kleidos`` reads ``kleidos``).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

#: This repository: the masters and pack.json are read from it.
SOCIAL = Path(__file__).resolve().parents[1]
OWNER = "kleidos-dev"
#: Where every README reads the masters from: this repository is public, and its main branch is the contract.
RAW = f"https://raw.githubusercontent.com/{OWNER}/social/main/"
THEMES = ("dark", "light")
BEGIN = "<!-- BEGIN GENERATED: banner (kleidos-dev/social, tools/sync_readme_banners.py); do not edit by hand -->"
END = "<!-- END GENERATED: banner -->"
#: A row's mode: ``raw`` (its README reads this repository's files by address) or ``self`` (social's own README).
MODES = ("raw", "self")
#: Where a repository used to keep its copy; a clone that still has one is told to remove it.
OLD_COPY = ".github/readme"
#: The cache-busting query a README may add to an address.
VERSION = re.compile(r"\?v=\d+(?=\")")
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
                    "mode": entry.get("mode", "raw"), "card": bool(card), **merged})
    return out


def row(data: dict[str, Any], repo: str) -> dict[str, Any]:
    """Return the banner row of *repo*."""
    for found in rows(data):
        if found["repo"] == repo:
            return found
    raise ValueError(f"pack.json has no README banner for the repository {repo!r}")


def consumers(data: dict[str, Any]) -> list[dict[str, str]]:
    """Return every README that reads a banner from here: its repository (``owner/name``) and the banner row it shows."""
    return list(data["readme_banners"].get("consumers", []))


def master(data: dict[str, Any], entry: dict[str, Any], theme: str) -> str:
    """Return the path, in this repository, of a row's banner for *theme*."""
    return f"{data['readme_banners']['out']}/{entry['name']}/banner-{theme}.svg"


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
    """Return the absolute addresses a repository's README reads its banner from."""
    return {theme: RAW + master(data, entry, theme) for theme in THEMES}


def block(data: dict[str, Any], entry: dict[str, Any]) -> str:
    """Return the whole block of a repository's README, markers included."""
    return f"{BEGIN}\n\n{picture(entry, sources_for(data, entry))}\n\n{END}"


def current_block(text: str) -> str | None:
    """Return the README's banner block, markers included, or None when it has none."""
    found = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), text, re.S)
    return found.group(0) if found else None


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


def origin_of(clone: Path) -> str:
    """Return the repository a clone's ``origin`` names, as ``owner/name``: ``.../kleidos-dev/boards.git`` is ``kleidos-dev/boards``."""
    try:
        url = subprocess.run(["git", "-C", str(clone), "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"{clone}: no origin to read the repository's name from; pass --repo NAME") from error
    found = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    if not found:
        raise ValueError(f"{clone}: cannot read a repository's name from {url!r}; pass --repo NAME")
    return f"{found.group(1)}/{found.group(2)}"


def resolve(data: dict[str, Any], clone: Path, repo: str | None) -> dict[str, Any]:
    """Return the banner row the README of the clone at *clone* shows."""
    if repo is None:
        origin = origin_of(clone)
        named = [consumer["banner"] for consumer in consumers(data) if consumer["repository"].lower() == origin.lower()]
        if not named:
            raise ValueError(f"{origin}: not a consumer in pack.json (readme_banners.consumers); add it there first")
        repo = named[0]
    entry = row(data, repo)
    if entry["mode"] == "self":
        raise ValueError(f"{entry['repo']}: its README's banner is written by tools/export.py, not checked by this tool")
    return entry


def findings(clone: Path, repo: str | None = None, social: Path = SOCIAL) -> list[str]:
    """Return how the README of the clone at *clone* differs from the block social gives it."""
    data = load_pack(social)
    try:
        entry = resolve(data, clone, repo)
    except ValueError as error:
        return [str(error)]
    where = entry["repo"]
    found = []
    if (clone / OLD_COPY).exists():
        found.append(f"{where}: {OLD_COPY}/ still holds a copy; README banners are read from social, so remove it")
    readme = clone / "README.md"
    if not readme.is_file():
        return [*found, f"{where}: README.md is missing"]
    text = readme.read_text(encoding="utf-8")
    present = current_block(text)
    if present is None:
        try:
            with_block(text, "")
        except ValueError as error:
            return [*found, f"{where}: README.md: {error}"]
        return [*found, f"{where}: README.md has no banner block; paste the output of tools/sync_readme_banners.py --print {where}"]
    if VERSION.sub("", present) != block(data, entry):
        found.append(f"{where}: README.md: its banner block is not the one social gives (addresses or alt text);"
                     f" paste the output of tools/sync_readme_banners.py --print {where}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", metavar="REPO", type=Path, nargs="+", help="check the README of the clones at REPO ...")
    mode.add_argument("--print", metavar="NAME", dest="show", help="print the block of the banner row NAME")
    parser.add_argument("--repo", help="the row to use, when a clone's origin does not name it")
    args = parser.parse_args(argv)
    if args.show is not None:
        try:
            print(block(load_pack(), row(load_pack(), args.show)))
        except ValueError as error:
            print(error)
            return 1
        return 0
    if args.repo and len(args.check) > 1:
        parser.error("--repo names the row of one clone")
    found = [line for clone in args.check for line in findings(clone.resolve(), args.repo)]
    for line in found:
        print(line)
    if found:
        print(f"\n{len(found)} finding(s).")
        return 1
    print(f"banners: {len(args.check)} README(s) current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
