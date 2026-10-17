"""Indicateurs de charge d'entraînement.

Toutes les fonctions travaillent sur un DataFrame « long » :
une ligne par séance avec au minimum les colonnes
``joueuse``, ``date``, ``rpe`` (0-10) et ``duree_min``.

Références :
- sRPE : Foster et al. (2001), charge = RPE x durée.
- Monotonie et contrainte : Foster (1998).
- Ratio aigu / chronique en moyenne exponentielle (EWMA) : Williams et al. (2017).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def srpe(seances: pd.DataFrame) -> pd.DataFrame:
    """Ajoute la colonne ``charge`` = RPE x durée (minutes).

    Lève une erreur si une note RPE sort de l'échelle 0-10 ou si une durée est négative.
    """
    df = seances.copy()
    if not df["rpe"].between(0, 10).all():
        raise ValueError("RPE hors de l'échelle 0-10")
    if (df["duree_min"] < 0).any():
        raise ValueError("Durée négative")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["charge"] = df["rpe"] * df["duree_min"]
    return df


def charge_quotidienne(seances: pd.DataFrame, debut=None, fin=None) -> pd.DataFrame:
    """Charge totale par joueuse et par jour, jours sans séance à 0.

    Renvoie un tableau large : une ligne par jour, une colonne par joueuse.
    """
    df = srpe(seances) if "charge" not in seances else seances.assign(date=pd.to_datetime(seances["date"]).dt.normalize())
    large = df.pivot_table(index="date", columns="joueuse", values="charge", aggfunc="sum")
    debut = pd.to_datetime(debut) if debut is not None else large.index.min()
    fin = pd.to_datetime(fin) if fin is not None else large.index.max()
    jours = pd.date_range(debut, fin, freq="D", name="date")
    return large.reindex(jours).fillna(0.0)


def ratio_aigu_chronique(quotidien: pd.DataFrame, methode: str = "decouple",
                         aigu: int = 7, chronique: int = 28) -> pd.DataFrame:
    """Ratio aigu / chronique par joueuse et par jour.

    methode :
    - ``"decouple"`` (par défaut, celui affiché dans Vestiaire) : charge des 7 derniers
      jours divisée par la charge hebdomadaire moyenne des 28 jours qui précèdent.
      Exemple : 3 150 sur 7 jours contre 2 170 en moyenne = 1,45.
    - ``"couple"`` : moyenne sur 7 jours / moyenne sur 28 jours (les 7 derniers jours inclus).
    - ``"ewma"`` : moyennes exponentielles (Williams et al., 2017),
      lambda = 2 / (N + 1).

    Les premiers jours, tant que l'historique est insuffisant, valent NaN.
    """
    q = quotidien.astype(float)
    if methode == "decouple":
        a = q.rolling(aigu, min_periods=aigu).sum()
        c = q.shift(aigu).rolling(chronique, min_periods=chronique).sum() / (chronique / aigu)
    elif methode == "couple":
        a = q.rolling(aigu, min_periods=aigu).mean()
        c = q.rolling(chronique, min_periods=chronique).mean()
    elif methode == "ewma":
        a = q.ewm(alpha=2 / (aigu + 1), adjust=False).mean()
        c = q.ewm(alpha=2 / (chronique + 1), adjust=False).mean()
        # pas de ratio avant d'avoir un historique chronique complet
        nb = q.notna().cumsum()
        c = c.where(nb >= chronique)
    else:
        raise ValueError("methode doit valoir 'decouple', 'couple' ou 'ewma'")
    return a / c.replace(0, np.nan)


def monotonie(quotidien: pd.DataFrame, fenetre: int = 7) -> pd.DataFrame:
    """Monotonie de Foster : moyenne / écart-type de la charge quotidienne sur 7 jours.

    Une semaine où toutes les charges sont identiques (écart-type nul) donne NaN.
    """
    q = quotidien.astype(float)
    moy = q.rolling(fenetre, min_periods=fenetre).mean()
    et = q.rolling(fenetre, min_periods=fenetre).std(ddof=0)
    return moy / et.replace(0, np.nan)


def contrainte(quotidien: pd.DataFrame, fenetre: int = 7) -> pd.DataFrame:
    """Contrainte (strain) : charge de la semaine x monotonie."""
    hebdo = quotidien.astype(float).rolling(fenetre, min_periods=fenetre).sum()
    return hebdo * monotonie(quotidien, fenetre)


def resume_charge(quotidien: pd.DataFrame, jour=None) -> pd.DataFrame:
    """Tableau d'une ligne par joueuse pour un jour donné (par défaut le dernier).

    Colonnes : charge_7j, moyenne_hebdo_4sem, evolution_pct, ratio, monotonie, contrainte.
    """
    jour = pd.to_datetime(jour) if jour is not None else quotidien.index.max()
    q = quotidien.loc[:jour]
    charge_7j = q.tail(7).sum()
    moy_4sem = q.iloc[-35:-7].sum() / 4 if len(q) >= 35 else pd.Series(np.nan, index=q.columns)
    out = pd.DataFrame({
        "charge_7j": charge_7j,
        "moyenne_hebdo_4sem": moy_4sem,
        "evolution_pct": (charge_7j / moy_4sem - 1) * 100,
        "ratio": ratio_aigu_chronique(q).iloc[-1],
        "monotonie": monotonie(q).iloc[-1],
        "contrainte": contrainte(q).iloc[-1],
    })
    out.index.name = "joueuse"
    return out
