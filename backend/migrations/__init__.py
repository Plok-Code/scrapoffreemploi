"""Migrations versionnées du schéma SQLite.

Chaque fichier `{NNN}_{descripteur}.sql` est une migration appliquée une fois
en transaction, puis enregistrée dans la table `schema_migrations` pour ne
pas être ré-appliquée. Voir `backend/_migrations.py` pour le runner.

Convention :
- Numérotation 3 chiffres (001, 002, ...).
- Nom descriptif : `001_initial.sql`, `002_add_offers_views.sql`, etc.
- Les migrations DOIVENT être idempotentes ou DOIVENT supposer que la
  migration précédente est appliquée. En pratique on utilise
  `CREATE TABLE IF NOT EXISTS` pour les créations et de simples `ALTER`
  pour les ajouts (la table `schema_migrations` empêche déjà la
  ré-application).
- **NE JAMAIS** modifier une migration déjà publiée : elles sont
  historiquement immuables. Pour changer le schéma, créer une NOUVELLE
  migration.
"""
