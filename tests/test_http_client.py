from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from animal_adjectives.config import Settings
from animal_adjectives.http_client import HttpClient


def test_each_thread_gets_its_own_session_and_keeps_reusing_it():
    client = HttpClient(Settings())

    with ThreadPoolExecutor(max_workers=1) as pool:
        other_thread_session = pool.submit(client._session).result()

    assert client._session() is client._session()
    assert client._session() is not other_thread_session


def test_sessions_identify_themselves_and_retry_rate_limits():
    settings = Settings()
    session = HttpClient(settings)._session()

    assert session.headers["User-Agent"] == settings.user_agent
    retry = session.get_adapter("https://en.wikipedia.org").max_retries
    assert retry.total == settings.max_retries
    assert 429 in retry.status_forcelist
