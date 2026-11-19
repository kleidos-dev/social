# SPDX-License-Identifier: MIT
"""The README banners: every row holds the system, the files are exact, and the sync tool copies them true."""
from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

import pack
import readme_banners
import sync_readme_banners as sync
from kleidos_brand import meta

ROOT = pack.ROOT


@pytest.fixture(scope="module")
def data() -> dict:
    return pack.load(ROOT)


@pytest.fixture(scope="module")
def built(data: dict) -> list[readme_banners.Banner]:
    return readme_banners.banners(ROOT, data)


def test_every_row_holds_the_system(built: list[readme_banners.Banner]) -> None:
    assert len(built) == 2 * len(readme_banners.rows(pack.load(ROOT)))
    for banner in built:
        assert readme_banners.banner_findings(ROOT, banner) == [], banner.path


def test_the_rows_are_clean(data: dict) -> None:
    assert readme_banners.row_findings(data) == []


def test_a_row_takes_its_words_from_its_card(data: dict) -> None:
    rows = {row.repo: row for row in readme_banners.rows(data)}
    cards = {row.repo: row for row in pack.rows(data)}
    for repo, card in cards.items():
        if repo in rows:
            assert (rows[repo].label, rows[repo].line, rows[repo].motif) == (card.label, card.line, card.motif)


def test_a_title_too_long_for_the_column_is_found(data: dict) -> None:
    row = dataclasses.replace(readme_banners.rows(data)[2], repo="documentation-sites")
    found = readme_banners.banner_findings(ROOT, readme_banners.banner(ROOT, data, row, "dark"))
    assert any("'title'" in line and "text column" in line for line in found)


def test_a_third_line_is_refused(data: dict) -> None:
    row = dataclasses.replace(readme_banners.rows(data)[2], lines=("one", "two", "three"))
    with pytest.raises(ValueError, match="room for one or 2"):
        readme_banners.compose(ROOT, data, row, "page")
    changed = json.loads(json.dumps(data))
    changed["readme_banners"]["repos"][2]["lines"] = ["The logo, type,", "colors, tokens", "and press kit."]
    assert any("has 3 lines" in line for line in readme_banners.row_findings(changed))


def test_lines_that_do_not_join_into_the_line_are_found(data: dict) -> None:
    changed = json.loads(json.dumps(data))
    changed["readme_banners"]["repos"][2]["lines"] = ["The logo and the press kit."]
    assert any("do not join" in line for line in readme_banners.row_findings(changed))


def test_a_row_that_repeats_its_card_is_found(data: dict) -> None:
    changed = json.loads(json.dumps(data))
    changed["readme_banners"]["repos"][2]["label"] = "Brand"
    assert any("repeats its card row's label" in line for line in readme_banners.row_findings(changed))


def test_a_row_with_no_card_and_no_words_is_found(data: dict) -> None:
    changed = json.loads(json.dumps(data))
    entry = next(entry for entry in changed["readme_banners"]["repos"] if entry["repo"] == "meter")
    del entry["motif"]
    assert any("no card to take its motif from" in line for line in readme_banners.row_findings(changed))


def test_two_exports_give_the_same_bytes(data: dict, built: list[readme_banners.Banner]) -> None:
    again = readme_banners.banners(ROOT, data)
    assert [banner.svg for banner in again] == [banner.svg for banner in built]


def test_each_committed_file_is_its_banner(built: list[readme_banners.Banner]) -> None:
    for banner in built:
        assert (ROOT / banner.path).read_text(encoding="utf-8") == banner.svg, banner.path


def test_the_metadata_is_the_record(built: list[readme_banners.Banner]) -> None:
    for banner in built:
        assert meta.svg_findings(banner.path.as_posix(), banner.svg, banner.record, banner.slug) == []
        assert banner.svg.startswith(readme_banners.HEADER)
        assert banner.slug == f"kl-readme-{banner.row.name}-{banner.theme}"
    first = built[0]
    tampered = first.svg.replace("README banner, dark theme</dc:title>", "README banner</dc:title>")
    assert meta.svg_findings("x.svg", tampered, first.record, first.slug) != []


def test_the_files_are_published_at_their_rule_and_under_its_weight(data: dict, built: list[readme_banners.Banner]) -> None:
    limit = pack.limit(data, data["readme_banners"]["rule"])
    for banner in built:
        assert 'viewBox="0 0 2560 800" width="1280" height="400"' in banner.svg
        assert len(banner.svg.encode()) < limit
        assert "<script" not in banner.svg and "<style" not in banner.svg and "<text" not in banner.svg


