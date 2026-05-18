-- ╔════════════════════════════════════════════════════════════════════════╗
-- ║  📚 RÉFÉRENCE DOCUMENTAIRE — pas appliqué directement par l'app        ║
-- ║                                                                        ║
-- ║  Le schéma vivant est désormais piloté par le runner de migrations     ║
-- ║  versionnées dans `backend/migrations/` (voir `backend/_migrations.py` ║
-- ║  et la table `schema_migrations`).                                     ║
-- ║                                                                        ║
-- ║  Ce fichier est conservé comme **vue synthétique** du schéma actuel    ║
-- ║  (état après toutes les migrations appliquées). Pratique pour lire le  ║
-- ║  schéma d'un coup d'œil sans empiler les migrations.                   ║
-- ║                                                                        ║
-- ║  ⚠️ MAINTENIR EN MIROIR : si tu modifies une migration ou en ajoutes   ║
-- ║  une nouvelle, mets ce fichier à jour. Le test                         ║
-- ║  `tests/test_schema_sql_in_sync.py` détecte le drift entre ce fichier  ║
-- ║  et les migrations effectivement appliquées.                           ║
-- ║                                                                        ║
-- ║  Pour faire évoluer le schéma : créer une nouvelle migration           ║
-- ║  `backend/migrations/{NNN}_<descripteur>.sql` (ALTER TABLE, etc.) et   ║
-- ║  mettre à jour ce fichier en miroir pour la lisibilité.                ║
-- ║                                                                        ║
-- ║  Voir aussi : .claude/rules/database.md                                ║
-- ╚════════════════════════════════════════════════════════════════════════╝

-- Schéma SQLite pour scrapoffreemploi (état après migrations 001 + 002).
-- Une seule table principale `offers` + `target_companies` + `scrape_runs`.

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
    remote TEXT CHECK (             -- migration 002 : enum
        remote IS NULL OR remote IN ('Oui', 'Non', 'Hybride')
    ),
    contract_type TEXT,             -- "Alternance" en général
    salary TEXT,

    -- Scoring LLM (rempli après passage au chat)
    match_score INTEGER CHECK (             -- migration 002 : borne /100
        match_score IS NULL OR (match_score >= 0 AND match_score <= 100)
    ),
    score_pipeline INTEGER CHECK (          -- migration 002 : borne /20
        score_pipeline IS NULL OR (score_pipeline >= 0 AND score_pipeline <= 20)
    ),
    score_exploration INTEGER CHECK (
        score_exploration IS NULL OR (score_exploration >= 0 AND score_exploration <= 20)
    ),
    score_modelisation INTEGER CHECK (
        score_modelisation IS NULL OR (score_modelisation >= 0 AND score_modelisation <= 20)
    ),
    score_deploiement INTEGER CHECK (
        score_deploiement IS NULL OR (score_deploiement >= 0 AND score_deploiement <= 20)
    ),
    score_cadrage INTEGER CHECK (
        score_cadrage IS NULL OR (score_cadrage >= 0 AND score_cadrage <= 20)
    ),
    match_label TEXT CHECK (                -- migration 002 : enum
        match_label IS NULL OR match_label IN ('Top', 'Bon', 'Moyen', 'Faible')
    ),
    match_reasoning TEXT,               -- justification écrite du LLM
    scored_at TEXT,

    -- Tracking utilisateur (manuel via UI)
    status TEXT CHECK (                     -- migration 002 : enum VALID_STATUSES
        status IS NULL OR status IN (
            'Postulé', 'Relancé', 'Entretien', 'Test technique',
            'Refusé', 'Accepté', 'Sans réponse', 'Abandonné', 'Pas intéressé'
        )
    ),
    application_method TEXT,            -- "Portail officiel recommandé", "Email RH", etc.
    date_applied TEXT,
    date_followup TEXT,
    date_interview TEXT,
    notes TEXT,
    priority TEXT CHECK (                   -- migration 002 : enum VALID_PRIORITIES
        priority IS NULL OR priority IN ('Haute', 'Moyenne', 'Basse')
    ),

    -- Méta
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    scraped_at TEXT,
    last_checked_at TEXT,               -- dernier check HTTP de l'URL
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),  -- migration 002

    -- Clé de dédoublonnage (titre + entreprise + ville normalisés)
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
    city TEXT,                       -- "Toulouse", "Paris", "Lyon"... (nullable, ville principale)
    relevance TEXT,                  -- "Pourquoi pertinent (AI Engineer)"
    priority TEXT CHECK (            -- migration 002 : enum VALID_PRIORITIES
        priority IS NULL OR priority IN ('Haute', 'Moyenne', 'Basse')
    ),
    contact_channel TEXT,            -- "Portail Airbus Careers / Workday..."
    contact_name TEXT,               -- "Talent Acquisition / Early Careers..."
    notes TEXT,
    feedback TEXT,                   -- "Retour / notes perso"
    email TEXT,                      -- "Pas de mail RH fiable" ou un email
    reliability TEXT,                -- "Portail officiel indispensable"
    source_url TEXT,                 -- URL portail
    source TEXT,                     -- "xlsx historique", "La Bonne Boite", "manual"
    -- Tracking applicatif (≠ VALID_STATUSES des offres — pas de 'Postulé')
    status TEXT CHECK (              -- migration 002 : enum VALID_COMPANY_STATUSES
        status IS NULL OR status IN (
            'Contacté', 'Relancé', 'Entretien', 'Refusé', 'Sans réponse', 'Abandonné'
        )
    ),
    date_contacted TEXT,
    date_followup TEXT,
    -- Méta
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Index UNIQUE sur (name, city) : permet une row par (entreprise, ville).
-- Ex : Capgemini Paris + Capgemini Toulouse = 2 rows (2 candidatures distinctes).
CREATE UNIQUE INDEX IF NOT EXISTS idx_target_companies_name_city
    ON target_companies(LOWER(name), LOWER(COALESCE(city, '')));
CREATE INDEX IF NOT EXISTS idx_target_companies_priority ON target_companies(priority);
CREATE INDEX IF NOT EXISTS idx_target_companies_status ON target_companies(status);
CREATE INDEX IF NOT EXISTS idx_target_companies_city ON target_companies(LOWER(city));

CREATE TRIGGER IF NOT EXISTS target_companies_updated_at
AFTER UPDATE ON target_companies
FOR EACH ROW
BEGIN
    UPDATE target_companies SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Historique des runs de scraping (pour audit, y compris les échecs)
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    sources TEXT,                       -- CSV des sources scrapées
    total_fetched INTEGER DEFAULT 0,
    total_new INTEGER DEFAULT 0,
    total_duplicates INTEGER DEFAULT 0,
    batch_file TEXT,                    -- chemin du fichier batch JSON généré
    error TEXT                          -- message d'erreur si le scrape a échoué
);
