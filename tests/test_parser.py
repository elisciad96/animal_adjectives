"""Parser tests. Each one pins down a quirk found on the real page."""

from __future__ import annotations

import pytest

from animal_adjectives.errors import PageStructureError
from animal_adjectives.parser import parse_animal_records
from conftest import BASE_URL


@pytest.fixture
def records(sample_html):
    return parse_animal_records(sample_html, BASE_URL)


def _adjectives_by_name(records) -> dict[str, tuple[str, ...]]:
    return {record.animal.name: record.adjectives for record in records}


def test_every_adjective_of_an_animal_is_returned(records):
    assert _adjectives_by_name(records)["Bear"] == ("ursid", "ursine")


def test_qualifiers_in_parentheses_are_removed_from_adjectives(records):
    assert _adjectives_by_name(records)["Cattle"] == ("bovine", "taurine", "vaccine")


def test_comma_separated_adjectives_are_split(records):
    assert ("porcine", "suine") in _adjectives_by_name(records).values()


def test_rows_shifted_by_rowspans_still_find_their_adjectives(records):
    # The regression that matters most: without grid expansion these two rows read
    # the wrong column, or fall off the end of the row and vanish.
    by_name = _adjectives_by_name(records)
    assert by_name["Raccoon family of Carnivorans"] == ("procyonid", "procyonine")
    assert by_name["Civet family of Carnivorans"] == ("viverrid", "viverrine")


def test_rows_without_adjectives_are_dropped(records):
    names = _adjectives_by_name(records)
    assert "Gecko" not in names  # the N/A template, including its hidden "N/a" text
    assert "Donkey" not in names  # an empty cell


def test_placeholder_text_never_becomes_an_adjective(records):
    all_adjectives = {adjective for record in records for adjective in record.adjectives}
    assert all_adjectives.isdisjoint({"n/a", "a", "—", "[2]"})


def test_alphabetical_divider_rows_are_not_animals(records):
    assert "A" not in _adjectives_by_name(records)


def test_row_with_an_extra_cell_uses_the_right_column(records):
    assert _adjectives_by_name(records)["Sea urchin"] == ("echinoid",)


@pytest.mark.parametrize("name", ["Bear", "Cattle", "Pig"])
def test_animal_names_lose_their_editorial_clutter(records, name):
    # "Bear (list)[1]", "Pig (list) Also see Boar" and so on.
    assert name in _adjectives_by_name(records)


def test_article_link_is_absolute_and_ignores_the_list_link(records):
    bear = next(record.animal for record in records if record.animal.name == "Bear")
    assert bear.article_url == "https://en.wikipedia.org/wiki/Bear"


def test_species_table_is_emitted_first_regardless_of_page_order(records):
    # catalog.py relies on this order to pick the tidier spelling of a name.
    names = [record.animal.name for record in records]
    assert names.index("Cattle") < names.index("Cattle; ox, cow, kine")


def test_a_page_without_the_table_fails_loudly():
    html = "<table class='wikitable'><tr><th>Animal</th><th>Young</th></tr></table>"
    with pytest.raises(PageStructureError):
        parse_animal_records(html, BASE_URL)


def test_a_table_with_no_values_fails_loudly():
    html = """<table class="wikitable">
        <tr><th>Animal</th><th>Collateral adjective</th></tr>
        <tr><td>Gecko</td><td></td></tr>
    </table>"""
    with pytest.raises(PageStructureError):
        parse_animal_records(html, BASE_URL)
