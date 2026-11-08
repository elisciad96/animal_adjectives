"""Command-line entry point: arguments in, exit code out. No logic of its own."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import requests

from animal_adjectives.config import Settings
from animal_adjectives.errors import AnimalAdjectivesError
from animal_adjectives.pipeline import run

logger = logging.getLogger("animal_adjectives")

EXIT_OK = 0
EXIT_FAILURE = 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(threadName)s %(message)s",
    )
    # urllib3 and BeautifulSoup would otherwise flood the --verbose output.
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    settings = Settings(
        output_path=args.output,
        image_dir=args.image_dir,
        max_workers=args.workers,
    )

    # Only *expected* failures get a friendly one-line message. A programming
    # error should still produce a traceback, because the traceback is the useful
    # part of that bug report.
    try:
        summary = run(settings)
    except (AnimalAdjectivesError, requests.RequestException, OSError) as error:
        logger.error("Run failed: %s", error)
        return EXIT_FAILURE

    logger.info(
        "Done: %d adjectives, %d animals, %d pictures. Report: %s",
        summary.adjective_count,
        summary.animal_count,
        summary.image_count,
        summary.output_path.resolve(),
    )
    if summary.animals_without_image:
        logger.warning(
            "%d animals have no picture: %s",
            len(summary.animals_without_image),
            ", ".join(summary.animals_without_image),
        )
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    defaults = Settings()
    parser = argparse.ArgumentParser(
        prog="animal-adjectives",
        description="Write an HTML report of Wikipedia's collateral adjectives and their animals.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=defaults.output_path,
        help="report file (default: %(default)s)",
    )
    parser.add_argument(
        "--image-dir", type=Path, default=defaults.image_dir,
        help="where pictures are stored (default: %(default)s)",
    )
    parser.add_argument(
        "-w", "--workers", type=_positive_int, default=defaults.max_workers,
        help="concurrent download threads (default: %(default)s)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    return parser


def _positive_int(value: str) -> int:
    # ThreadPoolExecutor raises on 0 workers. Rejecting it here gives the user a
    # proper usage message rather than a traceback.
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number
