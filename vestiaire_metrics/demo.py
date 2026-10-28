"""Données fictives cohérentes avec le prototype Vestiaire (effectif Seniors F, 12 joueuses).

Aucune donnée réelle : les profils sont inventés pour montrer les indicateurs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .forme import QUESTIONS

EFFECTIF = {
    "Camille D.": "Défenseure", "Inès B.": "Milieu", "Sarah K.": "Attaquante",
    "Maëlys R.": "Latérale", "Léa M.": "Milieu", "Nina L.": "Défenseure",
    "Emma G.": "Milieu", "Chloé P.": "Attaquante", "Manon V.": "Attaquante",
    "Jade T.": "Gardienne", "Lina A.": "Défenseure", "Zoé F.": "Latérale",
}

# Semaine type : (jour de la semaine, durée en min, RPE moyen). Samedi = match.
SEMAINE_TYPE = {0: (60, 3), 1: (90, 7), 3: (75, 6), 4: (60, 3), 5: (95, 8)}


def generer(fin: str = "2026-10-13", nb_jours: int = 70, graine: int = 7):
    """Renvoie (seances, etats, douleurs) sur ``nb_jours`` jours jusqu'à ``fin``.

    Scénarios intégrés pour la démonstration :
    - Inès B. : retour de sélection, deux semaines chargées en fin de période ;
    - Camille D. : forme en baisse sur les 3 derniers jours et douleur déclarée ;
    - Sarah K. : forme sous sa moyenne (sommeil, stress) ;
    - Jade T., Lina A., Zoé F. : état du jour pas encore reçu le dernier jour.
    """
    rng = np.random.default_rng(graine)
    jours = pd.date_range(end=pd.Timestamp(fin), periods=nb_jours, freq="D")
    seances, etats = [], []
    for j, poste in EFFECTIF.items():
        base_forme = rng.integers(3, 5, size=len(QUESTIONS)).astype(float)
        for d in jours:
            reste = pd.Timestamp(fin) - d
            wd = d.day_of_week
            if wd in SEMAINE_TYPE:
                duree, rpe = SEMAINE_TYPE[wd]
                facteur = 1.0
                if j == "Inès B." and reste.days < 14 and wd != 5:
                    facteur = 1.45
                if poste == "Gardienne":
                    rpe = max(1, rpe - 2)
                rpe_j = float(np.clip(round(rng.normal(rpe, 0.8)), 1, 10))
                duree_j = float(round(duree * facteur * rng.uniform(0.9, 1.05)))
                if j == "Inès B." and reste.days < 14 and wd == 5:
                    seances.append({"joueuse": j, "date": d - pd.Timedelta(days=3), "rpe": 8.0, "duree_min": 90.0})
                seances.append({"joueuse": j, "date": d, "rpe": rpe_j, "duree_min": duree_j})
            # état du jour
            if reste.days == 0 and j in ("Jade T.", "Lina A.", "Zoé F."):
                continue
            rep = base_forme + rng.normal(0, 0.45, size=len(QUESTIONS))
            if j == "Camille D." and reste.days < 3:
                rep -= 1.5
            if j == "Sarah K." and reste.days < 2:
                rep[[1, 3]] -= 2
            rep = np.clip(np.round(rep), 1, 5)
            etats.append({"joueuse": j, "date": d, **dict(zip(QUESTIONS, rep))})
    douleurs = pd.Series({j: j == "Camille D." for j in EFFECTIF}, name="douleur")
    return pd.DataFrame(seances), pd.DataFrame(etats), douleurs
