from __future__ import annotations

from animal_adjectives.catalog import build_catalog, unique_animals
from animal_adjectives.models import Animal, AnimalRecord

BEAR = Animal("Bear", "https://en.wikipedia.org/wiki/Bear")
SEAL = Animal("Seal", "https://en.wikipedia.org/wiki/Seal")


def test_an_animal_with_several_adjectives_is_listed_under_each_one():
    catalog = build_catalog([AnimalRecord(BEAR, ("ursid", "ursine"))])
    assert catalog == {"ursid": (BEAR,), "ursine": (BEAR,)}


def test_an_adjective_collects_all_of_its_animals_in_sorted_order():
    catalog = build_catalog([AnimalRecord(SEAL, ("shared",)), AnimalRecord(BEAR, ("shared",))])
    assert catalog["shared"] == (BEAR, SEAL)


def test_the_same_animal_in_two_tables_is_merged_and_keeps_the_first_name():
    # Same article URL, so the same animal, even though the spellings differ.
    tidy = Animal("Cattle", "https://en.wikipedia.org/wiki/Cattle")
    messy = Animal("Cattle; ox, cow, kine", "https://en.wikipedia.org/wiki/Cattle")
    catalog = build_catalog([AnimalRecord(tidy, ("bovine",)), AnimalRecord(messy, ("bovine",))])
    assert catalog == {"bovine": (tidy,)}


def test_the_same_name_linking_to_different_articles_is_merged():
    # Regression, from the real page: "Pig" links to /wiki/Domestic_pig in the
    # species table and /wiki/Pig in the generic one, and "porcine" listed it twice.
    species = Animal("Pig", "https://en.wikipedia.org/wiki/Domestic_pig")
    generic = Animal("Pig", "https://en.wikipedia.org/wiki/Pig")
    catalog = build_catalog(
        [AnimalRecord(species, ("porcine",)), AnimalRecord(generic, ("porcine", "suine"))]
    )
    assert catalog == {"porcine": (species,), "suine": (species,)}
    assert unique_animals(catalog) == [species]


def test_unlinked_animals_with_the_same_name_are_merged():
    catalog = build_catalog(
        [AnimalRecord(Animal("Yak"), ("bovid",)), AnimalRecord(Animal("yak"), ("bovid",))]
    )
    assert catalog["bovid"] == (Animal("Yak"),)


def test_adjectives_are_sorted():
    catalog = build_catalog([AnimalRecord(BEAR, ("ursine", "arctoid", "ursid"))])
    assert list(catalog) == ["arctoid", "ursid", "ursine"]


def test_unique_animals_lists_a_multi_adjective_animal_once():
    catalog = build_catalog([AnimalRecord(BEAR, ("ursid", "ursine")), AnimalRecord(SEAL, ("ursid",))])
    assert unique_animals(catalog) == [BEAR, SEAL]
