"""Render the catalog as one self-contained HTML file."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from html import escape
from pathlib import Path
from string import Template

from animal_adjectives.models import Animal, Catalog

# string.Template instead of str.format because CSS is full of { } braces, and
# instead of Jinja2 because one small page does not justify another dependency.
_PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Collateral adjectives of animals</title>
<style>
  :root { color-scheme: light dark; --bg: #fff; --fg: #1f2328; --muted: #656d76; --line: #d0d7de; --tile: #f6f8fa; --link: #0a5bc4; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #16191d; --fg: #e6e8eb; --muted: #9aa3ad; --line: #343a42; --tile: #1f2329; --link: #6cb0ff; }
  }
  body { margin: 0 auto; max-width: 70rem; padding: 1.5rem 1rem 4rem; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }
  a { color: var(--link); }
  .summary { color: var(--muted); margin-top: 0; }
  nav { display: flex; flex-wrap: wrap; gap: .25rem .75rem; padding: .75rem 0; border-block: 1px solid var(--line); }
  h2 { margin: 2rem 0 .75rem; font-size: 1.25rem; }
  h2 small { color: var(--muted); font-weight: 400; font-size: .85rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: .75rem; grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr)); }
  li { background: var(--tile); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
  .picture { display: block; aspect-ratio: 4 / 3; width: 100%; object-fit: cover; }
  .no-picture { display: flex; align-items: center; justify-content: center; aspect-ratio: 4 / 3; color: var(--muted); font-size: .85rem; }
  .caption { padding: .4rem .6rem .5rem; font-size: .9rem; overflow-wrap: anywhere; }
  .caption small { display: block; }
</style>
</head>
<body>
<h1>Collateral adjectives of animals</h1>
<p class="summary">$adjective_count adjectives, $animal_count animals, $image_count pictures. Source: <a href="$source_url">$source_url</a></p>
<nav aria-label="Adjectives by first letter">$letter_links</nav>
$sections
</body>
</html>
""")


def render_report(catalog: Catalog, images: Mapping[str, Path], source_url: str) -> str:
    """Return the report as an HTML string. Pure, which makes it easy to test.

    `images` maps `Animal.key` to a local file. Animals missing from it get a
    placeholder rather than a broken image icon.
    """
    # Every piece of text below comes from a web page or the file system, so all
    # of it gets escaped. An odd table cell must not be able to inject markup.
    animal_keys = {animal.key for animals in catalog.values() for animal in animals}
    return _PAGE.substitute(
        adjective_count=len(catalog),
        animal_count=len(animal_keys),
        image_count=len(animal_keys & images.keys()),
        source_url=escape(source_url, quote=True),
        letter_links=_render_letter_links(catalog),
        sections="\n".join(
            _render_section(adjective, animals, images) for adjective, animals in catalog.items()
        ),
    )


def write_report(html: str, output_path: Path) -> None:
    """Write the report atomically, so a crash never leaves half a page behind."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=output_path.parent, suffix=".part")
    temp_path = Path(temp_name)
    try:
        # newline="" stops Windows from rewriting line endings, so the same input
        # produces a byte-identical report on every platform.
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temp_file:
            temp_file.write(html)
        os.replace(temp_path, output_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _render_letter_links(catalog: Catalog) -> str:
    # With about 150 sections on one page, jump links make it far easier to use.
    # Each letter points at the first adjective that starts with it. The catalog
    # is sorted, so setdefault finds exactly that one.
    first_by_letter: dict[str, str] = {}
    for adjective in catalog:
        first_by_letter.setdefault(adjective[0].upper(), adjective)
    return " ".join(
        f'<a href="#{_anchor(adjective)}">{escape(letter)}</a>'
        for letter, adjective in first_by_letter.items()
    )


def _render_section(
    adjective: str, animals: tuple[Animal, ...], images: Mapping[str, Path]
) -> str:
    noun = "animal" if len(animals) == 1 else "animals"
    items = "\n".join(_render_animal(animal, images.get(animal.key)) for animal in animals)
    return (
        f'<section id="{_anchor(adjective)}">\n'
        f"<h2>{escape(adjective)} <small>{len(animals)} {noun}</small></h2>\n"
        f"<ul>\n{items}\n</ul>\n</section>"
    )


def _render_animal(animal: Animal, image: Path | None) -> str:
    name = escape(animal.name)
    if image is None:
        picture = '<div class="no-picture">No picture</div>'
        local_link = ""
    else:
        # An absolute file:// URI works wherever the report is moved to, as long
        # as it stays on this machine, whereas a relative path would break, and
        # cannot even be expressed across two Windows drives.
        uri = escape(image.resolve().as_uri(), quote=True)
        # loading="lazy" because hundreds of images would otherwise all be decoded
        # as soon as the page opens.
        picture = f'<a href="{uri}"><img class="picture" src="{uri}" alt="{name}" loading="lazy"></a>'
        local_link = f'<small><a href="{uri}">Local image</a></small>'

    title = name
    if animal.article_url:
        title = f'<a href="{escape(animal.article_url, quote=True)}">{name}</a>'
    return f'<li>{picture}<div class="caption">{title}{local_link}</div></li>'


def _anchor(adjective: str) -> str:
    # Adjectives may contain spaces, which are not valid in an id.
    return escape("adj-" + "-".join(adjective.split()), quote=True)
