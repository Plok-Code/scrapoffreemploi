"""Remplit le champ `contact_channel` pour chaque entreprise Toulouse avec
la méthode optimale en fonction du profil (taille, secteur, formalisme RH).

Logique par profil :
- Grands groupes RH rigides (Airbus, Sanofi, Dassault, IBM, Renault, SNCF, Stellantis) :
    portail obligatoire + Talent Community / job alerts
- ESN volume (Capgemini, Sopra Steria, CGI, Atos, Onepoint, Smile) :
    portail + LinkedIn recruteur Toulouse pour relance
- BUs Thales / spatial / défense :
    portail Thales Careers filtré site + LinkedIn Talent Acquisition Toulouse
- Recherche / institutions (ANITI, IRT, ONERA, Inserm) :
    email direct chercheur/équipe + portail
- Startups / scale-ups (Donecle, UnaBiz, TellMePlus) :
    LinkedIn direct fondateur/CTO + portail Taleez/Workable si présent
- Cabinets de recrutement (Externatic, Itekway, Silkhom, NEXTGEN RH) :
    inscription portail + LinkedIn recruteur (ce sont des intermédiaires, pas des employeurs finaux)
- PME locales sans branding RH (NBTECH, SOPHIA Engineering, N Support, REEV) :
    email direct + LinkedIn fondateur/manager
"""
from __future__ import annotations

from backend.db import db


