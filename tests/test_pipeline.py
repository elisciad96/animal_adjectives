"""End-to-end tests of the whole flow, with only the network replaced."""

from __future__ import annotations

import pytest
import requests

from animal_adjectives.cli import main
from animal_adjectives.errors import PageStructureError
from animal_adjectives.pipeline import run
from conftest import BASE_URL, make_response

SAMPLE_ARTICLES = ("Bird", "Cattle", "Domestic_pig", "Raccoon", "Civet", "Bear", "Sea_urchin")


@pytest.fixture
def client_with_page(fake_client, sample_html):
    fake_client.routes[BASE_URL] = lambda: make_response(sample_html.encode(), "text/html")
    for title in SAMPLE_ARTICLES:
        fake_client.add_image(title)
    return fake_client


def test_full_run_writes_a_report_with_every_adjective_and_local_links(client_with_page, settings):
    summary = run(settings, client_with_page)

    html = settings.output_path.read_text(encoding="utf-8")
    for adjective in ("avian", "bovine", "taurine", "ursine", "viverrine", "echinoid"):
        assert f"<h2>{adjective} " in html
    assert html.count("Local image") >= summary.animal_count
    assert "file:" in html

    assert summary.animal_count == len(SAMPLE_ARTICLES)
    assert summary.image_count == len(SAMPLE_ARTICLES)
    assert summary.animals_without_image == ()
    assert len(list(settings.image_dir.iterdir())) == len(SAMPLE_ARTICLES)


def test_each_animal_is_downloaded_once_despite_several_adjectives(client_with_page, settings):
    run(settings, client_with_page)
    downloads = [url for url in client_with_page.requests if "upload.wikimedia.org" in url]
    assert len(downloads) == len(set(downloads)) == len(SAMPLE_ARTICLES)


def test_missing_pictures_are_reported_but_do_not_fail_the_run(client_with_page, settings):
    del client_with_page.routes["https://en.wikipedia.org/api/rest_v1/page/summary/Bear"]

    summary = run(settings, client_with_page)

    assert summary.animals_without_image == ("Bear",)
    assert settings.output_path.exists()


def test_a_changed_page_layout_fails_and_writes_no_report(fake_client, settings):
    fake_client.routes[BASE_URL] = lambda: make_response(b"<html></html>", "text/html")

    with pytest.raises(PageStructureError):
        run(settings, fake_client)
    assert not settings.output_path.exists()


def test_cli_returns_a_failure_code_when_the_page_cannot_be_fetched(monkeypatch, tmp_path):
    def unreachable(self, url, *, stream=False):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr("animal_adjectives.http_client.HttpClient.get", unreachable)

    exit_code = main(["-o", str(tmp_path / "r.html"), "--image-dir", str(tmp_path / "i")])

    assert exit_code == 1
    assert not (tmp_path / "r.html").exists()


@pytest.mark.parametrize("workers", ["0", "-1", "many"])
def test_cli_rejects_invalid_worker_counts(workers):
    with pytest.raises(SystemExit) as error:
        main(["--workers", workers])
    assert error.value.code == 2  # argparse's usage-error code
