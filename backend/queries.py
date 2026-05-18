"""Couche d'accès aux données : requêtes sur la table offers."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from backend.db import db


# ---------- Helpers ----------

def _row_to_dict(row: sqlite3.Row | None) -> Optional[dict]:
    return dict(row) if row is not None else None


# ---------- Reads ----------

def get_offer(offer_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
    return _row_to_dict(row)


def _offer_filters(
    *,
    search: str = "",
    status: str = "",
    source: str = "",
    min_score: int | None = None,
    only_to_apply: bool = False,
    include_archived: bool = False,
) -> tuple[list[str], list[Any]]:
    where = []
    params: list[Any] = []

    if not include_archived:
        where.append("(is_active IS NULL OR is_active = 1)")

    if search:
        where.append("(LOWER(title) LIKE ? OR LOWER(company) LIKE ? OR LOWER(city) LIKE ?)")
        s = f"%{search.lower()}%"
        params.extend([s, s, s])

    if status:
        if status == "_NONE_":
            where.append("status IS NULL")
        else:
            where.append("status = ?")
            params.append(status)

    if source:
        where.append("source = ?")
        params.append(source)

    if min_score is not None:
        where.append("match_score >= ?")
        params.append(min_score)

    if only_to_apply:
        where.append("status IS NULL")

    return where, params


def count_offers(
    *,
    search: str = "",
    status: str = "",
    source: str = "",
    min_score: int | None = None,
    only_to_apply: bool = False,
    include_archived: bool = False,
) -> int:
    """Compte les offres correspondant aux filtres UI."""
    where, params = _offer_filters(
        search=search,
        status=status,
        source=source,
        min_score=min_score,
        only_to_apply=only_to_apply,
        include_archived=include_archived,
    )
    sql = "SELECT COUNT(*) AS n FROM offers"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with db() as conn:
        return int(conn.execute(sql, params).fetchone()["n"])


def list_offers(
    *,
    search: str = "",
    status: str = "",
    source: str = "",
    min_score: int | None = None,
    only_to_apply: bool = False,
    include_archived: bool = False,
    sort: str = "score_desc",
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Liste filtrée des offres. Filtres optionnels.

    Par défaut exclut les offres archivées (is_active = 0). Passer
    include_archived=True pour les inclure.
    """
    where, params = _offer_filters(
        search=search,
        status=status,
        source=source,
        min_score=min_score,
        only_to_apply=only_to_apply,
        include_archived=include_archived,
    )

    sql = "SELECT * FROM offers"
    if where:
        sql += " WHERE " + " AND ".join(where)

    sort_clauses = {
        "score_desc": "match_score DESC NULLS LAST, date_published DESC",
        "score_asc": "match_score ASC NULLS LAST",
        "date_desc": "date_published DESC NULLS LAST",
        "date_asc": "date_published ASC NULLS LAST",
        "company": "LOWER(company) ASC NULLS LAST",
        "title": "LOWER(title) ASC NULLS LAST",
    }
    sql += " ORDER BY " + sort_clauses.get(sort, sort_clauses["score_desc"])
    sql += " LIMIT ? OFFSET ?"
    params.extend([max(1, int(limit)), max(0, int(offset))])

    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_sources() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT source FROM offers WHERE source IS NOT NULL AND source != '' ORDER BY source"
        ).fetchall()
    return [r["source"] for r in rows]


def list_distinct_statuses() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT status FROM offers WHERE status IS NOT NULL AND status != '' ORDER BY status"
        ).fetchall()
    return [r["status"] for r in rows]


