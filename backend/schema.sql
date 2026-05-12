-- Schéma SQLite pour scrapoffreemploi
-- Une seule table principale `offers` + une table `scrape_runs` pour l'historique

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Données de l'offre (immutables après scraping)
    title TEXT NOT NULL,
    company TEXT,
    city TEXT,
    department TEXT,
    source TEXT,                    -- "Hellowork", "Apec", "LinkedIn", etc.
    url TEXT,
    description TEXT,               -- description complète si récupérée
    date_published TEXT,            -- ISO date (YYYY-MM-DD) ou null
    remote TEXT,                    -- "Oui", "Non", "Hybride", null
    contract_type TEXT,             -- "Alternance" en général
    salary TEXT,

    -- Scoring LLM (rempli après passage au chat)
    match_score INTEGER,                -- 0-100 (somme des 5 axes)
    score_pipeline INTEGER,             -- /20  Ingestion / pipeline data
    score_exploration INTEGER,          -- /20  Exploration / analyse
    score_modelisation INTEGER,         -- /20  Modélisation IA
    score_deploiement INTEGER,          -- /20  Déploiement / MLOps
    score_cadrage INTEGER,              -- /20  Cadrage / qualité / indus
    match_label TEXT,                   -- "Top", "Bon", "Moyen", "Faible"
    match_reasoning TEXT,               -- justification écrite du LLM
    scored_at TEXT,

    -- Tracking utilisateur (manuel via UI)
    status TEXT,                        -- null = pas postulé, sinon "Postulé"/"Refusé"/"Entretien"/etc.
    application_method TEXT,            -- "Portail officiel recommandé", "Email RH", etc.
    date_applied TEXT,
    date_followup TEXT,
    date_interview TEXT,
    notes TEXT,
    priority TEXT,                      -- "Haute", "Moyenne", "Basse"

    -- Méta
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    scraped_at TEXT,
    last_checked_at TEXT,               -- dernier check HTTP de l'URL
    is_active INTEGER DEFAULT 1,        -- 1 = URL toujours valide, 0 = 404/410/archived

    -- Clé de dédoublonnage (titre + entreprise normalisés) pour fallback URL manquante
    dedup_key TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_offers_url ON offers(url) WHERE url IS NOT NULL AND url != '';
CREATE INDEX IF NOT EXISTS idx_offers_dedup_key ON offers(dedup_key);
CREATE INDEX IF NOT EXISTS idx_offers_match_score ON offers(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);
CREATE INDEX IF NOT EXISTS idx_offers_source ON offers(source);
CREATE INDEX IF NOT EXISTS idx_offers_date_published ON offers(date_published DESC);
CREATE INDEX IF NOT EXISTS idx_offers_is_active ON offers(is_active);

-- Trigger pour updated_at
CREATE TRIGGER IF NOT EXISTS offers_updated_at
AFTER UPDATE ON offers
FOR EACH ROW
BEGIN
    UPDATE offers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Entreprises cibles "candidature spontanée" (phase 2)
-- Importées initialement depuis data/companies_spontaneous_extracted.json
CREATE TABLE IF NOT EXISTS target_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sector TEXT,
    relevance TEXT,                  -- "Pourquoi pertinent (AI Engineer)"
    priority TEXT,                   -- "Haute", "Moyenne", "Basse"
    contact_channel TEXT,            -- "Portail Airbus Careers / Workday..."
    contact_name TEXT,               -- "Talent Acquisition / Early Careers..."
    notes TEXT,
    feedback TEXT,                   -- "Retour / notes perso"
    email TEXT,                      -- "Pas de mail RH fiable" ou un email
    reliability TEXT,                -- "Portail officiel indispensable"
    source_url TEXT,                 -- URL portail
    -- Tracking applicatif
    status TEXT,                     -- "Contacté", "Relancé", "Refusé", "Entretien", etc.
    date_contacted TEXT,
    date_followup TEXT,
    -- Méta
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_target_companies_name ON target_companies(LOWER(name));
CREATE INDEX IF NOT EXISTS idx_target_companies_priority ON target_companies(priority);
CREATE INDEX IF NOT EXISTS idx_target_companies_status ON target_companies(status);

CREATE TRIGGER IF NOT EXISTS target_companies_updated_at
AFTER UPDATE ON target_companies
FOR EACH ROW
BEGIN
    UPDATE target_companies SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Historique des runs de scraping (pour audit)
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    sources TEXT,                       -- CSV des sources scrapées
    total_fetched INTEGER DEFAULT 0,
    total_new INTEGER DEFAULT 0,
    total_duplicates INTEGER DEFAULT 0,
    batch_file TEXT,                    -- chemin du fichier batch JSON généré
    error TEXT
);
