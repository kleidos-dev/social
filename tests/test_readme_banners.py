# SPDX-License-Identifier: MIT
"""The README banners: every row holds the system, the files are exact, and every README reads them from here."""
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


def test_a_line_too_long_for_the_column_is_found(data: dict) -> None:
    long = "The logo, type, colors, tokens, press kit and much more besides."
    row = dataclasses.replace(readme_banners.rows(data)[2], line=long, lines=(long,))
    found = readme_banners.banner_findings(ROOT, readme_banners.banner(ROOT, data, row, "dark"))
    assert any("'line.0'" in line and "text column" in line for line in found)


def test_the_name_is_set_once(built: list[readme_banners.Banner]) -> None:
    for banner in built:
        assert "title" not in banner.drawing.words, banner.path
        assert set(banner.drawing.words) <= {"label", "line.0", "line.1"}, banner.path


def test_every_text_block_sits_on_the_middle(data: dict) -> None:
    row = readme_banners.rows(data)[2]
    assert len(row.lines) == 1
    moved = readme_banners.compose(ROOT, data, row, "page")
    lockup = readme_banners.source.by_id(moved)["lockup"]
    assert readme_banners.source.placement(lockup)[1] > 168, "a one-line row moves its text block down"


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


# --- The check of each README ----------------------------------------------------------


README = "<!-- a comment that stays first -->\n\n# boards\n\nWhat it holds.\n\n```md\n# not a heading\n```\n"


def _clone(tmp_path: Path, name: str = "boards", readme: str = README, owner: str = "kleidos-dev") -> Path:
    clone = tmp_path / name
    clone.mkdir()
    (clone / "README.md").write_text(readme, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "remote", "add", "origin", f"https://github.com/{owner}/{name}.git"], check=True)
    return clone


def _with_block(clone: Path, data: dict, repo: str = "boards") -> None:
    readme = clone / "README.md"
    readme.write_text(sync.with_block(readme.read_text(), sync.block(data, sync.row(data, repo))), encoding="utf-8")


def test_the_block_reads_the_masters_by_their_raw_address(data: dict) -> None:
    text = sync.block(data, sync.row(data, "boards"))
    raw = "https://raw.githubusercontent.com/kleidos-dev/social/main/svg/readme/boards/"
    assert f'srcset="{raw}banner-dark.svg"' in text and f'src="{raw}banner-light.svg"' in text
    assert 'alt="Kleidos Boards: Drawings, measurements, schematics and 3D models of the boards Kleidos runs on."' in text
    assert "height=" not in text and ".github/readme" not in text


def test_a_current_readme_passes(tmp_path: Path, data: dict) -> None:
    clone = _clone(tmp_path)
    _with_block(clone, data)
    text = (clone / "README.md").read_text()
    assert text.startswith("<!-- a comment that stays first -->\n\n" + sync.BEGIN)
    assert text.index(sync.END) < text.index("# boards")
    assert sync.findings(clone) == []
    assert sync.main(["--check", str(clone)]) == 0


def test_a_cache_busting_query_is_accepted(tmp_path: Path, data: dict) -> None:
    clone = _clone(tmp_path)
    _with_block(clone, data)
    readme = clone / "README.md"
    readme.write_text(readme.read_text().replace('.svg"', '.svg?v=3"'), encoding="utf-8")
    assert sync.findings(clone) == []


@pytest.mark.parametrize("change", ["address", "alt", "copy"])
def test_check_finds_a_stale_block_or_a_leftover_copy(tmp_path: Path, data: dict, change: str) -> None:
    clone = _clone(tmp_path)
    _with_block(clone, data)
    readme = clone / "README.md"
    if change == "address":
        readme.write_text(readme.read_text().replace(sync.RAW, ".github/readme/", 1), encoding="utf-8")
    elif change == "alt":
        readme.write_text(readme.read_text().replace("Kleidos Boards:", "Kleidos boards:", 1), encoding="utf-8")
    else:
        (clone / ".github/readme").mkdir(parents=True)
        (clone / ".github/readme/banner-dark.svg").write_text("<svg/>", encoding="utf-8")
    assert sync.findings(clone), change
    assert sync.main(["--check", str(clone)]) == 1


def test_check_finds_a_missing_block(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    assert any("no banner block" in line for line in sync.findings(clone))


def test_check_never_writes(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    before = (clone / "README.md").read_bytes()
    sync.main(["--check", str(clone)])
    assert (clone / "README.md").read_bytes() == before


def test_the_firmware_is_found_through_its_consumer(tmp_path: Path, data: dict) -> None:
    clone = _clone(tmp_path, "kleidos", "# Kleidos\n\nFirmware.\n", owner="jmrplens")
    _with_block(clone, data, "kleidos")
    assert 'srcset="https://raw.githubusercontent.com/kleidos-dev/social/main/svg/readme/kleidos/banner-dark.svg"' in (clone / "README.md").read_text()
    assert sync.findings(clone) == []


def test_the_row_can_be_named(tmp_path: Path, data: dict) -> None:
    clone = tmp_path / "elsewhere"
    clone.mkdir()
    (clone / "README.md").write_text(sync.block(data, sync.row(data, "brand")) + "\n\n# brand\n", encoding="utf-8")
    assert sync.findings(clone, "brand") == []


def test_print_gives_the_block(capsys: pytest.CaptureFixture[str], data: dict) -> None:
    assert sync.main(["--print", "meter"]) == 0
    assert capsys.readouterr().out.strip() == sync.block(data, sync.row(data, "meter"))


def test_social_and_an_unknown_repository_are_refused(tmp_path: Path) -> None:
    assert any("tools/export.py" in line for line in sync.findings(_clone(tmp_path, "social", "# social\n"), "social"))
    assert any("not a consumer" in line for line in sync.findings(_clone(tmp_path, "nowhere", "# nowhere\n")))


def test_a_readme_with_no_heading_is_refused() -> None:
    with pytest.raises(ValueError, match="no level-1 heading"):
        sync.with_block("Just words.\n\n```\n# fenced\n```\n", "BLOCK")


def test_every_consumer_reads_a_banner_that_is_here(data: dict) -> None:
    assert readme_banners.consumer_findings(ROOT, data) == []
    assert {consumer["repository"] for consumer in sync.consumers(data)} >= {"jmrplens/kleidos", "kleidos-dev/boards", "kleidos-dev/.github"}


def test_a_banner_a_readme_reads_cannot_go(tmp_path: Path, data: dict) -> None:
    changed = json.loads(json.dumps(data))
    changed["readme_banners"]["consumers"].append({"repository": "kleidos-dev/elsewhere", "banner": "nothing"})
    assert any("no banner row has that name" in line for line in readme_banners.consumer_findings(ROOT, changed))
    empty = tmp_path / "social"
    empty.mkdir()
    found = readme_banners.consumer_findings(empty, data)
    assert any("svg/readme/boards/banner-dark.svg: missing" in line and "kleidos-dev/boards" in line for line in found)


def test_a_banner_no_readme_reads_is_found(data: dict) -> None:
    changed = json.loads(json.dumps(data))
    changed["readme_banners"]["consumers"] = [c for c in changed["readme_banners"]["consumers"] if c["banner"] != "posts"]
    assert any("no consumer reads the banner of posts" in line for line in readme_banners.consumer_findings(ROOT, changed))


def test_socials_own_readme_shows_its_masters() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.index('srcset="svg/readme/social/banner-dark.svg"') < text.index("\n# social\n")