def get_stats() -> dict:
    """KPIs pour la barre de stats en haut de page.

    Une SEULE requête SQL avec `SUM(CASE WHEN cond THEN 1 ELSE 0 END)` —
    ~10× plus rapide que 9 `SELECT COUNT(*)` séparés sur 1000+ offres
    (un seul scan de table + un seul commit côté WAL).

    Toutes les conditions sont des littéraux SQL constants (pas d'input user),
    bandit-clean sans `# nosec`.

    Notes :
    - `is_active IS NULL OR is_active = 1` = "offre active" (NULL = pré-migration v2)
    - `archived` compte les offres avec `is_active = 0` (à exclure des autres KPIs)
    - `top_fit` ≥ 80, `bon_fit` ∈ [60, 80[ — cf `models.label_for_score`
    """
    sql = """
        SELECT
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                     THEN 1 ELSE 0 END) AS total,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND status IS NULL
                     THEN 1 ELSE 0 END) AS to_apply,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND status = 'Postulé'
                     THEN 1 ELSE 0 END) AS applied,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND status = 'Entretien'
                     THEN 1 ELSE 0 END) AS interviews,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND status = 'Refusé'
                     THEN 1 ELSE 0 END) AS refused,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND match_score >= 80
                     THEN 1 ELSE 0 END) AS top_fit,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND match_score >= 60 AND match_score < 80
                     THEN 1 ELSE 0 END) AS bon_fit,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND match_score IS NULL
                     THEN 1 ELSE 0 END) AS unscored,
            SUM(CASE WHEN (is_active IS NULL OR is_active = 1)
                          AND status = 'Pas intéressé'
                     THEN 1 ELSE 0 END) AS not_interested,
            SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS archived
        FROM offers
    """
    with db() as conn:
        row = conn.execute(sql).fetchone()
    # `SUM(0 rows)` retourne NULL en SQLite → on coerce à 0 pour stabilité du retour.
    return {k: int(row[k] or 0) for k in (
        "total", "to_apply", "applied", "interviews", "refused",
        "top_fit", "bon_fit", "unscored", "not_interested", "archived",
    )}


# ---------- Writes ----------

ALLOWED_UPDATE_FIELDS = {
    "status", "application_method", "date_applied", "date_followup",
    "date_interview", "notes", "priority", "remote",
}


def update_description(offer_id: int, description: str) -> bool:
    """Met à jour uniquement le champ description d'une offre."""
    with db() as conn:
        cur = conn.execute(
            "UPDATE offers SET description = :desc WHERE id = :id",
            {"desc": description, "id": offer_id},
        )
        return cur.rowcount > 0


def delete_offer(offer_id: int) -> bool:
    """Supprime définitivement une offre. Réservé au cleanup des URLs mortes
    sans statut user (l'historique applicatif est préservé)."""
    with db() as conn:
        cur = conn.execute("DELETE FROM offers WHERE id = :id", {"id": offer_id})
        return cur.rowcount > 0


def set_alive_state(offer_id: int, *, is_active: bool) -> bool:
    """Marque l'offre active (1) ou archivée (0) et stamp last_checked_at."""
    with db() as conn:
        cur = conn.execute(
            """
            UPDATE offers
            SET is_active = :state, last_checked_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """,
            {"state": 1 if is_active else 0, "id": offer_id},
        )
        return cur.rowcount > 0


