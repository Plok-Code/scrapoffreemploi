"""Scraper HelloWork (https://www.hellowork.com).

Approche : HTML statique avec httpx + BeautifulSoup. Pas d'auth nécessaire.
Filtres :
  - URL de recherche : k=keyword, p=page (1-indexed)
  - Le filtre alternance ne semble pas exposable directement dans l'URL,
    on filtre côté code via le aria-label "pour un Alternance".

Structure HTML observée :
  [data-cy=serpCard]               → 1 carte par offre (30 par page)
   └─ a[data-cy=offerTitle]        → lien principal
       ├─ aria-label="Voir offre de TITLE à CITY - DEPT, chez COMPANY, pour un CONTRACT, avec un salaire de SALARY, en TIME"
       ├─ href="/fr-fr/emplois/{id}.html"
       ├─ title="TITLE - COMPANY"
       └─ <p class="tw-typo-l">TITLE</p>
          <p class="tw-typo-s">COMPANY</p>
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from backend.scrapers._http import (
    get_with_retry, http_client, polite_sleep,
)
from backend.scrapers._keywords import matches_keywords
from backend.scrapers.base import RawOffer, Scraper

BASE_URL = "https://www.hellowork.com"
SEARCH_URL = BASE_URL + "/fr-fr/emploi/recherche.html"

# Regex pour parser l'aria-label
ARIA_RE = re.compile(
    r"Voir offre de\s+(?P<title>.+?)"
    r"(?:\s+à\s+(?P<city>[^,]+?)(?:\s+-\s+(?P<department>\d{2,3}[A-Z]?))?)?"
    r"(?:\s*,\s*chez\s+(?P<company>[^,]+?))?"
    r"(?:\s*,\s*pour un\s+(?P<contract>[^,]+?))?"
    r"(?:\s*,\s*avec un salaire de\s+(?P<salary>[^,]+?))?"
    r"(?:\s*,\s*en\s+(?P<time>[^,]+?))?"
    r"\s*$",
    re.IGNORECASE,
)


class HelloWorkScraper(Scraper):
    source_name = "Hellowork"

    def fetch_list(
        self,
        *,
        keywords: list[str],
        max_pages: int = 5,
    ) -> list[RawOffer]:
        """Pour chaque keyword, parcourt jusqu'à max_pages.
        Dédoublonne par URL. Filtre alternance + mots-clés IA.
        """
        seen_urls: set[str] = set()
        results: list[RawOffer] = []

        with http_client() as client:
            for kw in keywords:
                for page in range(1, max_pages + 1):
                    url = (
                        f"{SEARCH_URL}?k={quote_plus(kw)}"
                        f"&st=relevance&d=all&p={page}"
                    )
                    resp = get_with_retry(client, url)
                    if resp.status_code != 200:
                        break

                    page_offers = self._parse_search_page(resp.text)
                    if not page_offers:
                        break  # plus d'offres → on arrête

                    new_count = 0
                    for off in page_offers:
                        # filtre alternance (mot-clé "Alternance" dans contract_type ou title)
                        if not self._is_alternance(off):
                            continue
                        # filtre IA/data
                        if not matches_keywords(off.title, off.description):
                            continue
                        # dédup par URL
                        if off.url and off.url in seen_urls:
                            continue
                        if off.url:
                            seen_urls.add(off.url)
                        results.append(off)
                        new_count += 1

                    if new_count == 0:
                        # Page entière déjà vue ou tout filtré → on arrête ce keyword
                        break

                    polite_sleep(1.5)

        return results

    def _parse_search_page(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("[data-cy=serpCard]")
        offers: list[RawOffer] = []
        for card in cards:
            try:
                offer = self._parse_card(card)
                if offer:
                    offers.append(offer)
            except Exception:  # noqa: BLE001
                # En cas de structure inattendue, skip plutôt que crash
                continue
        return offers

    def _parse_card(self, card) -> RawOffer | None:
        link = card.select_one("a[data-cy=offerTitle]")
        if not link:
            return None
        href = link.get("href", "")
        if not href:
            return None
        url = BASE_URL + href if href.startswith("/") else href

        # Préférer le DOM pour le titre/entreprise (plus fiable que le regex)
        title = self._text(card, "p.tw-typo-l, p.tw-typo-xl")
        company = self._text(card, "p.tw-typo-s")

        # L'aria-label sert pour city/dept/contract/salary
        aria = link.get("aria-label", "") or ""
        city = department = contract = salary = None
        if aria:
            city, department, contract, salary = self._parse_aria_label(aria)

        # Fallback titre via le title attribute si pas trouvé dans le DOM
        if not title:
            t_attr = link.get("title", "")
            if t_attr:
                # Format : "TITRE - ENTREPRISE"
                parts = t_attr.rsplit(" - ", 1)
                title = parts[0].strip() or None
                if not company and len(parts) > 1:
                    company = parts[1].strip() or None

        if not title:
            return None

        return RawOffer(
            title=title,
            company=company,
            city=city,
            department=department,
            url=url,
            source=self.source_name,
            contract_type=contract,
            salary=salary,
            raw={"aria_label": aria},
        )

    @staticmethod
    def _parse_aria_label(aria: str) -> tuple[str | None, str | None, str | None, str | None]:
        """Extrait (city, department, contract, salary) depuis l'aria-label.

        Format observé (groupes après le ", " séparateur) :
          "Voir offre de TITLE à CITY - DEPT, chez COMPANY, pour un CONTRACT,
           avec un salaire de SALARY, en temps plein"

        Approche : on splitte sur ", " et on extrait les segments connus.
        """
        # Split sur ", " — robuste car les segments suivent un format ", PRÉFIXE ..."
        parts = [p.strip() for p in aria.split(", ")]
        city = department = contract = salary = None
        # Le premier segment contient "Voir offre de TITLE à CITY - DEPT"
        first = parts[0] if parts else ""
        # Chercher " à " (avec espaces) qui démarre la zone localisation
        m_loc = re.search(r"\s+à\s+(.+?)(?:\s+-\s+(\d{2,3}[A-Z]?))?\s*$", first)
        if m_loc:
            city = (m_loc.group(1) or "").strip() or None
            department = (m_loc.group(2) or "").strip() or None
        # Les segments suivants : "chez COMPANY", "pour un CONTRACT", "avec un salaire de SALARY", "en TIME"
        for p in parts[1:]:
            lp = p.lower()
            if lp.startswith("pour un "):
                contract = p[len("pour un "):].strip() or None
            elif lp.startswith("avec un salaire de "):
                salary = p[len("avec un salaire de "):].strip() or None
        return city, department, contract, salary

    @staticmethod
    def _text(soup_node, css_sel: str) -> str | None:
        el = soup_node.select_one(css_sel)
        if not el:
            return None
        return el.get_text(strip=True) or None

    @staticmethod
    def _is_alternance(off: RawOffer) -> bool:
        """Garde uniquement les offres en alternance."""
        candidates = [
            (off.contract_type or "").lower(),
            (off.title or "").lower(),
        ]
        return any("alternance" in c or "apprentissage" in c for c in candidates)

    def fetch_detail(self, url: str) -> str | None:
        """Récupère la description complète d'une offre.

        Stratégie : parser le JSON-LD JobPosting (présent sur toutes les pages
        détail HelloWork, contient description HTML complète).
        Fallback : parser le HTML brut.
        """
        with http_client() as client:
            resp = get_with_retry(client, url)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "lxml")

            # 1) Stratégie JSON-LD JobPosting (la plus propre)
            import json as _json
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = _json.loads(script.string or "{}")
                except (_json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("@type") == "JobPosting":
                    desc_html = data.get("description", "")
                    if desc_html:
                        # Strip HTML pour avoir du texte propre
                        inner = BeautifulSoup(desc_html, "lxml")
                        text = inner.get_text(separator="\n", strip=True)
                        text = re.sub(r"\n{3,}", "\n\n", text)
                        if len(text) > 200:
                            return text

            # 2) Fallback : HTML brut
            for sel in ("[data-cy=jobBody]", "article", "main"):
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    text = re.sub(r"\n{3,}", "\n\n", text)
                    if len(text) > 200:
                        return text
            return None


# Test rapide en CLI : `python -m backend.scrapers.hellowork`
if __name__ == "__main__":
    scraper = HelloWorkScraper()
    offers = scraper.fetch_list(
        keywords=["alternance intelligence artificielle", "alternance machine learning"],
        max_pages=2,
    )
    print(f"Trouvé {len(offers)} offres en alternance IA")
    for o in offers[:5]:
        print(f"  - {o.title} @ {o.company} ({o.city or '?'}, {o.department or '?'})")
        print(f"      {o.url}")