def test_the_light_file_is_the_dark_file_plus_its_ground(built: list[readme_banners.Banner]) -> None:
    for index in range(0, len(built), 2):
        pair = built[index:index + 2]
        assert readme_banners.pair_findings(pair) == []
    dark, light = (dataclasses.replace(banner) for banner in built[4:6])
    light.svg = light.svg.replace("#9aa3ad", "#9aa3ae", 1)
    assert readme_banners.pair_findings([dark, light]) != []


def test_only_the_boards_banner_embeds_pictures(built: list[readme_banners.Banner]) -> None:
    for banner in built:
        embeds = banner.svg.count("data:image/png;base64,")
        assert embeds == (9 if banner.row.repo == "boards" else 0), banner.path


# --- The sync tool ---------------------------------------------------------------------


README = "<!-- a comment that stays first -->\n\n# boards\n\nWhat it holds.\n\n```md\n# not a heading\n```\n"


def _clone(tmp_path: Path, name: str = "boards", readme: str = README) -> Path:
    clone = tmp_path / name
    clone.mkdir()
    (clone / "README.md").write_text(readme, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "remote", "add", "origin", f"https://github.com/kleidos-dev/{name}.git"], check=True)
    return clone


def test_write_copies_the_files_the_sums_and_the_block(tmp_path: Path, data: dict) -> None:
    clone = _clone(tmp_path)
    written = sync.write(clone)
    assert set(written) == {".github/readme/banner-dark.svg", ".github/readme/banner-light.svg", ".github/readme/SHA256SUMS", "README.md"}
    for theme in sync.THEMES:
        assert (clone / f".github/readme/banner-{theme}.svg").read_bytes() == (ROOT / f"svg/readme/boards/banner-{theme}.svg").read_bytes()
    sums = (clone / ".github/readme/SHA256SUMS").read_text()
    assert "  .github/readme/banner-dark.svg\n" in sums and "  .github/readme/banner-light.svg\n" in sums
    text = (clone / "README.md").read_text()
    assert text.startswith("<!-- a comment that stays first -->\n\n" + sync.BEGIN)
    assert text.index(sync.END) < text.index("# boards")
    assert 'srcset=".github/readme/banner-dark.svg"' in text and 'alt="Kleidos Boards: Drawings' in text
    assert "height=" not in text.split(sync.END)[0]
    assert sync.write(clone) == []
    assert sync.findings(clone) == []
    shasum = subprocess.run(["shasum", "-a", "256", "-c", ".github/readme/SHA256SUMS"], cwd=clone, capture_output=True, text=True)
    assert shasum.returncode == 0, shasum.stdout + shasum.stderr


@pytest.mark.parametrize("change", ["copy", "sums", "block"])
def test_check_finds_a_stale_copy_sums_or_block(tmp_path: Path, change: str) -> None:
    clone = _clone(tmp_path)
    sync.write(clone)
    if change == "copy":
        target = clone / ".github/readme/banner-light.svg"
        target.write_bytes(target.read_bytes().replace(b"#0a0c0f", b"#0a0c0e", 1))
    elif change == "sums":
        target = clone / ".github/readme/SHA256SUMS"
        target.write_text(target.read_text().splitlines()[0] + "\n")
    else:
        target = clone / "README.md"
        target.write_text(target.read_text().replace("Kleidos Boards:", "Kleidos boards:", 1))
    found = sync.findings(clone)
    assert found, change
    assert sync.main(["--check", str(clone)]) == 1


def test_check_finds_a_missing_block(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    assert any("no banner block" in line for line in sync.findings(clone))


def test_a_linked_row_writes_no_file(tmp_path: Path, data: dict) -> None:
    clone = _clone(tmp_path, "kleidos", "# Kleidos\n\nFirmware.\n")
    assert sync.write(clone) == ["README.md"]
    assert not (clone / ".github").exists()
    text = (clone / "README.md").read_text()
    assert 'srcset="https://github.com/kleidos-dev/social/raw/main/svg/readme/kleidos/banner-dark.svg"' in text
    assert sync.findings(clone) == []


def test_the_row_can_be_named(tmp_path: Path) -> None:
    clone = tmp_path / "elsewhere"
    clone.mkdir()
    (clone / "README.md").write_text("# brand\n", encoding="utf-8")
    assert "README.md" in sync.write(clone, "brand")
    assert sync.findings(clone, "brand") == []


def test_social_and_an_unknown_repository_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tools/export.py"):
        sync.write(_clone(tmp_path, "social", "# social\n"))
    with pytest.raises(ValueError, match="no README banner"):
        sync.write(_clone(tmp_path, "nowhere", "# nowhere\n"))


def test_a_readme_with_no_heading_is_refused() -> None:
    with pytest.raises(ValueError, match="no level-1 heading"):
        sync.with_block("Just words.\n\n```\n# fenced\n```\n", "BLOCK")


def test_socials_own_readme_shows_its_masters() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.index('srcset="svg/readme/social/banner-dark.svg"') < text.index("\n# social\n")
