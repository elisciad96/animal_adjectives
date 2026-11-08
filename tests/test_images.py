from __future__ import annotations

import threading
from dataclasses import replace
from urllib.parse import quote

import requests

from animal_adjectives.images import ImageDownloader
from animal_adjectives.models import Animal
from conftest import IMAGE_BYTES, make_response, summary_url, thumbnail_url


def _animal(title: str) -> Animal:
    return Animal(title, f"https://en.wikipedia.org/wiki/{title}")


def _part_files(settings) -> list:
    return list(settings.image_dir.glob(".download-*"))


def test_downloads_the_image_and_maps_it_to_the_animal(fake_client, settings):
    fake_client.add_image("Bear")
    bear = _animal("Bear")

    images = ImageDownloader(fake_client, settings).download_all([bear])

    assert images[bear.key].read_bytes() == IMAGE_BYTES
    assert images[bear.key].parent == settings.image_dir


def test_one_failed_download_does_not_affect_the_others(fake_client, settings):
    fake_client.add_image("Bear")
    fake_client.add_image("Seal")
    fake_client.routes[thumbnail_url("Seal")] = requests.ConnectionError("boom")
    bear, seal = _animal("Bear"), _animal("Seal")

    images = ImageDownloader(fake_client, settings).download_all([bear, seal])

    assert bear.key in images
    assert seal.key not in images


def test_an_article_without_a_picture_is_skipped_quietly(fake_client, settings):
    fake_client.routes[summary_url("Bear")] = lambda: make_response(b'{"title": "Bear"}')
    assert ImageDownloader(fake_client, settings).download_all([_animal("Bear")]) == {}


def test_an_animal_without_an_article_makes_no_requests(fake_client, settings):
    assert ImageDownloader(fake_client, settings).download_all([Animal("Yak")]) == {}
    assert fake_client.requests == []


def test_a_non_image_response_is_rejected_and_leaves_no_file(fake_client, settings):
    # For example an HTML error page served with a 200 status.
    fake_client.add_image("Bear")
    fake_client.routes[thumbnail_url("Bear")] = lambda: make_response(b"<html>", "text/html")

    assert ImageDownloader(fake_client, settings).download_all([_animal("Bear")]) == {}
    assert list(settings.image_dir.iterdir()) == []


def test_an_oversized_image_is_rejected_and_cleaned_up(fake_client, settings):
    fake_client.add_image("Bear")
    small_limit = replace(settings, max_image_bytes=len(IMAGE_BYTES) - 1)

    assert ImageDownloader(fake_client, small_limit).download_all([_animal("Bear")]) == {}
    assert list(settings.image_dir.iterdir()) == []


def test_a_non_https_image_url_is_refused_without_being_fetched(fake_client, settings):
    insecure = "http://example.com/x.jpg"
    body = f'{{"thumbnail": {{"source": "{insecure}"}}}}'.encode()
    fake_client.routes[summary_url("Bear")] = lambda: make_response(body)

    assert ImageDownloader(fake_client, settings).download_all([_animal("Bear")]) == {}
    assert insecure not in fake_client.requests


def test_a_second_run_reuses_files_without_any_network_requests(fake_client, settings):
    fake_client.add_image("Bear")
    downloader = ImageDownloader(fake_client, settings)
    first = downloader.download_all([_animal("Bear")])
    fake_client.requests.clear()

    second = downloader.download_all([_animal("Bear")])

    assert second == first
    assert fake_client.requests == []


def test_hostile_article_titles_cannot_escape_the_image_directory(fake_client, settings):
    # The title is percent-encoded "../../evil", so it decodes to a traversal path.
    title = "..%2F..%2Fevil"
    fake_client.add_image(title)
    animal = _animal(title)

    images = ImageDownloader(fake_client, settings).download_all([animal])

    assert images[animal.key].parent == settings.image_dir


def test_titles_that_reduce_to_the_same_slug_get_different_files(fake_client, settings):
    # "Rook_(bird)" and "Rook_bird" both slugify to "rook_bird".
    for title in ("Rook_(bird)", "Rook_bird"):
        fake_client.routes[summary_url(quote(title, safe=""))] = _summary_for(title)
        fake_client.routes[thumbnail_url(title)] = lambda: make_response(IMAGE_BYTES, "image/jpeg")
    first, second = _animal("Rook_(bird)"), _animal("Rook_bird")

    images = ImageDownloader(fake_client, settings).download_all([first, second])

    assert images[first.key] != images[second.key]


def test_downloads_really_run_in_parallel(fake_client, settings):
    # Both requests wait at the barrier until the other one arrives. A sequential
    # implementation could never get two threads here, so the barrier would time
    # out and fail the download. This proves concurrency without relying on timing.
    barrier = threading.Barrier(2, timeout=5)

    def thumbnail_after_rendezvous():
        barrier.wait()
        return make_response(IMAGE_BYTES, "image/jpeg")

    for title in ("Bear", "Seal"):
        fake_client.add_image(title)
        fake_client.routes[thumbnail_url(title)] = thumbnail_after_rendezvous
    bear, seal = _animal("Bear"), _animal("Seal")

    images = ImageDownloader(fake_client, settings).download_all([bear, seal])

    assert set(images) == {bear.key, seal.key}


def _summary_for(title: str):
    body = f'{{"thumbnail": {{"source": "{thumbnail_url(title)}"}}}}'.encode()
    return lambda: make_response(body)
