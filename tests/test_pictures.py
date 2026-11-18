# SPDX-License-Identifier: MIT
"""The pictures themselves: what was exported, drawn again, and the mark by itself."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import export
import pack
import pytest
from kleidos_brand import png

ROOT = Path(__file__).resolve().parents[1]

#: The pixels of the first social pack's images of the mark alone (SHA-256 of their RGBA bytes),
#: drawn from the firmware repository's copy of the mark before this repository existed. The port
#: draws the same pixels from brand.
FIRST_PACK = {
    "png/youtube/avatar.png": "0ad28dd1a37089ce87438521c69c88709b2220ac5cc146165ccd8c3f65fc840f",
    "png/makertube/avatar.png": "30a10e39d63bd690ece7864511045f5c078d38f05d3bbb448daff83e5f9cf229",
    "png/youtube/watermark.png": "d7e5f7f88637e902cbb67792903ec55e359221356060fd92dc0cdf83ab118de9",
}


def _pixels(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as opened:
        return hashlib.sha256(opened.convert("RGBA").tobytes()).hexdigest()


def test_the_record_names_every_picture_and_the_brand_files_it_read() -> None:
    recorded = json.loads((ROOT / "exports.json").read_text(encoding="utf-8"))
    collected = export.collect(ROOT)
    assert set(recorded["files"]) == {picture.path.as_posix() for picture in collected.pictures}
    for name, entry in recorded["files"].items():
        for needed in pack.BRAND_INPUTS:
            assert (pack.BRAND / needed).as_posix() in entry["inputs"], name
        assert not any(key.startswith("/") for key in entry["inputs"])
    assert "commit" not in json.dumps(recorded)  # digests only: a commit's name would not survive a squashed history


def test_every_card_weighs_less_than_github_accepts() -> None:
    for row in pack.rows(pack.load(ROOT)):
        data = (ROOT / row.file).read_bytes()
        assert png.size(data) == (2560, 1280)
        assert len(data) < 1_000_000


def test_the_mark_alone_is_the_first_pack_s_pixel_for_pixel() -> None:
    for name, digest in FIRST_PACK.items():
        assert _pixels(ROOT / name) == digest, name


def test_the_watermark_is_transparent_and_the_avatar_is_not() -> None:
    from PIL import Image

    with Image.open(ROOT / "png/youtube/watermark.png") as opened:
        assert opened.mode == "RGBA" and opened.getpixel((2, 2))[3] == 0 and opened.getpixel((300, 300))[3] == 255
    with Image.open(ROOT / "png/youtube/avatar.png") as opened:
        assert opened.mode == "RGB"


@pytest.mark.browser
def test_every_picture_drawn_again_is_the_committed_one(chromium) -> None:
    recorded = json.loads((ROOT / "exports.json").read_text(encoding="utf-8"))
    if chromium.version != recorded["chromium"]:
        assert export.drawn_findings(ROOT, tolerant=True, browser=chromium) == []
        pytest.skip(f"exact pixels are compared under Chromium {recorded['chromium']}; this is {chromium.version}")
    assert export.drawn_findings(ROOT, browser=chromium) == []


@pytest.mark.browser
def test_a_mark_alone_one_pixel_off_is_caught(chromium, tree: Path) -> None:
    from PIL import Image

    recorded = json.loads((ROOT / "exports.json").read_text(encoding="utf-8"))
    if chromium.version != recorded["chromium"]:
        pytest.skip("exact pixels are compared under the recorded Chromium only")
    path = tree / "png/youtube/avatar.png"
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    image.putpixel((400, 400), (255, 255, 255))
    path.write_bytes(png.encode(image))
    found = export.drawn_findings(tree, only=frozenset({"png/youtube/avatar.png"}), browser=chromium)
    assert any("is not brand's mark drawn by itself: it differs in 1 pixels" in line for line in found)
    assert any("drawn again, it differs in 1 pixels" in line for line in found)


@pytest.mark.browser
def test_a_mark_that_is_not_brand_s_is_caught_even_when_the_export_matches_its_source(chromium, tree_with_brand: Path) -> None:
    recorded = json.loads((ROOT / "exports.json").read_text(encoding="utf-8"))
    if chromium.version != recorded["chromium"]:
        pytest.skip("exact pixels are compared under the recorded Chromium only")
    # Brand's mark changes; this repository's source still holds the old shapes, and so does its export.
    mark = tree_with_brand / "brand/logo/src/mark.svg"
    mark.write_text(mark.read_text(encoding="utf-8").replace('r="42"', 'r="40"'), encoding="utf-8")
    found = export.drawn_findings(tree_with_brand, only=frozenset({"png/youtube/watermark.png"}), browser=chromium)
    assert any("png/youtube/watermark.png: is not brand's mark drawn by itself" in line for line in found)


@pytest.mark.browser
def test_a_video_s_thumbnail_is_drawn_from_the_template(chromium) -> None:
    from PIL import Image

    data = export.thumbnail(ROOT, ["One sign-in,", "uncut"], ROOT / "png/youtube/avatar.png", chromium)
    assert png.size(data) == (3840, 2160)
    assert len(data) < pack.limit(pack.load(ROOT), "youtube-thumbnail")
    assert png.findings("thumbnail", data) == []
    with Image.open(io.BytesIO(data)) as opened:
        assert opened.convert("RGB").getpixel((2933, 1020)) != (10, 12, 15)  # the picture, in its room


@pytest.mark.browser
def test_a_title_that_does_not_fit_is_refused(chromium) -> None:
    with pytest.raises(ValueError, match="reaches outside the safe area"):
        export.thumbnail(ROOT, ["A line that is much too long to fit on a thumbnail at this size"], None, chromium)
    with pytest.raises(ValueError, match="one to 3 lines"):
        export.thumbnail(ROOT, ["a", "b", "c", "d"], None, chromium)


def test_a_one_off_is_named_for_its_title_and_kept_out_of_the_pack() -> None:
    assert export.slug(["One sign-in,", "uncut"]) == "one-sign-in-uncut"
    assert "/dist/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