def set_alive_state_bulk(updates: list[tuple[int, bool]]) -> int:
    """Bulk update `is_active` + stamp `last_checked_at` sur N offres en
    **une seule transaction**.

    Utilisé par `cleanup_dead_unstatused` et `check_alive` qui peuvent toucher
    1000+ offres par run : 1 transaction au lieu de N évite l'effet "à mi-chemin"
    (Ctrl+C / crash uvicorn) et gagne ~10× en perf (WAL commit unique).

    Args:
        updates: liste de tuples `(offer_id, is_active_bool)`.

    Returns:
        Le nombre de rows réellement updatées (somme des `rowcount`).
    """
    if not updates:
        return 0
    payload = [(1 if state else 0, oid) for oid, state in updates]
    with db() as conn:
        cur = conn.executemany(
            """
            UPDATE offers
            SET is_active = ?, last_checked_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            payload,
        )
        return cur.rowcount


def delete_offers_bulk(ids: list[int]) -> int:
    """Bulk DELETE sur N offres en **une seule transaction**.

    Réservé au cleanup des URLs mortes + status NULL (mode purge explicite,
    `hard_delete_unstatused=True`). L'historique applicatif des offres ayant
    un statut user est préservé via `set_alive_state_bulk(..., False)`.

    Args:
        ids: liste d'`offer_id` à supprimer.

    Returns:
        Le nombre de rows réellement supprimées.
    """
    if not ids:
        return 0
    # SAFE (B608) : `placeholders` est une chaîne `"?,?,..."` générée
    # uniquement à partir de la LONGUEUR de `ids` — jamais à partir du contenu.
    # Tous les ids passent par sqlite3 via `conn.execute(sql, ids)` (params
    # positionnels, escaping géré par le driver).
    placeholders = ",".join("?" * len(ids))
    sql = f"DELETE FROM offers WHERE id IN ({placeholders})"  # nosec B608
    with db() as conn:
        cur = conn.execute(sql, ids)
        return cur.rowcount


def insert_offer(offer_data: dict) -> tuple[int | None, bool]:
    """Insère une offre nouvelle. Dédup par URL puis par dedup_key (title+company+city).

    Returns:
        (offer_id, was_new) — was_new=False si doublon (offer_id du doublon retourné).
    """
    from backend.db import make_dedup_key

    title = offer_data.get("title")
    company = offer_data.get("company")
    city = offer_data.get("city")
    url = offer_data.get("url")
    if not title:
        raise ValueError("Offer must have a title")

    # IMPORTANT : la ville fait partie du dedup_key.
    # Sinon "AI Engineer Capgemini Paris" et "AI Engineer Capgemini Toulouse"
    # seraient considérés comme doublons (bug majeur pour la recherche d'emploi).
    dedup_key = make_dedup_key(title, company, city)

    with db() as conn:
        # 1) Vérif URL
        if url:
            existing = conn.execute(
                "SELECT id FROM offers WHERE url = ?", (url,)
            ).fetchone()
            if existing:
                return existing["id"], False
        # 2) Vérif dedup_key
        existing = conn.execute(
            "SELECT id FROM offers WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()
        if existing:
            return existing["id"], False

        # Insert
        sql = """
            INSERT INTO offers (
                title, company, city, department, source, url, description,
                date_published, remote, contract_type, salary, dedup_key, scraped_at
            ) VALUES (
                :title, :company, :city, :department, :source, :url, :description,
                :date_published, :remote, :contract_type, :salary, :dedup_key,
                CURRENT_TIMESTAMP
            )
        """
        params = {
            "title": title,
            "company": company,
            "city": offer_data.get("city"),
            "department": offer_data.get("department"),
            "source": offer_data.get("source"),
            "url": url,
            "description": offer_data.get("description"),
            "date_published": offer_data.get("date_published"),
            "remote": offer_data.get("remote"),
            "contract_type": offer_data.get("contract_type"),
            "salary": offer_data.get("salary"),
            "dedup_key": dedup_key,
        }
        cur = conn.execute(sql, params)
        return cur.lastrowid, True


def insert_offers_bulk(offers: list[dict]) -> tuple[list[int], int]:
    """Insère un batch d'offres en UNE SEULE transaction (bien plus rapide
    que `insert_offer` × N).

    Dédup en mémoire avant l'INSERT (URL + dedup_key calculé via title+company+city).

    Returns:
        (new_ids, duplicates_count). `new_ids` = liste des ids des offres réellement
        insérées (taille ≤ len(offers)). `duplicates_count` = nb de doublons skippés.
    """
    from backend.db import make_dedup_key

    if not offers:
        return [], 0

    new_ids: list[int] = []
    duplicates = 0
    insert_sql = """
        INSERT INTO offers (
            title, company, city, department, source, url, description,
            date_published, remote, contract_type, salary, dedup_key, scraped_at
        ) VALUES (
            :title, :company, :city, :department, :source, :url, :description,
            :date_published, :remote, :contract_type, :salary, :dedup_key,
            CURRENT_TIMESTAMP
        )
    """
    with db() as conn:
        # Charge les URLs et dedup_keys existants en mémoire (1 seule query)
        existing_urls = {
            r["url"] for r in conn.execute(
                "SELECT url FROM offers WHERE url IS NOT NULL AND url != ''"
            ).fetchall()
        }
        existing_dedup_keys = {
            r["dedup_key"] for r in conn.execute(
                "SELECT dedup_key FROM offers WHERE dedup_key IS NOT NULL"
            ).fetchall()
        }

        seen_in_batch_urls: set[str] = set()
        seen_in_batch_keys: set[str] = set()
        to_insert: list[dict] = []
        for off in offers:
            title = off.get("title")
            if not title:
                continue
            url = off.get("url")
            key = make_dedup_key(title, off.get("company"), off.get("city"))
            # Dédup contre la DB
            if url and url in existing_urls:
                duplicates += 1
                continue
            if key in existing_dedup_keys:
                duplicates += 1
                continue
            # Dédup contre le batch lui-même (au cas où le scraper retourne des doublons)
            if url and url in seen_in_batch_urls:
                duplicates += 1
                continue
            if key in seen_in_batch_keys:
                duplicates += 1
                continue
            if url:
                seen_in_batch_urls.add(url)
            seen_in_batch_keys.add(key)
            to_insert.append({
                "title": title,
                "company": off.get("company"),
                "city": off.get("city"),
                "department": off.get("department"),
                "source": off.get("source"),
                "url": url,
                "description": off.get("description"),
                "date_published": off.get("date_published"),
                "remote": off.get("remote"),
                "contract_type": off.get("contract_type"),
                "salary": off.get("salary"),
                "dedup_key": key,
            })

        # Single transaction : executemany avec lastrowid pour récupérer les ids
        for params in to_insert:
            cur = conn.execute(insert_sql, params)
            new_ids.append(cur.lastrowid)

    return new_ids, duplicates


def record_scrape_run(
    *,
    sources: str,
    total_fetched: int,
    total_new: int,
    total_duplicates: int,
    batch_file: str | None = None,
    error: str | None = None,
) -> int:
    """Enregistre une exécution de scrape dans scrape_runs."""
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO scrape_runs (
                sources, total_fetched, total_new, total_duplicates,
                batch_file, error, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (sources, total_fetched, total_new, total_duplicates, batch_file, error),
        )
        return cur.lastrowid


def update_offer(offer_id: int, fields: dict[str, Any]) -> bool:
    """Update partiel d'une offre. Ne touche que les champs whitelist + valide enums.

    Lève `ValueError` si un champ enum (status/priority/remote) reçoit une valeur
    hors `VALID_STATUSES / VALID_PRIORITIES / VALID_REMOTE`. FastAPI convertit
    le ValueError en 422 automatiquement via les routes.
    """
    from backend.models import VALID_PRIORITIES, VALID_REMOTE, VALID_STATUSES

    clean = {k: (v if v not in ("", None) else None) for k, v in fields.items() if k in ALLOWED_UPDATE_FIELDS}
    if not clean:
        return False
    # Validation enum côté queries (défense en profondeur — même si l'UI valide,
    # un POST/PATCH direct ne doit pas pouvoir bypasser)
    _validate_enum("status", clean.get("status"), VALID_STATUSES)
    _validate_enum("priority", clean.get("priority"), VALID_PRIORITIES)
    _validate_enum("remote", clean.get("remote"), VALID_REMOTE)

    # SAFE (B608) : `clean` est filtré par ALLOWED_UPDATE_FIELDS (whitelist
    # module-level constante). Les noms de colonnes injectés dans le SQL ne
    # peuvent donc PAS venir d'un input user. Les valeurs passent via :name
    # (params nommés, escaping sqlite3).
    set_clause = ", ".join(f"{k} = :{k}" for k in clean)
    sql = f"UPDATE offers SET {set_clause} WHERE id = :id"  # nosec B608
    clean["id"] = offer_id
    with db() as conn:
        cur = conn.execute(sql, clean)
        return cur.rowcount > 0


def _validate_enum(field_name: str, value, allowed: tuple) -> None:
    """Lève ValueError si `value` n'est pas None/'' et pas dans `allowed`."""
    if value is None or value == "":
        return
    if value not in allowed:
        raise ValueError(
            f"{field_name}={value!r} invalide. Valeurs autorisées : {allowed}"
        )


