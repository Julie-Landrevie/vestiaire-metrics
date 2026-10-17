"""Chargement des données subjectives de SoccerMon (osf.io/uryz9, licence CC-BY 4.0).

D'après la description du jeu de données (Midoglu et al., Scientific Data, 2024), les
données subjectives sont des fichiers CSV séparés par indicateur (fatigue, mood,
readiness, soreness, stress, sleep_duration, sleep_quality, rpe, duration,
daily_load, acwr, ...). Dans chaque fichier, une colonne = une joueuse, une ligne = un jour.

Comme les noms exacts peuvent varier d'une version à l'autre, le chargeur ne suppose
rien : il lit tous les CSV d'un dossier et garde le nom du fichier comme nom
d'indicateur. Vérifier les noms avec ``lister_indicateurs`` avant d'aller plus loin.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def lire_fichier_large(chemin: str | Path) -> pd.DataFrame:
    """Lit un CSV « large » (dates en lignes, joueuses en colonnes) et le passe en format long."""
    df = pd.read_csv(chemin)
    col_date = next((c for c in df.columns if c.lower() in ("date", "dates", "day", "unnamed: 0")), df.columns[0])
    df = df.rename(columns={col_date: "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])
    long = df.melt(id_vars="date", var_name="joueuse", value_name="valeur")
    long["valeur"] = pd.to_numeric(long["valeur"], errors="coerce")
    return long.dropna(subset=["valeur"])


def lister_indicateurs(dossier: str | Path) -> list[str]:
    """Noms des indicateurs (fichiers CSV) trouvés dans un dossier et ses sous-dossiers."""
    return sorted({p.stem for p in Path(dossier).rglob("*.csv")})


def charger_dossier(dossier: str | Path, indicateurs: list[str] | None = None) -> pd.DataFrame:
    """Charge tous les CSV d'un dossier en un seul tableau : date, joueuse, une colonne par indicateur.

    Si plusieurs fichiers ont le même nom (une équipe par sous-dossier, par exemple),
    leurs lignes sont empilées.
    """
    tables = {}
    for p in sorted(Path(dossier).rglob("*.csv")):
        if indicateurs and p.stem not in indicateurs:
            continue
        t = lire_fichier_large(p).rename(columns={"valeur": p.stem})
        tables.setdefault(p.stem, []).append(t)
    if not tables:
        raise FileNotFoundError(f"Aucun CSV trouvé dans {dossier}")
    fusion = None
    for nom, morceaux in tables.items():
        t = pd.concat(morceaux).groupby(["date", "joueuse"], as_index=False)[nom].mean()
        fusion = t if fusion is None else fusion.merge(t, on=["date", "joueuse"], how="outer")
    return fusion.sort_values(["joueuse", "date"]).reset_index(drop=True)


# Correspondance SoccerMon -> questionnaire Vestiaire (échelles 1-5 dans les deux cas,
# à vérifier sur les fichiers : si une échelle est inversée, utiliser ``inverser``).
CORRESPONDANCE_FORME = {
    "fatigue": "fatigue",
    "sleep_quality": "sommeil",
    "soreness": "courbatures",
    "stress": "stress",
    "mood": "humeur",
}


def vers_etats_vestiaire(df: pd.DataFrame, inverser: tuple[str, ...] = ()) -> pd.DataFrame:
    """Transforme les colonnes de bien-être SoccerMon en questionnaire Vestiaire (1 à 5)."""
    cols = {k: v for k, v in CORRESPONDANCE_FORME.items() if k in df}
    out = df[["date", "joueuse", *cols]].rename(columns=cols)
    for q in inverser:
        out[q] = 6 - out[q]
    return out.dropna()


def vers_seances_vestiaire(df: pd.DataFrame, col_rpe: str = "rpe", col_duree: str = "duration") -> pd.DataFrame:
    """Transforme RPE et durée SoccerMon en séances Vestiaire (``rpe``, ``duree_min``)."""
    out = df[["date", "joueuse", col_rpe, col_duree]].rename(columns={col_rpe: "rpe", col_duree: "duree_min"})
    out = out.dropna()
    return out[(out["duree_min"] > 0) & out["rpe"].between(0, 10)]
