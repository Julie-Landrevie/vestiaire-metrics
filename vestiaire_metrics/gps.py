"""Lecture et résumé des fichiers GPS, adaptés au format SoccerMon (STATSports APEX).

Format SoccerMon :
- un fichier parquet par joueuse et par jour :
  ``<aaaa>/<aaaa-mm>/<aaaa-mm-jj>/<aaaa-mm-jj>-<TeamX-identifiant>.parquet`` ;
- colonnes utiles : ``time`` (« 08:23:15.6 »), ``speed`` (m/s), ``lat``.

Trois pièges traités :
1. chaque instant GPS (10 Hz) est répété environ 10 fois, car l'accéléromètre enregistre
   à 100 Hz sur des lignes séparées : une seule ligne est gardée par instant, sinon les
   distances seraient multipliées par 10 ;
2. le signal a des trous : la distance est intégrée avec le vrai pas de temps, et les
   trous de plus d'une seconde ne sont pas comblés ;
3. une latitude à 0 signifie « pas de satellite » : la vitesse de cet instant est ignorée.

D'autres formats (un fichier par séance avec une colonne joueuse, temps en dates ou en
millisecondes, vitesse en km/h) restent acceptés.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .zones import FEMININS, MASCULINS, Seuils

EXTENSIONS = {".csv", ".parquet"}
MOTIF_SOCCERMON = re.compile(r"^(\d{4}-\d{2}-\d{2})-(Team([A-Za-z])-.+)\.(parquet|csv)$")


@dataclass(frozen=True)
class Reglages:
    vitesse_max_ms: float = 10.0       # 36 km/h : au-delà, valeur aberrante
    trou_max_s: float = 1.0            # trou de signal non intégré au-delà
    pas_max_acc_s: float = 0.15        # accélération calculée seulement sur des pas de ~0,1 s
    lissage_points: int = 5            # médiane glissante sur 0,5 s
    duree_sprint_s: float = 1.0        # un sprint compte s'il dure au moins 1 s
    duree_acc_s: float = 0.5           # une accélération compte si elle dure au moins 0,5 s
    signal_min_min: float = 10.0       # séance retenue si au moins 10 min de signal...
    distance_min_m: float = 300.0      # ... et au moins 300 m parcourus


SEUILS = {"feminins": FEMININS, "masculins": MASCULINS}


# --------------------------------------------------------------------------- fichiers
def lister_fichiers(dossier: str | Path) -> list[Path]:
    """Fichiers GPS d'un dossier. Si des fichiers au format SoccerMon existent, seuls ceux-là."""
    tous = sorted(p for p in Path(dossier).rglob("*")
                  if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith("."))
    sm = [p for p in tous if MOTIF_SOCCERMON.match(p.name)]
    return sm or tous


def infos_nom_fichier(p: Path) -> dict:
    m = MOTIF_SOCCERMON.match(p.name)
    if not m:
        return {}
    return {"date": m.group(1), "joueuse": m.group(2), "equipe": f"Équipe {m.group(3).upper()}"}


def colonnes_fichier(chemin: Path) -> list[str]:
    """Noms de colonnes sans lire tout le fichier."""
    if chemin.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        return list(pq.read_schema(chemin).names)
    return list(pd.read_csv(chemin, nrows=2, sep=None, engine="python").columns)


def lire(chemin: Path, nrows: int | None = None, colonnes: list[str] | None = None) -> pd.DataFrame:
    if chemin.suffix.lower() == ".parquet" and nrows:
        import pyarrow.parquet as pq
        f = pq.ParquetFile(chemin)
        return next(f.iter_batches(batch_size=nrows)).to_pandas()
    if chemin.suffix.lower() == ".parquet":
        try:
            df = pd.read_parquet(chemin, columns=colonnes)
        except Exception:
            df = pd.read_parquet(chemin)
        return df.head(nrows) if nrows else df
    return pd.read_csv(chemin, nrows=nrows, sep=None, engine="python")


def _trouver(colonnes, exacts, contient):
    bas = {c.lower().strip(): c for c in colonnes}
    for n in exacts:
        if n in bas:
            return bas[n]
    for c in colonnes:
        if any(m in c.lower() for m in contient):
            return c
    return None


def detecter_colonnes(colonnes) -> dict:
    cols = list(colonnes)
    return {
        "vitesse": _trouver(cols, ["speed", "velocity", "vitesse", "speed_kmh", "speed (km/h)"], ["speed", "veloc", "vitesse"]),
        "temps": _trouver(cols, ["time", "timestamp", "datetime", "temps"], ["time"]),
        "latitude": _trouver(cols, ["lat", "latitude"], ["latitude"]),
        "joueuse": _trouver(cols, ["player_name", "player", "player_id", "athlete", "joueuse"], ["player", "athlete"]),
    }


