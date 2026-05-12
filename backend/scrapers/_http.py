"""Session HTTP partagée pour tous les scrapers.

Politesse + Résilience (niveau ultra senior) :
- User-Agent Chrome réaliste
- Pas de brotli (httpx sans la lib `brotli` reçoit du binaire)
- Retries avec exponential backoff via `tenacity` (4 tentatives, 2/4/8/16s)
- Rate limiter global avec pauses aléatoires entre requêtes (anti-ban IP)
"""
from __future__ import annotations

import random
import time
from contextlib import contextmanager

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from backend._logging import logger

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


# --- Rate limiter global (pauses aléatoires anti-ban) ---

class RateLimiter:
    """Rate limiter avec pauses aléatoires entre requêtes pour préserver l'IP.

    Génère un délai entre `min_delay` et `max_delay` secondes (uniforme aléatoire)
    avant chaque `acquire()`. Simule un comportement humain — un scraper qui hit
    à intervalle régulier (1.5s pile) est trivial à détecter et bannir.

    Usage :
        rl = RateLimiter(min_delay=1.5, max_delay=3.2)
        for url in urls:
            rl.acquire()  # bloque jusqu'à ce que le délai soit écoulé
            client.get(url)
    """

    def __init__(self, min_delay: float = 1.5, max_delay: float = 3.2):
        if min_delay > max_delay:
            raise ValueError("min_delay > max_delay")
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_call: float = 0.0

    def acquire(self) -> None:
        """Bloque jusqu'à ce que le prochain délai soit OK."""
        now = time.time()
        # random non-crypto OK : juste du jitter anti-fingerprint pour pas être bot-régulier
        target_delay = random.uniform(self.min_delay, self.max_delay)  # nosec B311
        elapsed = now - self._last_call
        if elapsed < target_delay:
            time.sleep(target_delay - elapsed)
        self._last_call = time.time()


# Limiter global partagé par tous les scrapers HTTP (peut être surchargé par scraper)
DEFAULT_RATE_LIMITER = RateLimiter(min_delay=1.0, max_delay=2.5)


def polite_sleep(seconds: float = 1.5) -> None:
    """Sleep simple (DEPRECATED — préférer RateLimiter pour vraie politesse).

    Conservé pour compat avec le code existant.
    """
    # Ajoute un peu de jitter même ici (±20%) pour pas être trop régulier
    # random non-crypto OK (anti-fingerprint, pas de secret généré)
    actual = seconds * random.uniform(0.8, 1.2)  # nosec B311
    time.sleep(actual)


# --- Retries avec exponential backoff (tenacity) ---

def _is_retryable_status(resp: httpx.Response) -> bool:
    """Détermine si un status code mérite un retry (transient errors)."""
    return resp.status_code in (429, 500, 502, 503, 504)


def _is_retryable_exception(exc: BaseException) -> bool:
    """Détermine si une exception réseau mérite un retry."""
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16),
    retry=(
        retry_if_exception(_is_retryable_exception)
        | retry_if_result(_is_retryable_status)
    ),
    reraise=True,
)
def _get_with_retry_inner(client: httpx.Client, url: str) -> httpx.Response:
    """Inner : raw GET avec retries via tenacity (2s, 4s, 8s, 16s max)."""
    return client.get(url)


def get_with_retry(client: httpx.Client, url: str, *, max_retries: int = 4) -> httpx.Response:
    """GET avec retries exponential backoff (tenacity).

    Args:
        max_retries: nombre max de tentatives. Ignoré — on utilise le decorator
            global (4 tentatives = 1 initial + 3 retries, attente 2-4-8s).
            Conservé pour compat avec ancien code.
    """
    try:
        return _get_with_retry_inner(client, url)
    except RetryError as e:
        logger.error("Retries épuisés pour {url} : {err}", url=url, err=str(e))
        raise
    except httpx.HTTPError as e:
        logger.warning("HTTP error sur {url} : {err}", url=url, err=str(e))
        raise
