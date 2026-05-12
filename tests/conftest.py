"""Configuration globale pytest.

- Init du logging en quiet (pas de spam dans la sortie test)
- Fixtures réutilisables (DB temp, etc.)
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _init_logging():
    """Initialise le logger en mode silencieux pour les tests."""
    from backend._logging import init_logging
    init_logging(level="WARNING", quiet_console=True)


@pytest.fixture
def html_workday_dead():
    """HTML simulant une page Workday avec offre supprimée."""
    return """<!DOCTYPE html>
    <html>
        <head><title>Careers | Renault Group</title></head>
        <body>
            <h1>La page que vous recherchez n'existe pas.</h1>
        </body>
    </html>"""


@pytest.fixture
def html_axa_redirect():
    """HTML simulant la home AXA recrutement (redirige après 404)."""
    return """<!DOCTYPE html>
    <html><head><title>Recrutement AXA en France. Nos offres d&#x27;emploi</title></head>
    <body>
        <h2>Votre recherche</h2>
        <p>663 offres correspondent à votre recherche</p>
        <p>Affinez votre recherche</p>
    </body></html>"""


@pytest.fixture
def html_alive_offer():
    """HTML simulant une vraie offre vivante (description + alternance)."""
    return """<!DOCTYPE html>
    <html><head><title>Alternance ML Engineer F/H | Doctolib</title></head>
    <body>
        <main>
            <h1>Alternance Machine Learning Engineer</h1>
            <p>Rejoignez Doctolib en alternance pour développer des modèles de machine learning
               appliqués à la santé. Python, PyTorch, MLflow.</p>
        </main>
    </body></html>"""
