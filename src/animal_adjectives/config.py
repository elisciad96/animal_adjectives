"""Runtime settings, kept in one place so no module hides a magic number."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE_URL = "https://en.wikipedia.org/wiki/List_of_animal_names"


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything a run can be configured with.

    The dataclass is frozen because worker threads read it concurrently: if it
    cannot change, there is no shared mutable state to reason about.
    """

    source_url: str = DEFAULT_SOURCE_URL

    # The assignment asks for /tmp/ explicitly. On Windows this resolves to
    # \tmp on the current drive (e.g. C:\tmp) and is created if it is missing.
    image_dir: Path = Path("/tmp")

    output_path: Path = Path("output/animal_adjectives.html")

    # Downloads are I/O-bound: threads spend nearly all their time waiting on
    # the network, when the GIL is released, so threads give a real speed-up
    # without the overhead of processes. The cap is deliberately modest because
    # Wikimedia rate-limits aggressive clients, and a few more threads would
    # only turn into more HTTP 429 responses.
    max_workers: int = 8

    # (connect, read) in seconds. `requests` has no default timeout, so without
    # this a single stalled socket could hang a worker thread forever.
    timeout: tuple[float, float] = (5.0, 30.0)

    # Retries apply to transient failures only (429 and 5xx, connection errors).
    max_retries: int = 4
    backoff_factor: float = 1.0

    # Wikimedia policy requires a descriptive User-Agent and rejects the default
    # library one. No personal contact details belong in here.
    user_agent: str = "animal-adjectives/1.0 (educational project; python-requests)"

    # We only ask for thumbnails, so anything bigger than this is unexpected.
    # The limit stops a bad response from filling the disk.
    max_image_bytes: int = 20 * 1024 * 1024
