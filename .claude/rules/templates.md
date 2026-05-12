---
description: Jinja templates + HTMX + Tailwind via CDN
paths:
  - backend/templates/**
  - backend/static/**
---

# Templates Jinja + HTMX + Tailwind CDN

## Stack frontend

- **Jinja2** : moteur de templates, livré par FastAPI
- **HTMX 2.0** via CDN (`<script src="https://unpkg.com/htmx.org@2.0.4">`)
- **Tailwind v3** via CDN (`<script src="https://cdn.tailwindcss.com">`)
- **CSS custom** : `backend/static/style.css` (minimal, juste fallback font)
- **Pas de JS custom**, pas de build step, pas de bundler

## Hiérarchie

- `templates/base.html` : layout commun (navbar, head, scripts CDN)
- `templates/offers.html` : page liste, étend `base.html`
- `templates/offer_detail.html` : page détail + form, étend `base.html`

## Pattern : étendre base.html

```jinja
{% extends "base.html" %}
{% block title %}Mon titre — Scrap'Offre Emploi{% endblock %}

{% block content %}
    <!-- contenu spécifique ici -->
{% endblock %}
```

## Pattern : macros pour les composants répétés

Définir en haut du fichier :
```jinja
{% macro score_badge(score) -%}
    {% if score is none %}
        <span class="inline-block px-2 py-0.5 text-xs rounded bg-slate-200 text-slate-600">—</span>
    {% elif score >= 80 %}
        <span class="inline-block px-2 py-0.5 text-xs rounded bg-emerald-100 text-emerald-800 font-medium">{{ score }}</span>
    ...
{%- endmacro %}
```

## Tailwind : palette de couleurs (cohérence)

Utiliser SEULEMENT ces couleurs sémantiques :
- **Slate** (gris) : neutre, texte, backgrounds
- **Emerald** : Top fit / Accepté / succès
- **Yellow** : Bon fit / Relancé / warning
- **Orange** : Moyen fit
- **Rose** : Refusé / erreur critique
- **Blue** : Postulé / liens
- **Purple** : Entretien / Test technique
- **Amber** : Relancé

Bg/text doublé : `bg-emerald-100 text-emerald-800`, `bg-rose-100 text-rose-800`, etc.

## HTMX patterns (à utiliser à venir)

Pour update inline sans reload :
```html
<select name="status"
        hx-patch="/api/offers/{{ offer.id }}"
        hx-trigger="change"
        hx-swap="none">
    ...
</select>
```

Pour confirmation avant action destructive :
```html
<button hx-post="/api/offers/{{ offer.id }}/delete"
        hx-confirm="Supprimer cette offre ?">
    Supprimer
</button>
```

## Toujours

- ✅ Étendre `base.html` (pas de doc HTML complète dans une autre page)
- ✅ Pour le HTML, utiliser des labels accessibles (`<label>`, `aria-*`)
- ✅ Utiliser HTMX pour les interactions dynamiques, pas de JS custom
- ✅ Indentation 4 espaces
- ✅ Tailwind sur une ligne si raisonnable, sinon par groupes logiques

## Jamais

- ❌ Inline `<style>` ou `<script>` custom (sauf cas force majeure)
- ❌ Charger React, Vue, Alpine, jQuery, ou un autre framework JS
- ❌ Tailwind config file (on est en CDN)
- ❌ Build CSS (`postcss`, `lightningcss`, etc.)
- ❌ Embarquer des classes dynamiques type `bg-{{ color }}-100` (Tailwind purge ne marche pas avec ça, mais en CDN c'est moins critique — préfère un if/elif clair)

## Accessibilité minimale

- `lang="fr"` sur `<html>`
- `<label>` lié à chaque `<input>` (via `for=...` ou wrapping)
- Boutons avec `type="button"` ou `type="submit"` explicite
- Contrast color OK (les couleurs Tailwind ci-dessus le sont par défaut)
