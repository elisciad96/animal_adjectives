"""Find and download each animal's picture, concurrently."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests

from animal_adjectives.config import Settings
from animal_adjectives.errors import ImageDownloadError
from animal_adjectives.http_client import HttpClient
from animal_adjectives.models import Animal

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"})
_DEFAULT_EXTENSION = ".jpg"
_CHUNK_SIZE = 64 * 1024


class ImageDownloader:
    """Downloads one picture per animal into a directory."""

    def __init__(self, client: HttpClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    def download_all(self, animals: Iterable[Animal]) -> dict[str, Path]:
        """Download all pictures and return {animal.key: local path}.

        Animals that end up without a picture are simply absent from the result.
        One failure must never sink a run of ~150 downloads: the report shows a
        placeholder for that animal, and the failure is logged.
        """
        # Done once up front, in the main thread, so that a bad directory fails
        # immediately with one clear error instead of once per worker.
        self._settings.image_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Path] = {}
        with ThreadPoolExecutor(
            max_workers=self._settings.max_workers, thread_name_prefix="image"
        ) as pool:
            futures = {pool.submit(self._download_one, animal): animal for animal in animals}

            # Only this main thread writes to `results`, so it needs no lock:
            # the workers communicate purely by returning values.
            for future in as_completed(futures):
                animal = futures[future]
                try:
                    path = future.result()
                except (requests.RequestException, ImageDownloadError, OSError) as error:
                    # Expected, per-image problems. Anything else is a bug, and is
                    # left to propagate rather than being hidden behind a warning.
                    logger.warning("No image for %s: %s", animal.name, error)
                    continue
                if path is None:
                    logger.info("No image available for %s", animal.name)
                else:
                    results[animal.key] = path
        return results

    def _download_one(self, animal: Animal) -> Path | None:
        """Runs in a worker thread. Returns None if the animal has no picture."""
        if animal.article_url is None:
            return None

        # Reuse an earlier download. This makes re-runs fast, avoids needless load
        # on Wikimedia, and means a run that was cut short just picks up again.
        stem = _file_stem(animal.article_url)
        cached = self._find_cached(stem)
        if cached is not None:
            return cached

        image_url = self._resolve_image_url(animal.article_url)
        if image_url is None:
            return None

        destination = self._settings.image_dir / f"{stem}{_extension_of(image_url)}"
        self._save(image_url, destination)
        return destination

    def _find_cached(self, stem: str) -> Path | None:
        # The extension is only known after asking the API, so look for any
        # extension. `stem` is sanitised, so it holds no glob metacharacters.
        for path in self._settings.image_dir.glob(f"{stem}.*"):
            if path.suffix in _ALLOWED_EXTENSIONS and path.stat().st_size > 0:
                return path
        return None

    def _resolve_image_url(self, article_url: str) -> str | None:
        """Ask Wikipedia which picture represents an article.

        The REST summary endpoint returns the article's lead image, chosen by
        Wikipedia itself. That is more reliable than scraping each article for
        the "first <img>", which is frequently an icon or a maintenance banner.
        It also resolves redirects for us.
        """
        parsed = urlparse(article_url)
        # Title segments may already be percent-encoded, and a "/" inside a title
        # must be encoded for this endpoint: normalise by decoding, then encoding.
        title = quote(unquote(parsed.path.removeprefix("/wiki/")), safe="")
        api_url = f"{parsed.scheme}://{parsed.netloc}/api/rest_v1/page/summary/{title}"

        with self._client.get(api_url) as response:
            try:
                summary = response.json()
            except ValueError as error:  # the JSON error type varies between backends
                raise ImageDownloadError(f"Invalid JSON from {api_url}") from error

        # The thumbnail is preferred: it is plenty for a report, whereas an
        # "original" can run to tens of megabytes.
        for field in ("thumbnail", "originalimage"):
            source = (summary.get(field) or {}).get("source")
            if source:
                return source
        return None

    def _save(self, image_url: str, destination: Path) -> None:
        """Stream an image to disk atomically, enforcing type and size limits."""
        # The URL comes from a remote response, so check it before fetching it.
        if urlparse(image_url).scheme != "https":
            raise ImageDownloadError(f"Refusing non-HTTPS image URL: {image_url}")

        with self._client.get(image_url, stream=True) as response:
            content_type = response.headers.get("Content-Type", "")
            # An error page delivered with a 200 status must not be saved as a .jpg.
            if not content_type.startswith("image/"):
                raise ImageDownloadError(f"Expected an image, got {content_type!r}")

            # Write to a temp file in the same directory and rename at the end.
            # The rename is atomic on the same filesystem, so an interrupted
            # download can never leave a truncated file that the cache check
            # would later accept as complete.
            descriptor, temp_name = tempfile.mkstemp(
                dir=destination.parent, prefix=".download-", suffix=".part"
            )
            temp_path = Path(temp_name)
            try:
                written = 0
                with os.fdopen(descriptor, "wb") as temp_file:
                    for chunk in response.iter_content(_CHUNK_SIZE):
                        written += len(chunk)
                        # Checked while streaming, because Content-Length can be
                        # missing or wrong.
                        if written > self._settings.max_image_bytes:
                            raise ImageDownloadError(
                                f"Image exceeds {self._settings.max_image_bytes} bytes"
                            )
                        temp_file.write(chunk)
                if written == 0:
                    raise ImageDownloadError("Image response was empty")
                os.replace(temp_path, destination)
            except BaseException:
                # BaseException so Ctrl-C leaves no stray temp files behind either.
                temp_path.unlink(missing_ok=True)
                raise


def _file_stem(article_url: str) -> str:
    """Build a readable file name that is safe and unique for this article.

    The slug comes from page content, so everything outside [a-z0-9] is dropped.
    That rules out path traversal and characters Windows forbids.

    The short hash matters for two reasons: different titles could reduce to the
    same slug, and /tmp is shared, so a bare "cat.jpg" could collide with somebody
    else's file, which the cache check would then wrongly reuse.
    """
    title = unquote(urlparse(article_url).path.rsplit("/", 1)[-1])
    slug = re.sub(r"[^a-z0-9]+", "_", title.casefold()).strip("_")[:60]
    digest = hashlib.sha256(article_url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}" if slug else digest


def _extension_of(image_url: str) -> str:
    suffix = Path(urlparse(image_url).path).suffix.lower()
    return suffix if suffix in _ALLOWED_EXTENSIONS else _DEFAULT_EXTENSION
