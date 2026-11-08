"""Connect the steps into one run. This is the only module that knows their order."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from animal_adjectives.catalog import build_catalog, unique_animals
from animal_adjectives.config import Settings
from animal_adjectives.http_client import HttpClient
from animal_adjectives.images import ImageDownloader
from animal_adjectives.parser import parse_animal_records
from animal_adjectives.report import render_report, write_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunSummary:
    """What a run produced, so the caller can report on it without re-deriving it."""

    adjective_count: int
    animal_count: int
    image_count: int
    animals_without_image: tuple[str, ...]
    output_path: Path


def run(settings: Settings, client: HttpClient | None = None) -> RunSummary:
    """Fetch the page, download the pictures and write the report.

    `client` can be injected so that tests can run the entire flow with no
    network access, without any monkeypatching.

    Failing to fetch or parse the page is fatal and raises. A missing picture is
    not: the report is still useful, and the summary says which ones are missing.
    """
    client = client or HttpClient(settings)

    logger.info("Fetching %s", settings.source_url)
    with client.get(settings.source_url) as response:
        page_html = response.text

    records = parse_animal_records(page_html, settings.source_url)
    catalog = build_catalog(records)
    animals = unique_animals(catalog)
    logger.info("Parsed %d adjectives covering %d animals", len(catalog), len(animals))

    logger.info("Downloading pictures into %s", settings.image_dir)
    images = ImageDownloader(client, settings).download_all(animals)

    # Writing the report comes last, so it can never reference a file that has not
    # been downloaded yet.
    write_report(render_report(catalog, images, settings.source_url), settings.output_path)

    return RunSummary(
        adjective_count=len(catalog),
        animal_count=len(animals),
        image_count=len(images),
        animals_without_image=tuple(a.name for a in animals if a.key not in images),
        output_path=settings.output_path,
    )
