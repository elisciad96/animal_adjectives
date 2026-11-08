"""Invert the page's "animal -> adjectives" rows into "adjective -> animals"."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from animal_adjectives.models import Animal, AnimalRecord, Catalog


def build_catalog(records: Iterable[AnimalRecord]) -> Catalog:
    """Group animals under every adjective they have.

    An animal with several adjectives is listed under each one, as the assignment
    asks. The result is sorted so the same input always gives the same report,
    which makes reports easy to compare between runs.
    """
    # Two rows are the same animal if they share an article OR a display name, and
    # each signal catches duplicates the other misses, as seen on the real page:
    #   * same article, different name: "cattle; ox, cow, kine" and "Cattle"
    #   * same name, different article: "Pig" links to /wiki/Pig in one table and
    #     to /wiki/Domestic_pig in the other
    # Both signals are registered as aliases of the first Animal seen. The parser
    # emits the species table first, so its tidier spelling is the one that is kept.
    aliases: dict[str, Animal] = {}

    # A set per adjective: the same adjective/animal pair can occur twice, because
    # "porcine" is listed for Pig in both tables.
    grouped: defaultdict[str, set[Animal]] = defaultdict(set)

    for record in records:
        animal = _resolve_alias(record.animal, aliases)
        for adjective in record.adjectives:
            grouped[adjective].add(animal)

    return {
        adjective: tuple(sorted(grouped[adjective], key=_sort_key))
        for adjective in sorted(grouped)
    }


def _resolve_alias(animal: Animal, aliases: dict[str, Animal]) -> Animal:
    """Return the Animal already known by this article or name, else this one."""
    name_key = animal.name.casefold()
    signals = [name_key] if animal.article_url is None else [animal.article_url, name_key]
    canonical = next((aliases[s] for s in signals if s in aliases), animal)
    # Register every signal, so that a later row matching on either one finds it.
    for signal in signals:
        aliases.setdefault(signal, canonical)
    return canonical


def unique_animals(catalog: Catalog) -> list[Animal]:
    """Return each animal once, however many adjectives it appears under.

    This is the list to download images for: 'Snake' has five adjectives, but
    needs only one picture.
    """
    animals = {animal.key: animal for group in catalog.values() for animal in group}
    return sorted(animals.values(), key=_sort_key)


def _sort_key(animal: Animal) -> tuple[str, str]:
    # casefold puts "bird" and "Bear" in dictionary order. The key is the tie-break
    # that keeps the order stable if two animals ever share a name.
    return animal.name.casefold(), animal.key
