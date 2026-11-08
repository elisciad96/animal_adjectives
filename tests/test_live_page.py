"""Contract test against the live page. Run explicitly with: pytest -m network

The other tests prove that the code handles the sample page. Only this one can
notice that Wikipedia itself has changed. It stays out of the default run because
it depends on the network and on a page anyone can edit, which is the wrong trade
for a test that should block a commit, but is useful on a schedule.
"""

from __future__ import annotations

import pytest

from animal_adjectives.catalog import build_catalog
from animal_adjectives.config import DEFAULT_SOURCE_URL, Settings
from animal_adjectives.http_client import HttpClient
from animal_adjectives.parser import parse_animal_records


@pytest.mark.network
def test_live_page_still_parses_into_a_plausible_catalog():
    with HttpClient(Settings()).get(DEFAULT_SOURCE_URL) as response:
        catalog = build_catalog(parse_animal_records(response.text, DEFAULT_SOURCE_URL))

    assert len(catalog) > 100

    def names(adjective: str) -> set[str]:
        return {animal.name for animal in catalog[adjective]}

    # Long-established facts, chosen to be unlikely to be edited away. Together
    # they cover the species table, the generic table and multi-adjective rows.
    assert "Cattle" in names("bovine")
    assert "Dog" in names("canine")
    assert "Dog" in names("canid")
    assert "Bird" in names("avian")
    assert "Snake" in names("serpentine")
