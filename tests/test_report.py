from __future__ import annotations

from pathlib import Path

from animal_adjectives.models import Animal
from animal_adjectives.report import render_report, write_report

SOURCE = "https://en.wikipedia.org/wiki/List_of_animal_names"
BEAR = Animal("Bear", "https://en.wikipedia.org/wiki/Bear")


def test_each_animal_links_to_its_local_picture(tmp_path):
    image = tmp_path / "bear.jpg"
    html = render_report({"ursine": (BEAR,)}, {BEAR.key: image}, SOURCE)

    uri = image.resolve().as_uri()
    assert uri.startswith("file:")
    assert f'<a href="{uri}">Local image</a>' in html
    assert f'<img class="picture" src="{uri}"' in html


def test_an_animal_listed_under_two_adjectives_appears_in_both_sections(tmp_path):
    html = render_report(
        {"ursid": (BEAR,), "ursine": (BEAR,)}, {BEAR.key: tmp_path / "bear.jpg"}, SOURCE
    )
    assert html.count(">Bear</a>") == 2
    assert "<h2>ursid " in html
    assert "<h2>ursine " in html


def test_a_missing_picture_gets_a_placeholder_rather_than_a_broken_link():
    html = render_report({"ursine": (BEAR,)}, {}, SOURCE)
    assert "No picture" in html
    assert "<img" not in html
    assert "Local image" not in html


def test_page_content_is_escaped():
    # Everything in the report originates from an editable web page.
    hostile = Animal("<script>alert(1)</script>", None)
    html = render_report({"<b>bold</b>": (hostile,)}, {}, SOURCE)
    assert "<script>" not in html
    assert "<b>bold</b>" not in html
    assert "&lt;script&gt;" in html


def test_summary_counts_animals_once_each(tmp_path):
    seal = Animal("Seal", "https://en.wikipedia.org/wiki/Seal")
    html = render_report(
        {"a": (BEAR, seal), "b": (BEAR,)}, {BEAR.key: tmp_path / "bear.jpg"}, SOURCE
    )
    assert "2 adjectives, 2 animals, 1 pictures" in html


def test_write_report_creates_parent_directories_and_leaves_no_temp_files(tmp_path):
    output = tmp_path / "nested" / "dir" / "report.html"
    write_report("<p>héllo</p>", output)
    assert output.read_text(encoding="utf-8") == "<p>héllo</p>"
    assert [path.name for path in Path(output.parent).iterdir()] == ["report.html"]
