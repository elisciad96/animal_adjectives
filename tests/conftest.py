"""Shared test helpers: a sample page and an in-memory replacement for HttpClient."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import requests

from animal_adjectives.config import Settings

BASE_URL = "https://en.wikipedia.org/wiki/List_of_animal_names"
IMAGE_BYTES = b"\xff\xd8\xff fake jpeg bytes"


def make_response(
    body: bytes = b"", content_type: str = "application/json", status: int = 200
) -> requests.Response:
    """Build a genuine `requests.Response`, so production code runs its real paths."""
    response = requests.Response()
    response.status_code = status
    response.headers["Content-Type"] = content_type
    response.encoding = "utf-8"
    response.raw = io.BytesIO(body)
    return response


def summary_url(title: str) -> str:
    return f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def thumbnail_url(title: str) -> str:
    return f"https://upload.wikimedia.org/thumb/{title}.jpg"


class FakeClient:
    """Stands in for HttpClient, serving canned responses with no network access.

    A route is either a callable that returns a response (called afresh each time,
    because a response body can only be read once) or an exception to raise.
    """

    def __init__(self) -> None:
        self.routes: dict = {}
        self.requests: list[str] = []  # list.append is atomic, so this is thread-safe

    def add_image(self, title: str) -> None:
        """Register both requests needed to download one article's image."""
        body = f'{{"thumbnail": {{"source": "{thumbnail_url(title)}"}}}}'.encode()
        self.routes[summary_url(title)] = lambda: make_response(body)
        self.routes[thumbnail_url(title)] = lambda: make_response(IMAGE_BYTES, "image/jpeg")

    def get(self, url: str, *, stream: bool = False) -> requests.Response:
        self.requests.append(url)
        route = self.routes.get(url)
        if route is None:
            raise requests.HTTPError(f"404 for {url}")
        if isinstance(route, Exception):
            raise route
        return route()


@pytest.fixture
def sample_html() -> str:
    return (Path(__file__).parent / "fixtures" / "sample_page.html").read_text(encoding="utf-8")


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a per-test temp directory, never at the real /tmp."""
    return Settings(
        source_url=BASE_URL,
        image_dir=tmp_path / "images",
        output_path=tmp_path / "out" / "report.html",
        max_workers=4,
    )
