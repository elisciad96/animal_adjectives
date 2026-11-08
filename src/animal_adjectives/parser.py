"""Turn the Wikipedia page's HTML into `AnimalRecord`s.

This is the only module that knows what the page looks like, so when Wikipedia's
layout changes, this is the only module that should need to change. It does no
network I/O, which lets it be tested with plain HTML strings.

The rules below come from profiling the real page rather than from assumptions.
The comments point out the specific rows that made each rule necessary.
"""

from __future__ import annotations

import copy
import logging
import re
from collections.abc import Iterable
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from animal_adjectives.errors import PageStructureError
from animal_adjectives.models import Animal, AnimalRecord

logger = logging.getLogger(__name__)

ADJECTIVE_HEADER = "collateral adjective"

# Two tables hold adjectives, and they name the animal in different columns:
#   * "Terms by species or taxon" -> "Animal"
#   * "Generic terms" -> "Trivial name" ("Scientific term" holds Latin names)
# The generic table is needed for completeness, since "avian" and "cetacean"
# appear nowhere else. The order here is a priority: species-table names are
# tidier ("Cattle" vs "cattle; ox, cow, kine"), so they are processed first and
# their spelling wins when the same animal is merged later (see catalog.py).
ANIMAL_HEADERS = ("animal", "trivial name")

# Text inside these elements is never part of the value we want:
#   sup            citation markers, e.g. "bovine[12]"
#   style, link    TemplateStyles that Wikipedia inlines into some cells
#   .sr-only       screen-reader text: the "N/a" in the N/A template
#   aria-hidden    the decorative dash in the same template
_NOISE_SELECTOR = "sup, style, link, .sr-only, [aria-hidden='true']"

_PARENTHETICAL = re.compile(r"\([^)]*\)")

# Adjectives are separated by <br> in one table (turned into a newline below)
# and by commas in the other. The rest are cheap to accept in case editors
# switch style.
_ADJECTIVE_SEPARATOR = re.compile(r"[\n,;/]|\s+or\s+")

