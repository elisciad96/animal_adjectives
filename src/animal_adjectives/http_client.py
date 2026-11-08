"""A small thread-safe HTTP client with timeouts and retries."""

from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from animal_adjectives.config import Settings


class HttpClient:
    """Wraps `requests` so that every call gets the same safe behaviour.

    Why not share one `requests.Session`? Its docs do not promise thread
    safety (it mutates cookies and connection state), so the safe design is one
    session per thread. `threading.local` gives us that with no locks, and each
    thread still reuses its own TCP/TLS connections, which is the main reason
    to have a session at all.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._local = threading.local()

    def get(self, url: str, *, stream: bool = False) -> requests.Response:
        """GET `url` and return the response, raising `HTTPError` on 4xx/5xx.

        Use the response as a context manager when `stream=True`, otherwise the
        connection is not returned to the pool.
        """
        response = self._session().get(url, timeout=self._settings.timeout, stream=stream)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            # A streamed response owns a connection until it is closed, and the
            # caller never receives this one, so it has to be closed here.
            response.close()
            raise
        return response

    def _session(self) -> requests.Session:
        """Return this thread's session, creating it on first use."""
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._build_session()
            self._local.session = session
        return session

    def _build_session(self) -> requests.Session:
        # Retrying at the transport level keeps the callers free of retry loops.
        # urllib3 also honours Retry-After, which is how Wikimedia tells a
        # client to slow down, so retrying this way stays polite.
        retry = Retry(
            total=self._settings.max_retries,
            backoff_factor=self._settings.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
            # Hand back the final bad response rather than raising urllib3's own
            # error, so that callers only ever have to handle requests' errors.
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)

        session = requests.Session()
        session.headers["User-Agent"] = self._settings.user_agent
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
