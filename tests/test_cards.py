# SPDX-License-Identifier: MIT
"""The card writer: one template, one row, one motif."""
from __future__ import annotations

import io
import random
from pathlib import Path

import cards
import export
import pack
import pytest
import records
import source
from kleidos_brand import meta

ROOT = Path(__file__).resolve().parents[1]
DATA = pack.load(ROOT)

FIXTURE = pack.Row(
    repo="example", label="Sample", line="Two short lines to stand under a name.",
    lines=("Two short lines to stand", "under a name."), motif="frames", file=None)


def test_every_repository_of_the_project_has_a_card() -> None:
    assert [row.repo for row in pack.rows(DATA)] == ["kleidos", "boards", "brand", "social", "agents", ".github"]
    for row in pack.rows(DATA):
        assert row.file is not None and (ROOT / row.file).is_file()


def test_a_card_is_written_from_its_row() -> None:
    built = cards.card(ROOT, DATA, FIXTURE)
    words = {name: placed.line.text for name, placed in built.drawing.words.items()}
    assert words == {"label": "SAMPLE", "title": "example", "line.0": "Two short lines to stand", "line.1": "under a name."}
    assert built.inputs == (Path("src/cards/card.svg"), Path("src/cards/motifs/frames.svg"), Path("pack.json"))
    assert cards.card_findings(ROOT, built) == []


def test_a_card_holds_outlines_and_no_guide() -> None:
    svg = cards.card(ROOT, DATA, FIXTURE).drawing.svg
    assert "<text" not in svg and 'id="guides"' not in svg and "data-lockup" not in svg
    assert svg.count('class="mark"') == 1


def test_every_card_differs_only_in_its_words_and_its_motif() -> None:
    built = cards.cards(ROOT, DATA)
    first = built[0].drawing
    for other in built[1:]:
        assert other.drawing.lockup == first.lockup
        assert other.drawing.shapes == first.shapes
        assert other.drawing.guides == first.guides
        assert other.drawing.words["title"].y == first.words["title"].y
        assert other.drawing.words["title"].scale == first.words["title"].scale


def test_every_motif_stands_on_the_shelf_inside_its_box() -> None:
    assert cards.motif_findings(ROOT, DATA) == []
    for built in cards.cards(ROOT, DATA):
        box, room = built.drawing.motif, built.drawing.guides["motif-box"]
        assert box is not None and source.inside(box, room)
        assert box[3] == pytest.approx(1118.0)  # the shelf's top edge


def test_a_card_keeps_its_mark_at_320_px() -> None:
    built = cards.card(ROOT, DATA, pack.rows(DATA)[0])
    share = cards.NARROW_WIDTH / built.drawing.size[0]
    assert (built.drawing.lockup[3] - built.drawing.lockup[1]) * share >= cards.MIN_MARK_PX
    assert cards.card_findings(ROOT, built) == []


def test_a_row_with_too_many_lines_is_refused() -> None:
    crowded = pack.Row("example", "Sample", "a b c d", ("a", "b", "c", "d"), "typing", None)
    with pytest.raises(ValueError, match="room for 3"):
        cards.compose(ROOT, DATA, crowded)


def test_an_unknown_motif_is_refused() -> None:
    with pytest.raises(FileNotFoundError):
        cards.card(ROOT, DATA, pack.Row("example", "Sample", "a", ("a",), "nothing", None))


def _described() -> meta.MediaMeta:
    return records.build(ROOT, Path("png/github/kleidos.png"), "A test picture", "A picture a test draws.", (), False)


def test_a_heavy_picture_falls_back_to_a_palette() -> None:
    from PIL import Image

    # Many close shades in a soft pattern: heavy as full color, light with 256 colors.
    rng = random.Random(3)
    image = Image.new("RGB", (640, 320))
    image.putdata([(10 + rng.randrange(4), 12 + rng.randrange(4), 15 + rng.randrange(4)) for _ in range(640 * 320)])
    described = _described()
    plain = export.fit_under(image, None, described)
    limit = len(plain) - 1
    reduced = export.fit_under(image, limit, described)
    assert len(reduced) < limit  # the metadata counted in the weight
    with Image.open(io.BytesIO(reduced)) as opened:
        assert opened.mode == "P" and opened.format == "PNG"
    assert meta.png_findings("plain", plain, described) == meta.png_findings("reduced", reduced, described) == []


def test_a_picture_too_heavy_even_with_a_palette_fails() -> None:
    from PIL import Image

    noise = Image.frombytes("RGB", (256, 256), random.Random(5).randbytes(256 * 256 * 3))
    with pytest.raises(ValueError, match="the limit is under"):
        export.fit_under(noise, 1000, _described())


def test_the_boards_card_and_the_banner_show_all_nine_boards_at_one_scale() -> None:
    from kleidos_brand import boards

    data = pack.load(ROOT)
    row = next(row for row in pack.rows(data) if row.repo == "boards")
    assert row.motif == "shelf"
    banner = source.ready(source.parse(ROOT / "src/youtube/banner.svg"), pack.brand_root(ROOT), "banner")
    for drawing in (cards.card(ROOT, data, row).drawing, banner):
        assert sorted(placed.slug for placed in drawing.fronts) == sorted(boards.order(pack.brand_root(ROOT))), "not only the StickS3"
        assert len({round(placed.scale, 9) for placed in drawing.fronts}) == 1