# ---------- Target companies (phase 2 — candidature spontanée) ----------

ALLOWED_COMPANY_UPDATE_FIELDS = {
    "status", "date_contacted", "date_followup", "notes", "feedback", "priority",
}


def _target_company_filters(
    *,
    search: str = "",
    priority: str = "",
    status: str = "",
    city: str = "",
    other_haute: bool = False,
) -> tuple[list[str], list[Any]]:
    where = []
    params: list[Any] = []

    if search:
        where.append("(LOWER(name) LIKE ? OR LOWER(sector) LIKE ?)")
        s = f"%{search.lower()}%"
        params.extend([s, s])
    if priority:
        where.append("priority = ?")
        params.append(priority)
    if status:
        if status == "_NONE_":
            where.append("status IS NULL")
        else:
            where.append("status = ?")
            params.append(status)
    if city:
        where.append("LOWER(city) LIKE ?")
        params.append(f"%{city.lower()}%")
    if other_haute:
        where.append("priority = 'Haute'")
        for p in TARGET_CITIES:
            where.append("LOWER(COALESCE(city, '')) NOT LIKE ?")
            params.append(f"%{p.lower()}%")

    return where, params


def count_target_companies(
    *,
    search: str = "",
    priority: str = "",
    status: str = "",
    city: str = "",
    other_haute: bool = False,
) -> int:
    """Compte les entreprises cibles correspondant aux filtres UI."""
    where, params = _target_company_filters(
        search=search,
        priority=priority,
        status=status,
        city=city,
        other_haute=other_haute,
    )
    sql = "SELECT COUNT(*) AS n FROM target_companies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with db() as conn:
        return int(conn.execute(sql, params).fetchone()["n"])


