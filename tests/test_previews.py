# SPDX-License-Identifier: MIT
"""The previews' crops: what a platform keeps of a picture."""
from __future__ import annotations

from pathlib import Path

import pack
import previews
from kleidos_brand import lettering

ROOT = Path(__file__).resolve().parents[1]


def _picture(size: tuple[int, int], color: tuple[int, int, int, int] = (0, 210, 255, 255)):
    from PIL import Image

    return Image.new("RGBA", size, color)


def test_the_centered_crop_keeps_the_middle() -> None:
    from PIL import Image

    card = _picture((2560, 1280), (10, 12, 15, 255))
    card.paste(Image.new("RGBA", (10, 1280), (255, 0, 0, 255)), (0, 0))  # outside the crop
    card.paste(Image.new("RGBA", (10, 1280), (0, 255, 0, 255)), (160, 0))  # the safe area's left edge
    cut = previews.center_crop(card, previews.CROP_RATIO)
    assert cut.size == (2445, 1280)
    colors = {color for _, color in cut.getcolors()}
    assert (255, 0, 0, 255) not in colors and (0, 255, 0, 255) in colors


def test_a_circle_crop_clears_the_corners_and_keeps_the_middle() -> None:
    cut = previews.in_circle(_picture((800, 800)), 98)
    assert cut.size == (98, 98)
    assert cut.getpixel((0, 0))[3] == 0 and cut.getpixel((97, 97))[3] == 0
    assert cut.getpixel((49, 49)) == (0, 210, 255, 255)
    # The square inside the circle is whole: what the avatar's safe area promises.
    inset = round(98 * (1 - 0.708) / 2) + 2
    assert cut.getpixel((inset, inset))[3] == 255


def test_the_smaller_stored_copy_covers_and_is_cut_around_the_center() -> None:
    assert previews.covering(_picture((1920, 317)), (600, 100)).size == (600, 100)


def test_a_picture_is_fitted_and_never_enlarged() -> None:
    assert previews.fitted(_picture((2560, 1280)), (326, 206)).size == (326, 163)
    assert previews.fitted(_picture((100, 50)), (326, 206)).size == (100, 50)


def test_enlarging_keeps_each_pixel_a_square() -> None:
    small = _picture((2, 1))
    small.putpixel((1, 0), (255, 255, 255, 255))
    big = previews.enlarged(small, 4)
    assert big.size == (8, 4)
    assert {big.getpixel((x, 3)) for x in range(4)} == {(0, 210, 255, 255)}
    assert {big.getpixel((x, 0)) for x in range(4, 8)} == {(255, 255, 255, 255)}


def test_a_lede_is_broken_into_lines_that_fit() -> None:
    brand = pack.brand_root(ROOT)
    words = "In a circle at the sizes each platform shows it, on a dark and on a light page, and the small ones again enlarged."
    lines = previews.wrapped(words, 600, brand)
    assert " ".join(lines) == words and len(lines) > 1
    for line in lines:
        shaped = lettering.shape(line, "Mona Sans", previews.LEDE_AXES, 0.0, brand)
        assert shaped.advance * previews.LEDE_SIZE / shaped.upem <= 600


def test_the_banner_views_are_the_rule_s_own_areas() -> None:
    data = pack.load(ROOT)
    safe = previews.BANNER_VIEWS[-1][1]
    assert f"{safe[2] - safe[0]} x {safe[3] - safe[1]} at ({safe[0]}, {safe[1]})" in data["rules"]["youtube-banner"]["safe_zone"]
