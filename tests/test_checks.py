# SPDX-License-Identifier: MIT
"""The checks catch what they are for: each test plants one defect in a copy of the tree."""
from __future__ import annotations

import io
import json
import random
import shutil
from pathlib import Path

import check
import pack
from kleidos_brand import SVG_HEADER

ROOT = Path(__file__).resolve().parents[1]

# Private data the tests plant, put together here so that this file holds none.
HOME_PATH = "/Us" + "ers/" + "someone/notes.txt"
PRIVATE_ADDRESS = "192." + "168.1.20"
OTHER_EMAIL = "someone" + "@" + "elsewhere.org"
LOCAL_BRAND = "/Us" + "ers/" + "someone/GIT/brand"
# REUSE-IgnoreStart
CC_TAG = "SPDX-License-Identifier: CC-BY-SA-4.0"
# REUSE-IgnoreEnd


def found(tree: Path, *needles: str) -> bool:
    """Tell whether the check reports a finding that holds every needle."""
    return any(all(needle in line for needle in needles) for line in check.findings(tree))


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} does not hold {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def edit_pack(tree: Path, change) -> None:
    data = json.loads((tree / "pack.json").read_text(encoding="utf-8"))
    change(data)
    (tree / "pack.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_the_tree_as_committed_is_clean() -> None:
    assert check.findings(ROOT) == []


def test_a_copy_of_the_tree_is_clean(tree: Path) -> None:
    assert check.findings(tree) == []


def test_a_copy_with_its_own_brand_is_clean(tree_with_brand: Path) -> None:
    assert check.findings(tree_with_brand) == []


# --- The mark ----------------------------------------------------------------------------


def test_a_ringless_glyph_is_refused(tree: Path) -> None:
    edit(tree / "src/youtube/banner.svg", '<g id="guides">',
         '<g id="guides">\n    <rect x="20" y="20" width="40" height="76" rx="20" fill="#00d2ff"/>')
    assert found(tree, "src/youtube/banner.svg", "never drawn without its ring")


def test_a_keyhole_made_of_the_marks_own_shapes_is_refused(tree: Path) -> None:
    drawing = (tree / "brand/logo/src/mark.svg").read_text(encoding="utf-8")
    ring = next(line for line in drawing.splitlines() if 'r="42"' in line)
    (tree / "keyhole.svg").write_text(drawing.replace(ring + "\n", ""), encoding="utf-8")
    assert found(tree, "keyhole.svg", "never drawn without its ring")


def test_a_recolored_mark_is_refused(tree: Path) -> None:
    edit(tree / "src/shared/avatar.svg", 'stroke="#00D2FF" stroke-width="3"', 'stroke="#51cf66" stroke-width="3"')
    assert found(tree, "src/shared/avatar.svg", "recolored")


def test_a_redrawn_mark_is_refused(tree: Path) -> None:
    edit(tree / "src/youtube/watermark.svg", '<circle cx="0" cy="0" r="42"', '<circle cx="0" cy="0" r="40"')
    assert found(tree, "src/youtube/watermark.svg", "redrawn")


def test_a_lockup_that_is_not_brands_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/card.svg", 'class="lettering" fill="#eceef1"', 'class="lettering" fill="#9aa3ad"')
    assert found(tree, "src/cards/card.svg", "its lockup is not the one brand's logo files draw")


def test_a_mark_alone_with_company_is_refused(tree: Path) -> None:
    edit(tree / "src/shared/avatar.svg", "  </g>\n  <g id=\"guides\">",
         '    <rect x="400" y="900" width="200" height="20" fill="#eceef1"/>\n  </g>\n  <g id="guides">')
    assert found(tree, "src/shared/avatar.svg", "the mark and nothing else")


def test_a_mark_alone_moved_is_refused(tree: Path) -> None:
    edit(tree / "src/shared/avatar.svg", "translate(500 500) scale(8)", "translate(500 500) scale(7)")
    assert found(tree, "src/shared/avatar.svg", "holds the mark once, at")


# --- Keep zones --------------------------------------------------------------------------


def test_a_word_outside_the_safe_area_is_refused(tree: Path) -> None:
    edit(tree / "src/youtube/banner.svg", '<text id="line.0" x="615"', '<text id="line.0" x="1615"')
    assert found(tree, "src/youtube/banner.svg", "'line.0'", "reaches outside the safe area")


def test_a_lockup_outside_the_safe_area_is_refused(tree: Path) -> None:
    edit(tree / "src/makertube/banner.svg", "translate(291 116)", "translate(91 116)")
    assert found(tree, "src/makertube/banner.svg", "the lockup reaches outside the safe area")


def test_pixels_painted_outside_the_safe_area_are_refused(tree: Path) -> None:
    from PIL import Image

    path = tree / "png/youtube/banner.png"
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    image.putpixel((10, 10), (255, 255, 255))
    image.save(path)
    assert found(tree, "png/youtube/banner.png", "outside its safe area")


# --- Cards -------------------------------------------------------------------------------


def test_a_card_over_the_limit_is_refused(tree: Path) -> None:
    from PIL import Image

    noise = Image.frombytes("RGB", (2560, 1280), random.Random(7).randbytes(2560 * 1280 * 3))
    buffer = io.BytesIO()
    noise.save(buffer, "PNG")
    assert len(buffer.getvalue()) >= 1_000_000
    (tree / "png/github/kleidos.png").write_bytes(buffer.getvalue())
    assert found(tree, "png/github/kleidos.png", "the limit is under 1,000,000")


def test_a_motif_off_the_shelf_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/motifs/typing.svg", 'y="254" width="788" height="220"', 'y="234" width="788" height="220"')
    assert found(tree, "motifs/typing.svg", "does not stand on the shelf")


def test_a_motif_outside_its_box_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/motifs/frames.svg", 'x="6" y="31" width="788"', 'x="6" y="31" width="808"')
    assert found(tree, "motifs/frames.svg", "reaches outside its 800 x 480 box")


def test_a_motif_in_another_line_is_refused(tree: Path) -> None:
    path = tree / "src/cards/motifs/checklist.svg"
    path.write_text(path.read_text(encoding="utf-8").replace('stroke-width="12"', 'stroke-width="5"', 1), encoding="utf-8")
    assert found(tree, "motifs/checklist.svg", "a motif's lines are 12 px")


def test_a_motif_in_another_color_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/motifs/bubbles.svg", 'fill="#0f3460"', 'fill="#51cf66"')
    assert found(tree, "motifs/bubbles.svg", "a motif's fills are the social palette's")


def test_a_line_that_reaches_the_motif_is_refused(tree: Path) -> None:
    def longer(data) -> None:
        row = data["cards"]["repos"][0]
        row["line"] = "Free firmware that turns an ESP32 board into a hardware password manager."
        row["lines"] = ["Free firmware that turns an ESP32 board into a", "hardware password manager."]

    edit_pack(tree, longer)
    assert found(tree, "the card of kleidos", "reach outside the text column")


def test_lines_that_do_not_spell_the_line_are_refused(tree: Path) -> None:
    edit_pack(tree, lambda data: data["cards"]["repos"][1]["lines"].pop())
    assert found(tree, "the card of boards", "do not join into its line")


def test_a_title_too_small_at_320_px_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/card.svg", '<text id="title" x="160" y="640" font-size="232"', '<text id="title" x="160" y="640" font-size="120"')
    assert found(tree, "the title's capitals", "the least is 20")


def test_a_mark_too_small_at_320_px_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/card.svg", "translate(160 128) scale(0.146)", "translate(160 128) scale(0.12)")
    assert found(tree, "at 320 px wide the mark is 19.8 px", "the least is 24")


def test_a_repository_without_its_card_is_refused(tree: Path) -> None:
    (tree / "png/github/agents.png").unlink()
    assert found(tree, "png/github/agents.png", "missing")


def test_a_card_without_a_row_is_refused(tree: Path) -> None:
    shutil.copy(tree / "png/github/agents.png", tree / "png/github/extra.png")
    assert found(tree, "png/github/extra.png", "nothing generates it")


def test_a_card_under_another_name_is_refused(tree: Path) -> None:
    edit_pack(tree, lambda data: data["cards"]["repos"][5].update(file="png/github/github.png"))
    assert found(tree, "the card of .github", "a card's file is png/github/dot-github.png")


def test_a_motif_no_card_uses_is_refused(tree: Path) -> None:
    shutil.copy(tree / "src/cards/motifs/typing.svg", tree / "src/cards/motifs/spare.svg")
    assert found(tree, "motifs/spare.svg", "no card uses this motif")


# --- Stale exports -----------------------------------------------------------------------


def test_a_changed_row_makes_its_card_stale(tree: Path) -> None:
    edit_pack(tree, lambda data: data["cards"]["repos"][2].update(label="Identity"))
    assert found(tree, "png/github/brand.png", "stale")
    assert found(tree, "README.md", "its tables are not what pack.json and the record give")


def test_a_changed_source_makes_its_pictures_stale(tree: Path) -> None:
    edit(tree / "src/makertube/banner.svg", 'x="713" y="181"', 'x="715" y="181"')
    assert found(tree, "png/makertube/banner.png", "stale")


def test_a_changed_brand_file_makes_every_picture_stale(tree_with_brand: Path) -> None:
    tokens = tree_with_brand / "brand/tokens/tokens.json"
    tokens.write_text(tokens.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    for name in ("png/youtube/avatar.png", "png/github/social.png", "previews/cards.png"):
        assert found(tree_with_brand, name, "stale: brand/tokens/tokens.json changed")


def test_a_changed_picture_makes_its_preview_stale(tree: Path) -> None:
    shutil.copy(tree / "png/github/agents.png", tree / "png/github/boards.png")
    assert found(tree, "previews/cards.png", "stale: png/github/boards.png changed")


def test_a_picture_with_a_text_chunk_is_refused(tree: Path) -> None:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    path = tree / "png/youtube/watermark.png"
    extra = PngInfo()
    extra.add_text("Software", "an editor")
    with Image.open(path) as opened:
        opened.save(path, "PNG", pnginfo=extra)
    assert found(tree, "png/youtube/watermark.png", "holds tEXt")


# --- Brand, licenses, the public tree ----------------------------------------------------


def test_a_changed_trademarks_page_is_refused(tree: Path) -> None:
    edit(tree / "TRADEMARKS.md", "This part is a request.", "This part is a condition.")
    assert found(tree, "TRADEMARKS.md", "byte for byte")


def test_a_local_path_to_brand_is_refused(tree: Path) -> None:
    edit(tree / ".gitmodules", "url = https://github.com/kleidos-dev/brand.git", f"url = {LOCAL_BRAND}")
    assert found(tree, ".gitmodules", "the address https://github.com/kleidos-dev/brand.git and no other")
    assert found(tree, ".gitmodules", "a home-directory path")


def test_a_creative_commons_tag_is_refused(tree: Path) -> None:
    (tree / "src/extra.md").write_text(f"<!-- {CC_TAG} -->\n", encoding="utf-8")
    assert found(tree, "src/extra.md", "its license tag reads")


def test_another_license_text_is_refused(tree: Path) -> None:
    shutil.copy(tree / "LICENSES/GPL-3.0-or-later.txt", tree / "LICENSES/CC-BY-SA-4.0.txt")
    assert found(tree, "LICENSES/CC-BY-SA-4.0.txt", "only GPL-3.0-or-later")


def test_a_font_file_is_refused(tree: Path) -> None:
    shutil.copy(pack.brand_root(ROOT) / "fonts/mona-sans/MonaSansMonoVF[wght].ttf", tree / "src/MonaSansMono.ttf")
    assert found(tree, "src/MonaSansMono.ttf", "a font file that is not pinned")


def test_a_picture_out_of_place_is_refused(tree: Path) -> None:
    shutil.copy(tree / "png/youtube/avatar.png", tree / "src/shared/avatar.png")
    assert found(tree, "src/shared/avatar.png", "a picture or a PDF outside")


def test_an_embedded_picture_is_refused(tree: Path) -> None:
    edit(tree / "src/youtube/thumbnail.svg", '<g id="guides">', '<g id="guides">\n    <image x="0" y="0" width="10" height="10" href="x.png"/>')
    assert found(tree, "src/youtube/thumbnail.svg", "embeds a picture")
    assert found(tree, "src/youtube/thumbnail.svg", "a source holds plain shapes and text only")


def test_a_board_drawing_is_refused(tree: Path) -> None:
    (tree / "src/cards/front.svg").write_text(
        SVG_HEADER + '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><g id="screen-active"/></svg>\n', encoding="utf-8")
    assert found(tree, "src/cards/front.svg", "a board drawing's markers")


def test_private_data_is_refused(tree: Path) -> None:
    (tree / "notes.md").write_text(f"See {HOME_PATH}, at {PRIVATE_ADDRESS}, or write to {OTHER_EMAIL}.\n", encoding="utf-8")
    assert found(tree, "notes.md", "a home-directory path")
    assert found(tree, "notes.md", "a private network address")
    assert found(tree, "notes.md", "an e-mail address that is not the project's contact")


def test_an_off_palette_color_is_refused(tree: Path) -> None:
    edit(tree / "src/youtube/banner.svg", 'fill="#eceef1">Your passwords', 'fill="#ff00ff">Your passwords')
    assert found(tree, "src/youtube/banner.svg", "is not a token color")


def test_opacity_is_refused(tree: Path) -> None:
    edit(tree / "src/cards/card.svg", '<line id="shelf"', '<line id="shelf" opacity="0.5"')
    assert found(tree, "src/cards/card.svg", "carries opacity")
