"""Session HTTP partagée pour tous les scrapers."""
from __future__ import annotations

import time
from contextlib import contextmanager

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",  # pas brotli (httpx nécessite la lib `brotli` pour ça)
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


@contextmanager
def http_client(**kwargs):
    """Context manager pour une session httpx avec defaults raisonnables."""
    client = httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        http2=True,
        **kwargs,
    )
    try:
        yield client
    finally:
        client.close()


def polite_sleep(seconds: float = 1.5) -> None:
    """Sleep entre les requêtes pour être correct avec les serveurs."""
    time.sleep(seconds)


def get_with_retry(client: httpx.Client, url: str, *, max_retries: int = 3) -> httpx.Response:
    """GET avec backoff exponentiel sur 429/503/timeouts."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.get(url)
            if resp.status_code in (429, 503):
                wait = 2 ** attempt * 2  # 2, 4, 8 secondes
                time.sleep(wait)
                continue
            return resp
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            time.sleep(2 ** attempt)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Échec après {max_retries} tentatives : {url}")
