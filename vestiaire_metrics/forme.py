"""Score de forme du jour et comparaison à la moyenne personnelle de chaque joueuse.

Le questionnaire « Mon état du jour » de Vestiaire compte 5 questions notées de 1 à 5
(5 = meilleur) : fatigue, sommeil, courbatures, stress, humeur. Le score de forme est
leur somme, sur 25.

La comparaison se fait toujours à la joueuse elle-même, jamais à l'effectif :
une joueuse qui note toujours 17 n'est pas « en méforme » quand elle note 17.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

QUESTIONS = ["fatigue", "sommeil", "courbatures", "stress", "humeur"]


def score_forme(etats: pd.DataFrame) -> pd.DataFrame:
    """Ajoute ``forme`` (sur 25) à un DataFrame avec une ligne par joueuse et par jour.

    Une réponse manquante donne un score manquant : on ne devine pas une réponse.
    """
    df = etats.copy()
    manquantes = [q for q in QUESTIONS if q not in df]
    if manquantes:
        raise ValueError(f"Questions manquantes : {manquantes}")
    if not df[QUESTIONS].stack().between(1, 5).all():
        raise ValueError("Les réponses doivent être comprises entre 1 et 5")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["forme"] = df[QUESTIONS].sum(axis=1, min_count=len(QUESTIONS))
    return df


def reference_personnelle(etats: pd.DataFrame, fenetre_jours: int = 28,
                          min_reponses: int = 7) -> pd.DataFrame:
    """Moyenne et écart-type personnels de la forme sur les 28 jours précédents.

    Le jour même est exclu de sa propre référence. Sous 7 réponses, la référence
    n'est pas calculée (``NaN``) : l'écran affiche alors « référence en construction ».
    Ajoute les colonnes ``moyenne_perso``, ``ecart_points`` et ``z``.
    """
    df = score_forme(etats) if "forme" not in etats else etats.copy()
    df = df.sort_values(["joueuse", "date"])
    morceaux = []
    for joueuse, g in df.groupby("joueuse", sort=False):
        s = g.set_index("date")["forme"]
        passe = s.shift(1)
        fen = f"{fenetre_jours}D"
        moy = passe.rolling(fen, min_periods=min_reponses).mean()
        et = passe.rolling(fen, min_periods=min_reponses).std()
        g = g.assign(moyenne_perso=moy.values, ecart_type_perso=et.values)
        morceaux.append(g)
    out = pd.concat(morceaux)
    out["ecart_points"] = out["forme"] - out["moyenne_perso"]
    out["z"] = out["ecart_points"] / out["ecart_type_perso"].replace(0, np.nan)
    return out


def jours_sous_moyenne(etats_ref: pd.DataFrame, seuil_points: float = 3) -> pd.Series:
    """Nombre de jours consécutifs (jusqu'au dernier) où la forme est sous la moyenne
    personnelle d'au moins ``seuil_points``, par joueuse."""
    res = {}
    for joueuse, g in etats_ref.sort_values("date").groupby("joueuse"):
        bas = (g["ecart_points"] <= -seuil_points).to_numpy()
        n = 0
        for v in bas[::-1]:
            if not v:
                break
            n += 1
        res[joueuse] = n
    return pd.Series(res, name="jours_sous_moyenne")
