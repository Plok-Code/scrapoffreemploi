-- Migration 002 — CHECK constraints sur les colonnes enum + bornes scores
--
-- SQLite ne supporte pas `ALTER TABLE ADD CONSTRAINT` ; pour ajouter des
-- CHECK contraintes à une table existante, on recrée la table avec les
-- contraintes, on copie les données, on drop l'ancienne, on rename, on
-- recrée les index/triggers. Le tout dans une transaction.
--
-- Pré-requis : l'audit data du 14 mai 2026 a confirmé que TOUTES les
-- valeurs existantes respectent ces contraintes (`offers.status` ∈ {None,
-- Postulé, Refusé, Pas intéressé}, scores ∈ [0,20] ou [0,100], etc.).
-- Une éventuelle valeur invalide ferait échouer le `INSERT INTO ... SELECT`
-- et rollback proprement (cf rollback transactionnel du runner).
--
-- ⚠️ Les listes énumérées dans les CHECK doivent rester synchronisées avec
-- `backend/models.py` : VALID_STATUSES / VALID_PRIORITIES / VALID_REMOTE /
-- MATCH_LABELS / VALID_COMPANY_STATUSES. Si tu modifies l'un de ces
-- tuples, crée une nouvelle migration (003+).

-- ============================================================
-- Table offers : recréation avec CHECK
-- ============================================================

CREATE TABLE offers_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT NOT NULL,
    company TEXT,
    city TEXT,
    department TEXT,
    source TEXT,
    url TEXT,
    description TEXT,
    date_published TEXT,
    remote TEXT CHECK (
        remote IS NULL OR remote IN ('Oui', 'Non', 'Hybride')
    ),
    contract_type TEXT,
    salary TEXT,

    match_score INTEGER CHECK (
        match_score IS NULL OR (match_score >= 0 AND match_score <= 100)
    ),
    score_pipeline INTEGER CHECK (
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
    match_label TEXT CHECK (
        match_label IS NULL OR match_label IN ('Top', 'Bon', 'Moyen', 'Faible')
    ),
    match_reasoning TEXT,
    scored_at TEXT,

    status TEXT CHECK (
        status IS NULL OR status IN (
            'Postulé', 'Relancé', 'Entretien', 'Test technique',
            'Refusé', 'Accepté', 'Sans réponse', 'Abandonné', 'Pas intéressé'
        )
    ),
    application_method TEXT,
    date_applied TEXT,
    date_followup TEXT,
    date_interview TEXT,
    notes TEXT,
    priority TEXT CHECK (
        priority IS NULL OR priority IN ('Haute', 'Moyenne', 'Basse')
    ),

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    scraped_at TEXT,
    last_checked_at TEXT,
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),

    dedup_key TEXT
);

-- Copie des données : on nomme explicitement les colonnes pour ne pas dépendre
-- de l'ordre (défensif si l'ordre du CREATE TABLE diffère un jour).
INSERT INTO offers_new (
    id, title, company, city, department, source, url, description,
    date_published, remote, contract_type, salary,
    match_score, score_pipeline, score_exploration, score_modelisation,
    score_deploiement, score_cadrage, match_label, match_reasoning, scored_at,
    status, application_method, date_applied, date_followup, date_interview,
    notes, priority,
    created_at, updated_at, scraped_at, last_checked_at, is_active, dedup_key
)
SELECT
    id, title, company, city, department, source, url, description,
    date_published, remote, contract_type, salary,
    match_score, score_pipeline, score_exploration, score_modelisation,
    score_deploiement, score_cadrage, match_label, match_reasoning, scored_at,
    status, application_method, date_applied, date_followup, date_interview,
    notes, priority,
    created_at, updated_at, scraped_at, last_checked_at, is_active, dedup_key
FROM offers;

DROP TABLE offers;
ALTER TABLE offers_new RENAME TO offers;

-- Recréer les index et trigger (le DROP TABLE les a supprimés)
CREATE UNIQUE INDEX idx_offers_url ON offers(url) WHERE url IS NOT NULL AND url != '';
CREATE INDEX idx_offers_dedup_key ON offers(dedup_key);
CREATE INDEX idx_offers_match_score ON offers(match_score DESC);
CREATE INDEX idx_offers_status ON offers(status);
CREATE INDEX idx_offers_source ON offers(source);
CREATE INDEX idx_offers_date_published ON offers(date_published DESC);
CREATE INDEX idx_offers_is_active ON offers(is_active);

CREATE TRIGGER offers_updated_at
AFTER UPDATE ON offers
FOR EACH ROW
BEGIN
    UPDATE offers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- Table target_companies : recréation avec CHECK
-- ============================================================

CREATE TABLE target_companies_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sector TEXT,
    city TEXT,
    relevance TEXT,
    priority TEXT CHECK (
        priority IS NULL OR priority IN ('Haute', 'Moyenne', 'Basse')
    ),
    contact_channel TEXT,
    contact_name TEXT,
    notes TEXT,
    feedback TEXT,
    email TEXT,
    reliability TEXT,
    source_url TEXT,
    source TEXT,
    status TEXT CHECK (
        status IS NULL OR status IN (
            'Contacté', 'Relancé', 'Entretien', 'Refusé', 'Sans réponse', 'Abandonné'
        )
    ),
    date_contacted TEXT,
    date_followup TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO target_companies_new (
    id, name, sector, city, relevance, priority, contact_channel, contact_name,
    notes, feedback, email, reliability, source_url, source,
    status, date_contacted, date_followup, created_at, updated_at
)
SELECT
    id, name, sector, city, relevance, priority, contact_channel, contact_name,
    notes, feedback, email, reliability, source_url, source,
    status, date_contacted, date_followup, created_at, updated_at
FROM target_companies;

DROP TABLE target_companies;
ALTER TABLE target_companies_new RENAME TO target_companies;

-- Recréer les index et trigger
CREATE UNIQUE INDEX idx_target_companies_name_city
    ON target_companies(LOWER(name), LOWER(COALESCE(city, '')));
CREATE INDEX idx_target_companies_priority ON target_companies(priority);
CREATE INDEX idx_target_companies_status ON target_companies(status);
CREATE INDEX idx_target_companies_city ON target_companies(LOWER(city));

CREATE TRIGGER target_companies_updated_at
AFTER UPDATE ON target_companies
FOR EACH ROW
BEGIN
    UPDATE target_companies SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