# Letters, optionally joined by a space, hyphen or apostrophe. Anything else
# (a stray "?" or dash) is an editor's placeholder rather than an adjective.
# [^\W\d_] means "any Unicode letter", which \w alone does not.
_VALID_ADJECTIVE = re.compile(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*")

# Words that pass the check above but still mean "no value".
_PLACEHOLDERS = frozenset({"na", "none", "unknown"})

# Cross-references such as "Pig (list) Also see Boar" or "Donkey (list) See Ass".
_SEE_ALSO = re.compile(r"\s*\b(?:also\s+)?see\b.*$", re.IGNORECASE | re.DOTALL)

# A grid row can have gaps, where malformed markup leaves a position with neither
# a cell nor a rowspan coming down from above.
GridRow = list[Tag | None]


def parse_animal_records(html: str, base_url: str) -> list[AnimalRecord]:
    """Return one record per animal row that has at least one adjective.

    Rows without adjectives are dropped: the report is organised by adjective,
    so there is nowhere to display them.

    Raises:
        PageStructureError: if no adjective table or no adjective can be found.
    """
    soup = BeautifulSoup(html, "lxml")

    # Pair each table with the priority of its animal column, then process the
    # tables by priority instead of by document order.
    candidates = []
    for table in soup.select("table.wikitable"):
        grid = _expand_table_to_grid(table)
        columns = _locate_columns(grid)
        if columns is not None:
            candidates.append((columns, grid))

    if not candidates:
        raise PageStructureError(
            f"No table with a {ADJECTIVE_HEADER!r} column and an animal column was found."
        )

    candidates.sort(key=lambda candidate: candidate[0][0])

    records = []
    for (_, animal_col, adjective_col), grid in candidates:
        # grid[0] is the header row.
        for row in grid[1:]:
            record = _parse_row(row, animal_col, adjective_col, base_url)
            if record is not None:
                records.append(record)

    # An empty result means the markup changed in a way the checks above did not
    # notice. Fail loudly rather than write a blank report that looks successful.
    if not records:
        raise PageStructureError("The adjective tables were found, but no adjective was parsed.")
    return records


def _expand_table_to_grid(table: Tag) -> list[GridRow]:
    """Return the table as rows of cells, with row/colspans repeated in place.

    Looking cells up by position in each <tr> is not safe. On the real page, the
    Suinae row has two cells with rowspan=3, so the Procyonidae and Viverridae
    rows below it contain fewer <td>s, and their adjective is not at the column
    index the header suggests. Picking cells naively would silently misread or
    lose those rows, so we rebuild the grid the way a browser lays it out.

    The same Tag object can appear in many grid positions, which means later
    code must not modify the cells (see `_clean_text`).
    """
    grid: list[GridRow] = []
    # column index -> (rows still to fill, the spanning cell)
    pending_rowspans: dict[int, tuple[int, Tag]] = {}

    for tr in _tags(table.find_all("tr")):
        row: GridRow = []
        cells = iter(_tags(tr.find_all(["td", "th"], recursive=False)))
        column = 0

        # Fill the row left to right. Each position is taken by a rowspan coming
        # down from above if there is one, otherwise by this row's next real cell.
        while True:
            if column in pending_rowspans:
                remaining, spanning_cell = pending_rowspans[column]
                row.append(spanning_cell)
                if remaining > 1:
                    pending_rowspans[column] = (remaining - 1, spanning_cell)
                else:
                    del pending_rowspans[column]
                column += 1
                continue

            cell = next(cells, None)
            if cell is None:
                # This row is out of cells, but a rowspan may still occupy a later
                # column, and it has to be consumed or it would leak into the
                # following row. Record a gap and keep walking until none remain.
                if any(pending_column > column for pending_column in pending_rowspans):
                    row.append(None)
                    column += 1
                    continue
                break

            rowspan = _span_value(cell, "rowspan")
            for _ in range(_span_value(cell, "colspan")):
                row.append(cell)
                if rowspan > 1:
                    pending_rowspans[column] = (rowspan - 1, cell)
                column += 1

        grid.append(row)
    return grid


def _tags(nodes: Iterable[object]) -> list[Tag]:
    """Keep only the element nodes of a BeautifulSoup search result.

    A name-based find_all only ever matches elements, so at runtime this removes
    nothing. bs4's type hints are wider, though: they say a result may also hold
    text nodes. Filtering here once lets mypy check the rest of the module
    properly, with no casts or `# type: ignore` comments scattered around.
    """
    return [node for node in nodes if isinstance(node, Tag)]


def _span_value(cell: Tag, attribute: str) -> int:
    """Read a row/colspan, treating malformed values as the HTML default of 1."""
    try:
        # The default is the string "1" because attribute values are strings.
        return max(int(str(cell.get(attribute, "1"))), 1)
    except ValueError:
        return 1


def _locate_columns(grid: list[GridRow]) -> tuple[int, int, int] | None:
    """Return (priority, animal column, adjective column), or None for other tables.

    Columns are matched by header text instead of hard-coded positions, so that
    an editor adding a column to the table does not break the parser.
    """
    if not grid:
        return None
    headers = [
        " ".join(_clean_text(cell).split()).casefold() if cell is not None else ""
        for cell in grid[0]
    ]
    if ADJECTIVE_HEADER not in headers:
        return None
    for priority, animal_header in enumerate(ANIMAL_HEADERS):
        if animal_header in headers:
            return priority, headers.index(animal_header), headers.index(ADJECTIVE_HEADER)
    return None


def _parse_row(
    row: GridRow, animal_col: int, adjective_col: int, base_url: str
) -> AnimalRecord | None:
    """Build a record from a grid row, or None if the row holds no adjectives."""
    # Alphabetical dividers ("A", "B", ...) are one cell spanning every column,
    # so after expansion the whole row is the same Tag.
    if len({id(cell) for cell in row}) == 1:
        return None

    animal_cell = _cell_at(row, animal_col)
    adjective_cell = _cell_at(row, adjective_col)
    if animal_cell is None or adjective_cell is None:
        logger.debug("Skipping incomplete row: %s", row)
        return None

    adjectives = _parse_adjectives(adjective_cell)
    if not adjectives:
        return None

    name = _parse_animal_name(animal_cell)
    if not name:
        logger.warning("Skipping a row with adjectives but no animal name: %s", adjectives)
        return None

    return AnimalRecord(Animal(name, _parse_article_url(animal_cell, base_url)), adjectives)


def _cell_at(row: GridRow, column: int) -> Tag | None:
    return row[column] if column < len(row) else None


def _clean_text(cell: Tag) -> str:
    """Return the visible text of a cell, with each <br> as a newline."""
    # Work on a copy. A rowspan cell appears in several grid rows, so removing
    # nodes from the original would corrupt it for the following rows.
    clone = copy.copy(cell)
    for node in clone.select(_NOISE_SELECTOR):
        node.decompose()
    for line_break in clone.find_all("br"):
        line_break.replace_with("\n")
    return clone.get_text()


def _parse_adjectives(cell: Tag) -> tuple[str, ...]:
    """Split a cell into normalised adjectives, keeping page order."""
    # Parentheses go first: "taurine (male)" should become "taurine", and a
    # comma inside a note must not be mistaken for a separator.
    text = _PARENTHETICAL.sub(" ", _clean_text(cell))

    adjectives = []
    for piece in _ADJECTIVE_SEPARATOR.split(text):
        adjective = " ".join(piece.split()).casefold()
        if not adjective or adjective in _PLACEHOLDERS:
            continue
        if not _VALID_ADJECTIVE.fullmatch(adjective):
            logger.debug("Ignoring non-adjective value %r", adjective)
            continue
        adjectives.append(adjective)

    # dict.fromkeys removes duplicates while keeping order, which set() would not.
    return tuple(dict.fromkeys(adjectives))


def _parse_animal_name(cell: Tag) -> str:
    """Remove editorial clutter from an animal cell."""
    text = _PARENTHETICAL.sub(" ", _clean_text(cell))  # "Bear (list)" -> "Bear"
    text = _SEE_ALSO.sub("", text)  # "Pig Also see Boar" -> "Pig"
    text = " ".join(text.split())
    # Removing a parenthesis can leave a gap before punctuation.
    text = re.sub(r"\s+([,;])", r"\1", text).strip(" ,;")
    # Only the first letter changes: str.capitalize() would also lowercase the
    # rest. This matches the generic table's "bird" to the species table's style.
    return text[:1].upper() + text[1:]


def _parse_article_url(cell: Tag, base_url: str) -> str | None:
    """Return the absolute URL of the animal's article, if the cell links to one.

    The first real link is the animal: later ones are extras, like "(list)".
    """
    for link in _tags(cell.find_all("a", href=True)):
        if link.find_parent("sup"):  # citation link
            continue
        # bs4 returns multi-valued attributes (like class) as lists. href is not
        # one of them, but checking keeps both mypy and odd markup honest.
        href = link.get("href")
        if not isinstance(href, str):
            continue
        url = urljoin(base_url, href)
        if _is_article_url(url, base_url):
            # A fragment points inside an article and is not part of its identity.
            return url.split("#", 1)[0]
    return None


def _is_article_url(url: str, base_url: str) -> bool:
    """True for links to real articles on the same wiki."""
    parsed = urlparse(url)
    if parsed.netloc != urlparse(base_url).netloc:
        return False
    if not parsed.path.startswith("/wiki/"):  # also rejects red links (/w/index.php)
        return False
    # Same-page anchors like "#Pig" resolve to the page's own URL.
    if url.split("#", 1)[0] == base_url.split("#", 1)[0]:
        return False
    # "File:", "Help:" and so on are namespaces rather than articles.
    return ":" not in unquote(parsed.path.removeprefix("/wiki/"))
