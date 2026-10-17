"""Lecture de fichiers GPS dont on ne connaît pas le format à l'avance (SoccerMon ou autre).

Le module devine les colonnes utiles (temps, vitesse, joueuse) d'après leur nom, l'unité de
vitesse (m/s ou km/h) d'après les valeurs, et la fréquence d'échantillonnage d'après le temps.
Chaque choix est noté dans le résultat, pour pouvoir le vérifier.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .zones import FEMININS, MASCULINS, Seuils, resume_gps

EXTENSIONS = {".csv", ".parquet", ".txt"}
NOMS_VITESSE = ["speed", "velocity", "vitesse", "speed_kmh", "speed (km/h)", "speed_ms", "v"]
NOMS_TEMPS = ["time", "timestamp", "datetime", "date_time", "utc", "ts", "temps"]
NOMS_JOUEUSE = ["player_name", "player", "player_id", "athlete", "athlete_id", "name", "joueuse"]
VITESSE_MAX_PLAUSIBLE_KMH = 38.0


def lister_fichiers(dossier: str | Path) -> list[Path]:
    return sorted(p for p in Path(dossier).rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)


def lire(chemin: Path, nrows: int | None = None) -> pd.DataFrame:
    if chemin.suffix.lower() == ".parquet":
        df = pd.read_parquet(chemin)
        return df.head(nrows) if nrows else df
    return pd.read_csv(chemin, nrows=nrows, sep=None, engine="python") if nrows else pd.read_csv(chemin, sep=None, engine="python")


def _trouver(colonnes, candidats, contient=None):
    bas = {c.lower().strip(): c for c in colonnes}
    for n in candidats:
        if n in bas:
            return bas[n]
    if contient:
        for c in colonnes:
            if any(m in c.lower() for m in contient):
                return c
    return None


def detecter_colonnes(df: pd.DataFrame) -> dict:
    """Devine les colonnes temps, vitesse et joueuse. Renvoie un dict (valeur None si absente)."""
    cols = list(df.columns)
    return {
        "vitesse": _trouver(cols, NOMS_VITESSE, contient=["speed", "veloc", "vitesse"]),
        "temps": _trouver(cols, NOMS_TEMPS, contient=["time", "date"]),
        "joueuse": _trouver(cols, NOMS_JOUEUSE, contient=["player", "athlete"]),
    }


def vitesse_en_kmh(v: pd.Series) -> tuple[pd.Series, str]:
    """Convertit en km/h si les valeurs ressemblent à des m/s (99e centile sous 12)."""
    v = pd.to_numeric(v, errors="coerce")
    p99 = np.nanpercentile(v, 99) if v.notna().any() else np.nan
    if p99 < 12:
        return v * 3.6, "m/s (converti en km/h)"
    return v, "km/h"


def _temps_en_datetime(temps: pd.Series) -> pd.Series | None:
    """Temps en dates si la colonne contient des dates (texte), sinon None."""
    if pd.api.types.is_numeric_dtype(temps):
        return None
    t = pd.to_datetime(temps, errors="coerce", utc=True, format="mixed")
    return t if t.notna().mean() > 0.9 else None


def frequence_hz(temps: pd.Series | None, defaut: float = 10.0) -> tuple[float, str]:
    """Fréquence d'échantillonnage déduite de la colonne de temps (dates, secondes ou millisecondes)."""
    if temps is None:
        return defaut, f"inconnue, {defaut:g} Hz supposés"
    t = _temps_en_datetime(temps)
    if t is not None:
        dt = t.diff().dt.total_seconds().median()
        source = "déduite du temps (dates)"
    else:
        num = pd.to_numeric(temps, errors="coerce")
        dt = num.diff().median()
        source = "déduite du temps (nombres)"
        if pd.notna(dt) and dt > 5:  # millisecondes
            dt, source = dt / 1000, "déduite du temps (millisecondes)"
    if pd.isna(dt) or dt <= 0:
        return defaut, f"inconnue, {defaut:g} Hz supposés"
    return round(1 / dt, 1), source


def analyser_fichier(chemin: Path, seuils_list: dict[str, Seuils] | None = None) -> tuple[list[dict], dict]:
    """Résume chaque trace (une par joueuse si une colonne joueuse existe) d'un fichier.

    Renvoie (lignes de résultats, informations de détection).
    """
    seuils_list = seuils_list or {"feminins": FEMININS, "masculins": MASCULINS}
    df = lire(chemin)
    det = detecter_colonnes(df)
    info = {"fichier": str(chemin), "lignes": len(df), **{f"colonne_{k}": v for k, v in det.items()}}
    if det["vitesse"] is None:
        info["probleme"] = "aucune colonne de vitesse reconnue"
        return [], info
    groupes = df.groupby(det["joueuse"]) if det["joueuse"] else [(chemin.stem, df)]
    lignes = []
    for joueuse, g in groupes:
        if det["temps"]:
            g = g.sort_values(det["temps"])
        v, unite = vitesse_en_kmh(g[det["vitesse"]])
        aberrantes = int((v > VITESSE_MAX_PLAUSIBLE_KMH).sum())
        v = v.mask(v > VITESSE_MAX_PLAUSIBLE_KMH).interpolate(limit=5).fillna(0).clip(lower=0)
        hz, source_hz = frequence_hz(g[det["temps"]] if det["temps"] else None)
        info.update({"unite_vitesse": unite, "frequence_hz": hz, "source_frequence": source_hz})
        duree_min = len(v) / hz / 60
        if duree_min < 10:  # trace trop courte pour être une séance
            continue
        ligne = {"fichier": chemin.name, "joueuse": str(joueuse), "duree_min": round(duree_min, 1),
                 "points_aberrants_retires": aberrantes}
        t = _temps_en_datetime(g[det["temps"]]) if det["temps"] else None
        ligne["date"] = t.min().date().isoformat() if t is not None else None
        trace = pd.DataFrame({"vitesse_kmh": v.rolling(int(max(1, hz // 2)), min_periods=1, center=True).mean().to_numpy()})
        for nom, s in seuils_list.items():
            for k, val in resume_gps(trace, s, hz=hz).items():
                ligne[f"{k}__{nom}"] = round(float(val), 1)
        lignes.append(ligne)
    return lignes, info