def list_target_companies(
    *,
    search: str = "",
    priority: str = "",
    status: str = "",
    city: str = "",
    other_haute: bool = False,
    sort: str = "priority",
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Liste filtrée des entreprises cibles (candidature spontanée).

    Le filtre `city` accepte une sous-chaîne (LIKE) — utile pour matcher
    "Toulouse" ou "31 - Toulouse" etc.

    `other_haute=True` : tab spécial = entreprises priorité Haute dans les villes
    hors les 5 cibles (Toulouse/Bordeaux/Pau/Paris/Nancy). Permet de voir les
    pépites Haute partout en France.
    """
    where, params = _target_company_filters(
        search=search,
        priority=priority,
        status=status,
        city=city,
        other_haute=other_haute,
    )

    sql = "SELECT * FROM target_companies"
    if where:
        sql += " WHERE " + " AND ".join(where)

    sort_clauses = {
        "priority": (
            "CASE priority WHEN 'Haute' THEN 1 WHEN 'Moyenne' THEN 2 "
            "WHEN 'Basse' THEN 3 ELSE 4 END ASC, LOWER(name) ASC"
        ),
        "name": "LOWER(name) ASC",
        "sector": "LOWER(sector) ASC NULLS LAST, LOWER(name) ASC",
        "city": "LOWER(city) ASC NULLS LAST, LOWER(name) ASC",
        "recent": "updated_at DESC",
    }
    sql += " ORDER BY " + sort_clauses.get(sort, sort_clauses["priority"])
    sql += " LIMIT ? OFFSET ?"
    params.extend([max(1, int(limit)), max(0, int(offset))])

    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_company_cities() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT city FROM target_companies WHERE city IS NOT NULL AND city != '' ORDER BY city"
        ).fetchall()
    return [r["city"] for r in rows]


# Villes cibles fixes du projet (5 villes utilisateur)
TARGET_CITIES = ("Toulouse", "Bordeaux", "Pau", "Paris", "Nancy")


def count_companies_per_target_city() -> list[dict]:
    """Pour chaque ville cible fixe, compte les entreprises matchant (city LIKE)."""
    results: list[dict] = []
    with db() as conn:
        for city in TARGET_CITIES:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM target_companies WHERE LOWER(city) LIKE ?",
                (f"%{city.lower()}%",),
            ).fetchone()["n"]
            results.append({"name": city, "count": n})
    return results


def count_other_haute() -> int:
    """Compte les entreprises priorité Haute dans des villes hors-5-cibles."""
    where_parts = ["priority = 'Haute'"]
    params: list = []
    for c in TARGET_CITIES:
        where_parts.append("LOWER(COALESCE(city, '')) NOT LIKE ?")
        params.append(f"%{c.lower()}%")
    # SAFE (B608) : `where_parts` ne contient que des fragments SQL littéraux
    # ("priority = 'Haute'", "LOWER(COALESCE(city, '')) NOT LIKE ?") construits
    # dans la fonction depuis la constante TARGET_CITIES. Aucun input user
    # n'est interpolé. Les valeurs des villes (params LIKE) partent via `?`.
    sql = f"SELECT COUNT(*) AS n FROM target_companies WHERE {' AND '.join(where_parts)}"  # nosec B608
    with db() as conn:
        return conn.execute(sql, params).fetchone()["n"]


def extract_companies_from_offers_by_city(
    *,
    city_substr: str,
    min_score: int = 0,
    limit: int = 200,
) -> list[dict]:
    """Liste les entreprises distinctes (avec offres data/IA) pour une ville.

    Renvoie le nom, secteur déduit (1ère source), nb d'offres, ville, score max.
    Utilisé pour suggérer des entreprises cibles à candidature spontanée pour
    une zone (ex : Toulouse). Inclut par défaut TOUTES les offres (même Faible)
    car l'utilisateur veut des cibles à contacter en spontané, pas un classement IA.
    """
    sql = """
        SELECT
            company AS name,
            MAX(source) AS source,
            COUNT(*) AS n_offers,
            MAX(match_score) AS max_score,
            MIN(city) AS city,
            MAX(url) AS sample_url
        FROM offers
        WHERE company IS NOT NULL AND company != ''
          AND LOWER(city) LIKE :city
          AND (is_active IS NULL OR is_active = 1)
          AND (match_score IS NULL OR match_score >= :min_score)
        GROUP BY LOWER(company)
        ORDER BY max_score DESC NULLS LAST, n_offers DESC
        LIMIT :limit
    """
    with db() as conn:
        rows = conn.execute(
            sql,
            {"city": f"%{city_substr.lower()}%", "min_score": min_score, "limit": limit},
        ).fetchall()
    return [dict(r) for r in rows]


def import_companies_from_offers_to_targets(*, city_substr: str, min_score: int = 0) -> dict:
    """Importe en `target_companies` les entreprises distinctes ayant des
    offres data/IA sur la ville donnée.

    Pour chaque entreprise distincte, dédup sur LOWER(name). Ajoute avec
    priorité "Moyenne" par défaut. Marque source = "offre {ville} agrégée".
    """
    companies = extract_companies_from_offers_by_city(
        city_substr=city_substr, min_score=min_score, limit=500
    )
    inserted = 0
    skipped = 0
    for c in companies:
        max_score = c.get("max_score")
        score_note = f" (score max {max_score})" if max_score else ""
        sample_url = c.get("sample_url") or "(pas d'URL)"
        data = {
            "name": c["name"],
            "city": city_substr.title(),
            "sector": None,
            "relevance": (
                f"Entreprise détectée via {c['n_offers']} offre(s) data/IA"
                f"{score_note}"
                f" sur le bassin {city_substr.title()}."
                f" Cible candidature spontanée."
            ),
            "priority": "Moyenne",
            "contact_channel": "Candidature spontanée directe (site corporate, LinkedIn, email RH)",
            "notes": f"Offre type vue : {sample_url}",
            "source": f"offres-agrégées-{city_substr.lower()}",
        }
        _id, was_new = insert_target_company(data)
        if was_new:
            inserted += 1
        else:
            skipped += 1
    return {"city": city_substr, "candidates": len(companies), "inserted": inserted, "skipped_dup": skipped}


def insert_target_company(data: dict) -> tuple[int | None, bool]:
    """Insère une entreprise cible. Dédup sur (LOWER(name), LOWER(city)).

    Une même entreprise peut exister plusieurs fois si elle a plusieurs implantations
    (ex : Capgemini Paris, Capgemini Toulouse, etc.).

    Returns:
        (id, was_new). was_new=False si déjà présente sur cette ville.
    """
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    city = (data.get("city") or "").strip().lower()
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM target_companies "
            "WHERE LOWER(name) = LOWER(?) AND LOWER(COALESCE(city, '')) = ?",
            (name, city),
        ).fetchone()
        if existing:
            return existing["id"], False
        cur = conn.execute(
            """
            INSERT INTO target_companies (
                name, sector, city, relevance, priority, contact_channel,
                contact_name, notes, feedback, email, reliability,
                source_url, source
            ) VALUES (
                :name, :sector, :city, :relevance, :priority, :contact_channel,
                :contact_name, :notes, :feedback, :email, :reliability,
                :source_url, :source
            )
            """,
            {
                "name": name,
                "sector": data.get("sector"),
                "city": data.get("city"),
                "relevance": data.get("relevance"),
                "priority": data.get("priority"),
                "contact_channel": data.get("contact_channel"),
                "contact_name": data.get("contact_name"),
                "notes": data.get("notes"),
                "feedback": data.get("feedback"),
                "email": data.get("email"),
                "reliability": data.get("reliability"),
                "source_url": data.get("source_url"),
                "source": data.get("source", "manual"),
            },
        )
        return cur.lastrowid, True


def get_target_company(company_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM target_companies WHERE id = ?", (company_id,)
        ).fetchone()
    return _row_to_dict(row)


def update_target_company(company_id: int, fields: dict[str, Any]) -> bool:
    """Update partiel d'une entreprise cible. Whitelist + validation enums."""
    from backend.models import VALID_COMPANY_STATUSES, VALID_PRIORITIES

    clean = {
        k: (v if v not in ("", None) else None)
        for k, v in fields.items()
        if k in ALLOWED_COMPANY_UPDATE_FIELDS
    }
    if not clean:
        return False
    _validate_enum("status", clean.get("status"), VALID_COMPANY_STATUSES)
    _validate_enum("priority", clean.get("priority"), VALID_PRIORITIES)

    # SAFE (B608) : même pattern que `update_offer` — `clean` est filtré par
    # ALLOWED_COMPANY_UPDATE_FIELDS (whitelist constante). Les colonnes
    # injectées sont garanties dans une liste finie connue à l'écriture du code.
    # Les valeurs passent via :name.
    set_clause = ", ".join(f"{k} = :{k}" for k in clean)
    sql = f"UPDATE target_companies SET {set_clause} WHERE id = :id"  # nosec B608
    clean["id"] = company_id
    with db() as conn:
        cur = conn.execute(sql, clean)
        return cur.rowcount > 0


def list_company_priorities() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT priority FROM target_companies WHERE priority IS NOT NULL AND priority != '' ORDER BY priority"
        ).fetchall()
    return [r["priority"] for r in rows]