# Mapping company_id → contact_channel optimisé (Toulouse-specific)
# Note : on utilise les IDs qui sont stables (cf. requête SELECT précédente)
TOULOUSE_CONTACT_METHODS: dict[int, str] = {
    # ===== HAUTE PRIORITÉ =====
    1: (  # Airbus
        "Portail Airbus Careers (Workday) — filtrer 'site Toulouse' + 'apprenticeship'. "
        "Crée un compte Talent Community pour recevoir les alertes en avance. "
        "Email RH inutile (volume énorme, traité par bots). Bonus : forum Airbus à Toulouse Business School."
    ),
    2: (  # Thales Alenia Space
        "Portail careers.thalesgroup.com → filtre 'Thales Alenia Space' + 'Toulouse' + 'apprentissage'. "
        "Doublon avec LinkedIn : cible un Talent Acquisition Toulouse spécifique + un manager d'équipe data/IA."
    ),
    3: (  # Aumovio (ex Continental)
        "Aumovio Job Portal (SmartRecruiters) + LinkedIn Recruiter Toulouse. "
        "Équipe RH locale petite, ils répondent aux relances LinkedIn dans la semaine."
    ),
    8: (  # IBM Toulouse
        "IBM Careers + Talent Network alertes. "
        "Process rigide, ne pas tenter mail direct. Astuce : suivre la page LinkedIn 'IBM Toulouse' "
        "pour voir quand un recruteur poste, et postuler dans les 24h."
    ),
    9: (  # Pierre Fabre
        "Portail Pierre Fabre 'Carrières' rubrique Alternance/Work-study. "
        "Forum recrutement annuel à Castres (mi-juin). LinkedIn pour cibler RH Castres/Toulouse Sud."
    ),
    10: (  # IRT Saint Exupery
        "Taleez IRT Saint Exupéry + email direct au responsable du projet IA visé "
        "(les projets sont nommés sur leur site : Cosmoloc, OFELIA, etc.). "
        "Ne PAS envoyer de CV générique : adapter au projet sinon ignoré."
    ),
    11: (  # ANITI
        "Email aniti-stage@univ-toulouse.fr ET cibler un chercheur/chaire précis sur le site "
        "(45 chaires : NLP, optimisation, fairness…) + LinkedIn direct au PI. "
        "C'est une chaire universitaire, le mail générique ne suffit pas — il faut un projet précis."
    ),
    15: (  # Donecle
        "LinkedIn direct CTO + équipe ingénierie (boîte ~50 personnes, accessible). "
        "Plus efficace que Taleez générique. WTTJ aussi : page Donecle active."
    ),
    24: (  # Thales DMS / Thales LAS
        "Portail careers.thalesgroup.com → filtre 'DMS' ou 'LAS' + 'Toulouse'. "
        "Pour défense : nationalité française quasi-obligatoire. Sinon LinkedIn Talent Acquisition Thales Defense."
    ),
    219: (  # Dassault Aviation
        "Email emploi@dassault-aviation.com avec CV + lettre ciblée 'Toulouse (St-Martin) + IA/data'. "
        "Entreprise traditionnelle qui répond aux mails. "
        "Portail dassault-aviation.com en complément. Habilitation défense souvent requise."
    ),
    222: (  # Capgemini Engineering Toulouse
        "Portail Capgemini Careers + LinkedIn 'Talent Acquisition Capgemini Engineering Toulouse' (2-3 recruteurs identifiés). "
        "Volume énorme d'alternance, portail efficace. Relance LinkedIn après 1 semaine."
    ),
    243: (  # Renault Software Factory
        "Portail Renault Group Careers + LinkedIn 'Renault Software Factory Toulouse'. "
        "Équipe récente et accessible, les managers répondent aux messages directs LinkedIn."
    ),
    245: (  # Sanofi Toulouse
        "Sanofi Careers Workday + LinkedIn 'Talent Acquisition Sanofi France'. "
        "Process rigide groupe pharma, portail obligatoire."
    ),
    215: (  # Atos / Eviden Toulouse
        "Portail Atos/Eviden + activer alertes Toulouse. "
        "Énorme volume alternance, portail seul suffit. Relance par LinkedIn recruteur Toulouse si pas de réponse 2 semaines."
    ),

    # ===== MOYENNE PRIORITÉ =====
    235: (  # Capgemini (groupe, ≠ Capgemini Engineering)
        "Portail Capgemini Careers (capgemini.com/fr-fr/carrieres). "
        "Cibler les pôles conseil / banque / industrie selon préférence. Process aligné Engineering."
    ),
    209: (  # CGI
        "Portail CGI Recrute (Njoyn) + LinkedIn recruteur CGI Toulouse. "
        "Process rigide, le portail est la voie officielle. Évite les mails directs."
    ),
    14: (  # Daher
        "Portail Daher (Workday) — filtrer 'Toulouse-Blagnac'. "
        "Entreprise familiale, taille moyenne : portail + relance LinkedIn manager d'équipe."
    ),
    231: (  # Davidson Consulting
        "Formulaire candidature spontanée Davidson (davidson.fr/candidature-spontanee/) + "
        "LinkedIn manager Davidson Toulouse. Conseil = relation directe avec manager prime."
    ),
    74: (  # DISTRIBUTION SERVICES INDUSTRIELS — sortir du scope (pas IA)
        "Profil non-IA détecté (distribution industrielle classique). "
        "Désactiver de la cible. Sinon : email direct site web + LinkedIn."
    ),
    68: (  # Electricite de France (EDF)
        "Portail EDF Recrute (rubrique alternance) + LinkedIn 'EDF Sud-Ouest Toulouse'. "
        "Groupe public process formel. Hors-Saclay, peu d'IA pure à Toulouse."
    ),
    75: (  # Externatic (cabinet de recrutement)
        "Cabinet recrutement spécialisé tech. Inscription portail Externatic + "
        "LinkedIn 'Externatic Toulouse'. Ils placent chez leurs clients, donc ils répondent vite."
    ),
    76: (  # Inserm
        "Email direct au directeur de l'unité Inserm Toulouse ciblée (CRCT, Restore, etc.) + "
        "Portail Inserm jobs. Recherche = cibler un labo précis, jamais générique."
    ),
    72: (  # ITEKWAY (cabinet recrutement)
        "Cabinet de recrutement. Inscription site itekway.com + LinkedIn 'ITEKWAY Toulouse'. "
        "Toujours répondent aux candidats — c'est leur métier."
    ),
    12: (  # Latécoère
        "Portail Latécoère Carrières + LinkedIn Talent Acquisition Latécoère. "
        "ETI taille moyenne, recruteurs accessibles."
    ),
    13: (  # Liebherr Aerospace
        "Portail Liebherr Toulouse + formulaire de contact recruteur intégré. "
        "Process formel multinational allemand. Pas d'email direct."
    ),
    77: (  # N SUPPORT (petite ESN/SSII)
        "PME : LinkedIn direct fondateur/dirigeant + email site web. "
        "Pas de RH structurée — approche directe."
    ),
    73: (  # NBTECH TOULOUSE
        "Petite ESN locale Toulouse. LinkedIn direct + email RH du site web. "
        "Réactif au candidate direct. Vérifier site web pour adresse précise."
    ),
    207: (  # Onepoint Toulouse
        "Onepoint Workday (groupeonepoint.com) + LinkedIn 'Manager équipe Data Toulouse'. "
        "Cabinet haut de gamme : la relation manager directe est clé. Pré-qualif via Welcome to the Jungle."
    ),
    67: (  # ONERA Toulouse
        "Portail ONERA Carrières (rubrique alternance) + email direct à l'équipe IA/computer vision Toulouse "
        "(département DTIS). Centre recherche public, cibler un projet précis."
    ),
    71: (  # REEV SAS
        "Petite société. LinkedIn fondateur + email site web. Approche directe."
    ),
    78: (  # SILKHOM SAS (cabinet recrutement IT)
        "Cabinet de recrutement IT. Inscription site silkhom.com + LinkedIn. "
        "Cibler un consultant Toulouse spécifiquement (data/IA)."
    ),
    227: (  # Smile (Open Source IT)
        "Portail Smile Jobs (jobs.smile.eu) + LinkedIn Talent Smile Toulouse. "
        "ESN tech open-source, accessible et process standard."
    ),
    230: (  # SNCF Réseau Sud-Ouest
        "Portail SNCF Recrute (emploi.sncf.com) + Forum SNCF alternance (juin annuel Toulouse). "
        "Groupe public process rigide. Forums étudiants = canal alternatif efficace."
    ),
    79: (  # SOPHIA ENGINEERING
        "PME ingénierie. LinkedIn direct manager Toulouse + email site web. "
        "Vérifier sur leur site la BU IA/data exacte."
    ),
    201: (  # Sopra Steria Toulouse
        "Portail Sopra Steria Careers (careers.soprasteria.fr) + LinkedIn 'Talent Acquisition Sopra Steria Sud-Ouest'. "
        "Volume alternance important, portail efficace + LinkedIn pour suivi."
    ),
    70: (  # SUEZ Toulouse
        "Portail SUEZ Carrières + LinkedIn 'recruteur SUEZ Sud-Ouest'. "
        "Groupe énergie/eau, taille moyenne process formel."
    ),
    18: (  # TellMePlus
        "Startup IA prédictive — vérifier d'abord l'activité (site lent, peut-être en sommeil). "
        "Si actif : Station F Jobs + LinkedIn fondateur. Si inactif : skip."
    ),
    66: (  # Thales (entrée agrégée Toulouse, ≠ BUs)
        "Doublon agrégé. Voir Thales Alenia Space [2] ou Thales DMS/LAS [24] pour la BU précise. "
        "À fusionner manuellement si besoin."
    ),
    17: (  # UnaBiz (ex-Sigfox)
        "UnaBiz Careers + LinkedIn direct fondateur Henri Bong/Alexis Susset. "
        "Scale-up IoT/data, équipe Toulouse réduite : approche directe LinkedIn payante."
    ),
    69: (  # VINCI Energies en France
        "Portail VINCI Energies + LinkedIn 'recruteur VINCI Energies Sud-Ouest'. "
        "Cibler une BU précise (Actemium, Axians selon focus IA/data)."
    ),
}


def apply_toulouse_contact_methods() -> dict:
    """Applique les méthodes de contact optimisées sur les entreprises Toulouse."""
    updated = 0
    not_found = 0
    with db() as conn:
        for company_id, channel in TOULOUSE_CONTACT_METHODS.items():
            existing = conn.execute(
                "SELECT 1 FROM target_companies WHERE id = ?", (company_id,)
            ).fetchone()
            if not existing:
                not_found += 1
                continue
            conn.execute(
                "UPDATE target_companies SET contact_channel = :ch WHERE id = :id",
                {"ch": channel, "id": company_id},
            )
            updated += 1
    return {"updated": updated, "not_found": not_found, "total_mapping": len(TOULOUSE_CONTACT_METHODS)}


if __name__ == "__main__":
    result = apply_toulouse_contact_methods()
    print(f"Méthodes de contact Toulouse appliquées : {result}")
