"""Statut du jour affiché sur l'écran « Effectif du jour » : alerte, à surveiller, sans données, dans sa norme.

Ce sont des repères pour aider le staff à décider, pas un diagnostic ni une
prédiction de blessure. Tous les seuils sont réglables par le club (écran Réglages).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Reperes:
    ratio_min: float = 0.8
    ratio_max: float = 1.3
    ecart_forme_points: float = 3.0
    hausse_charge_pct: float = 30.0


def _fr(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def _milliers(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u202f")


def statut_du_jour(charge: pd.DataFrame, forme: pd.DataFrame,
                   douleurs: pd.Series | None = None,
                   reperes: Reperes | None = None) -> pd.DataFrame:
    """Combine charge et forme en un statut et une explication en français.

    charge : sortie de ``resume_charge`` (index = joueuse).
    forme : une ligne par joueuse pour le jour, colonnes ``forme`` et ``moyenne_perso``
            (``forme`` manquante = état du jour pas encore reçu).
    douleurs : série booléenne par joueuse (douleur déclarée ce matin).
    """
    r = reperes or Reperes()
    douleurs = douleurs if douleurs is not None else pd.Series(dtype=bool)
    lignes = []
    for j in charge.index.union(forme.index):
        raisons, statut = [], "ok"
        c = charge.loc[j] if j in charge.index else None
        f = forme.loc[j] if j in forme.index else None
        if bool(douleurs.get(j, False)):
            statut = "alerte"
            raisons.append("Douleur déclarée ce matin")
        sans_seance = c is not None and c.get("charge_7j", np.nan) == 0
        if sans_seance:
            # Dans SoccerMon comme dans un tableur, 0 ne distingue pas le repos de l'oubli de saisie.
            raisons.append("Aucune séance déclarée sur 7 jours : absence, blessure ou oubli de saisie ?")
        elif c is not None and not np.isnan(c["ratio"]):
            ratio = round(float(c["ratio"]), 2)  # on compare la valeur affichée au staff
            detail = f"ratio {_fr(ratio)}"
            if not np.isnan(c.get("charge_7j", np.nan)):
                detail += f" ({_milliers(c['charge_7j'])} sur 7 jours)"
            if ratio > r.ratio_max:
                raisons.append(f"Charge en hausse : {detail}")
            elif ratio < r.ratio_min:
                mot = "Forte baisse de charge" if ratio < r.ratio_min / 1.6 else "Charge en baisse"
                raisons.append(f"{mot} : {detail}")
        if not sans_seance and c is not None and not np.isnan(c.get("evolution_pct", np.nan)) and c["evolution_pct"] >= r.hausse_charge_pct:
            raisons.append(f"Charge en hausse de {c['evolution_pct']:.0f} % sur ses 4 semaines précédentes")
        if f is not None:
            if pd.isna(f["forme"]):
                raisons.append("État du jour pas encore reçu")
            elif not pd.isna(f["moyenne_perso"]) and f["forme"] - f["moyenne_perso"] <= -r.ecart_forme_points:
                raisons.append(f"Forme à {f['forme']:.0f}/25 contre {f['moyenne_perso']:.0f} habituellement")
        if statut != "alerte" and any(not x.startswith(("État du jour", "Aucune séance")) for x in raisons):
            statut = "a_surveiller"
        elif statut == "ok" and sans_seance:
            statut = "sans_donnees"
        lignes.append({"joueuse": j, "statut": statut,
                       "pourquoi": " · ".join(raisons) if raisons else "—"})
    ordre = {"alerte": 0, "a_surveiller": 1, "sans_donnees": 2, "ok": 3}
    out = pd.DataFrame(lignes).set_index("joueuse")
    return out.sort_values("statut", key=lambda s: s.map(ordre), kind="stable")