def get_company_stats() -> dict:
    """KPIs pour la page Entreprises."""
    with db() as conn:
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM target_companies").fetchone()[0]
        to_contact = cur.execute(
            "SELECT COUNT(*) FROM target_companies WHERE status IS NULL"
        ).fetchone()[0]
        contacted = cur.execute(
            "SELECT COUNT(*) FROM target_companies WHERE status = 'Contacté'"
        ).fetchone()[0]
        interviews = cur.execute(
            "SELECT COUNT(*) FROM target_companies WHERE status = 'Entretien'"
        ).fetchone()[0]
        refused = cur.execute(
            "SELECT COUNT(*) FROM target_companies WHERE status = 'Refusé'"
        ).fetchone()[0]
        haute = cur.execute(
            "SELECT COUNT(*) FROM target_companies WHERE priority = 'Haute'"
        ).fetchone()[0]
    return {
        "total": total,
        "to_contact": to_contact,
        "contacted": contacted,
        "interviews": interviews,
        "refused": refused,
        "haute": haute,
    }


def apply_llm_scores(scores: list[dict]) -> int:
    """Applique les scores LLM (output du chat) sur les offres existantes.

    scores : liste de dicts avec offer_id, score_pipeline..., match_reasoning
    Retourne le nombre d'offres mises à jour.
    """
    from backend.models import label_for_score

    updated = 0
    sql = """
        UPDATE offers SET
            score_pipeline = :score_pipeline,
            score_exploration = :score_exploration,
            score_modelisation = :score_modelisation,
            score_deploiement = :score_deploiement,
            score_cadrage = :score_cadrage,
            match_score = :match_score,
            match_label = :match_label,
            match_reasoning = :match_reasoning,
            scored_at = CURRENT_TIMESTAMP
        WHERE id = :offer_id
    """
    with db() as conn:
        for s in scores:
            total = (
                s.get("score_pipeline", 0)
                + s.get("score_exploration", 0)
                + s.get("score_modelisation", 0)
                + s.get("score_deploiement", 0)
                + s.get("score_cadrage", 0)
            )
            params = {
                "offer_id": s["offer_id"],
                "score_pipeline": s.get("score_pipeline"),
                "score_exploration": s.get("score_exploration"),
                "score_modelisation": s.get("score_modelisation"),
                "score_deploiement": s.get("score_deploiement"),
                "score_cadrage": s.get("score_cadrage"),
                "match_score": total,
                "match_label": label_for_score(total),
                "match_reasoning": s.get("match_reasoning", ""),
            }
            cur = conn.execute(sql, params)
            updated += cur.rowcount
    return updated
