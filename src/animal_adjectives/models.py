"""Plain data types shared across modules. No I/O and no parsing live here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class Animal:
    """An animal as listed on the page.

    Frozen, and therefore hashable and safe to share between threads.
    """

    name: str
    # None when the table cell has no usable link. Such an animal is still
    # reported, it just cannot have a picture because we have no article to
    # look one up from.
    article_url: str | None = None

    @property
    def key(self) -> str:
        """Identity of the animal, used to merge duplicates.

        The article URL beats the name because the two tables spell the same
        animal differently ("Cattle" vs "cattle; ox, cow, kine"), yet both link
        to the same article.
        """
        return self.article_url or self.name.casefold()


@dataclass(frozen=True, slots=True)
class AnimalRecord:
    """One table row: an animal and the adjectives listed next to it."""

    animal: Animal
    adjectives: tuple[str, ...]


# adjective -> its animals. A plain alias rather than a class: dict plus sorted
# tuples already gives the report everything it needs. Built-in generics work at
# runtime on 3.9+, so typing.Dict/Tuple are no longer needed.
Catalog: TypeAlias = dict[str, tuple[Animal, ...]]