# --------------------------------------------------------------------------- temps
def temps_en_secondes(t: pd.Series) -> tuple[np.ndarray, str]:
    """Convertit une colonne de temps en secondes. Formats acceptés : « 08:23:15.6 »,
    dates complètes, secondes ou millisecondes."""
    if pd.api.types.is_numeric_dtype(t):
        x = t.to_numpy(dtype=float)
        pas = np.nanmedian(np.diff(np.unique(x))) if len(x) > 1 else np.nan
        if pd.notna(pas) and pas > 5:
            return x / 1000.0, "millisecondes"
        return x, "secondes"
    s = t.astype(str)
    if s.str.match(r"^\d{1,2}:\d{2}:\d{2}").mean() > 0.9:
        parties = s.str.split(":", n=2, expand=True)
        sec = parties[0].astype(float) * 3600 + parties[1].astype(float) * 60 + parties[2].astype(float)
        return sec.to_numpy(), "heure (hh:mm:ss)"
    d = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
    return (d - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy(), "date et heure"


def _efforts(masque: np.ndarray, n_min: int) -> int:
    m = np.r_[False, np.asarray(masque, dtype=bool), False].astype(int)
    bords = np.flatnonzero(np.diff(m))
    return int(((bords[1::2] - bords[::2]) >= n_min).sum())


# --------------------------------------------------------------------------- résumé
def resumer_trace(df: pd.DataFrame, col_vitesse: str, col_temps: str | None, col_lat: str | None,
                  seuils: dict[str, Seuils] | None = None, reg: Reglages = Reglages(),
                  hz_defaut: float = 10.0) -> dict | None:
    """Résumé d'une séance d'une joueuse. Renvoie None si la trace est inexploitable."""
    seuils = seuils or SEUILS
    cols = [c for c in (col_temps, col_vitesse, col_lat) if c]
    d = df[cols].copy()
    if col_temps:
        n_lignes = len(d)
        d = d.drop_duplicates(col_temps)            # doublons de l'accéléromètre (100 Hz)
        sec, format_temps = temps_en_secondes(d[col_temps])
        d["_sec"] = sec
        d = d[np.isfinite(d["_sec"])]
        d = d.drop_duplicates("_sec").sort_values("_sec", kind="stable")
        doublons = n_lignes / max(1, len(d))
    else:
        d["_sec"] = np.arange(len(d)) / hz_defaut
        format_temps, doublons = f"absent ({hz_defaut:g} Hz supposés)", 1.0
    if len(d) < 50:
        return None

    v = pd.to_numeric(d[col_vitesse], errors="coerce").to_numpy(dtype=float)
    unite = "m/s"
    if np.nanpercentile(v, 99) > 12:  # valeurs en km/h
        v, unite = v / 3.6, "km/h"
    fix = np.ones(len(d), bool)
    if col_lat:
        lat = pd.to_numeric(d[col_lat], errors="coerce").to_numpy(dtype=float)
        fix = np.isfinite(lat) & (lat != 0)
    valide = fix & np.isfinite(v) & (v >= 0) & (v <= reg.vitesse_max_ms)
    aberrantes = int((fix & np.isfinite(v) & (v > reg.vitesse_max_ms)).sum())
    v = np.where(valide, v, np.nan)

    sec = d["_sec"].to_numpy()
    dt = np.r_[np.diff(sec), np.median(np.diff(sec)) if len(sec) > 1 else 0.1]
    dt_ok = np.where((dt > reg.trou_max_s) | (dt <= 0), 0.0, dt)
    v0 = np.nan_to_num(v, nan=0.0)
    pas = dt_ok * v0                                         # mètres parcourus à chaque pas
    hz = 1.0 / np.median(dt[dt > 0]) if (dt > 0).any() else hz_defaut

    lisse = pd.Series(v).rolling(reg.lissage_points, center=True, min_periods=1).median().to_numpy()
    dsec = np.diff(sec)
    acc = np.r_[np.nan, np.diff(lisse) / np.where(dsec > 0, dsec, np.nan)]
    acc[np.r_[False, dsec > reg.pas_max_acc_s]] = np.nan
    n_sprint = max(1, int(round(reg.duree_sprint_s * hz)))
    n_acc = max(1, int(round(reg.duree_acc_s * hz)))

    duree_s = sec[-1] - sec[0]
    signal_s = dt_ok.sum()
    res = {
        "duree_min": duree_s / 60,
        "signal_min": signal_s / 60,
        "part_signal_perdu": 1 - signal_s / duree_s if duree_s > 0 else np.nan,
        "part_sans_satellite": float(1 - fix.mean()),
        "points_aberrants": aberrantes,
        "lignes_par_instant": round(doublons, 1),
        "frequence_hz": round(hz, 1),
        "format_temps": format_temps,
        "unite_vitesse": unite,
        "distance_m": pas.sum(),
        "vitesse_max_kmh": np.nanmax(lisse) * 3.6 if np.isfinite(lisse).any() else np.nan,
    }
    vk = v0 * 3.6
    lk = np.nan_to_num(lisse, nan=0.0) * 3.6
    for nom, s in seuils.items():
        res[f"distance_course_m__{nom}"] = pas[(vk >= s.course) & (vk < s.hsr)].sum()
        res[f"distance_hsr_m__{nom}"] = pas[(vk >= s.hsr) & (vk < s.sprint)].sum()
        res[f"distance_sprint_m__{nom}"] = pas[vk >= s.sprint].sum()
        res[f"nb_sprints__{nom}"] = _efforts(lk >= s.sprint, n_sprint)
        res[f"nb_acc_hautes__{nom}"] = _efforts(np.nan_to_num(acc) >= s.acc_haute, n_acc)
        res[f"nb_dec_hautes__{nom}"] = _efforts(np.nan_to_num(acc) <= -s.acc_haute, n_acc)
    res["retenue"] = bool(res["signal_min"] >= reg.signal_min_min and res["distance_m"] >= reg.distance_min_m)
    return res


def analyser_fichier(chemin: str | Path) -> list[dict]:
    """Résume un fichier GPS. Une ligne par joueuse présente dans le fichier.

    Ne lève jamais d'erreur : un fichier illisible donne une ligne avec ``erreur``.
    """
    chemin = Path(chemin)
    base = {"fichier": chemin.name, **infos_nom_fichier(chemin)}
    try:
        noms_cols = colonnes_fichier(chemin)
        det = detecter_colonnes(noms_cols)
        if det["vitesse"] is None:
            return [{**base, "erreur": "aucune colonne de vitesse reconnue : " + ", ".join(map(str, noms_cols))}]
        utiles = [c for c in det.values() if c]
        df = lire(chemin, colonnes=utiles)
        groupes = df.groupby(det["joueuse"]) if (det["joueuse"] and "joueuse" not in base) else [(None, df)]
        lignes = []
        for joueuse, g in groupes:
            r = resumer_trace(g, det["vitesse"], det["temps"], det["latitude"])
            ligne = {**base}
            if joueuse is not None:
                ligne["joueuse"] = str(joueuse)
            ligne.setdefault("joueuse", chemin.stem)
            lignes.append({**ligne, **r} if r else {**ligne, "erreur": "trace trop courte"})
        return lignes
    except Exception as e:  # on note l'erreur et on continue
        return [{**base, "erreur": f"{type(e).__name__} : {e}"}]


# --------------------------------------------------------------------------- noms lisibles
def noms_lisibles(premiers_jours: pd.DataFrame) -> pd.DataFrame:
    """Règle du projet : « Équipe A » et joueuses A-01, A-02… numérotées par ordre d'arrivée
    (premier jour de données), puis par identifiant.

    premiers_jours : colonnes ``joueuse`` (identifiant SoccerMon) et ``premier_jour``.
    Renvoie : ``identifiant_soccermon``, ``equipe``, ``label``.
    """
    d = premiers_jours.copy()
    d["code"] = d["joueuse"].str.extract(r"^Team([A-Za-z])", expand=False).str.upper().fillna("X")
    d = d.sort_values(["code", "premier_jour", "joueuse"], na_position="last")
    d["label"] = d["code"] + "-" + (d.groupby("code").cumcount() + 1).map("{:02d}".format)
    return d.rename(columns={"joueuse": "identifiant_soccermon"}).assign(
        equipe="Équipe " + d["code"])[["identifiant_soccermon", "equipe", "label"]]


def lire_correspondance(chemin: str | Path) -> pd.DataFrame:
    """Lit un correspondance_joueuses.csv existant (projet R : label, team, identifiant_soccermon)."""
    c = pd.read_csv(chemin)
    col_id = next(k for k in c.columns if "identifiant" in k.lower() or k.lower() in ("player", "joueuse"))
    col_lab = next(k for k in c.columns if k.lower() == "label")
    col_eq = next((k for k in c.columns if k.lower() in ("team", "equipe", "équipe")), None)
    out = pd.DataFrame({"identifiant_soccermon": c[col_id].astype(str), "label": c[col_lab].astype(str)})
    out["equipe"] = c[col_eq] if col_eq else "Équipe " + out["label"].str[0]
    return out
