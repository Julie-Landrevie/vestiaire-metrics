"""Prépare les vraies données SoccerMon (anonymisées) pour le prototype Vestiaire.

Produit un petit fichier ``prototype_donnees_reelles.json`` avec ce qu'affichent :
- l'écran « Effectif du jour » de l'équipe A (forme, charge, ratio, statut, nuage volume /
  actions explosives sur les derniers jours de match probables) ;
- la « Fiche joueuse » d'A-19 (charge par semaine, forme sur 14 jours, profil match en
  percentiles avec les seuils masculins et féminins).

Utilisation, depuis le dossier vestiaire-metrics :

    python exporter_prototype.py

Le script cherche seul, sur le bureau :
- les séances GPS : resultats_vestiaire/seances_gps.csv (sortie de analyser_soccermon.py) ;
- les questionnaires SoccerMon : data/raw du projet R « Projet Suivi Charge Féminin » ;
- les noms A-01… : outputs/tables/correspondance_joueuses.csv du même projet.
Chaque chemin peut aussi être donné à la main (--gps-seances, --subjectif, --correspondance).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vestiaire_metrics as vm  # noqa: E402
from vestiaire_metrics import gps, soccermon  # noqa: E402

BUREAU = Path("~/Desktop").expanduser()
VARIABLES = ["daily_load", "fatigue", "mood", "sleep_quality", "soreness", "stress"]
F, M = "__feminins", "__masculins"


def chercher(motif: str, profondeur: int = 4) -> list[Path]:
    """Fichiers ou dossiers correspondant au motif sous le bureau, sans descendre dans les GPS."""
    trouves = []
    for niveau in range(1, profondeur + 1):
        for p in BUREAU.glob("/".join(["*"] * (niveau - 1) + [motif])):
            if "SoccerMon_GPS" not in str(p) and ".venv" not in str(p):
                trouves.append(p)
    return trouves


def trouver_seances(arg):
    if arg:
        return Path(arg).expanduser()
    ici = Path(__file__).resolve().parent / "resultats_vestiaire" / "seances_gps.csv"
    if ici.exists():
        return ici
    autres = sorted(chercher("resultats_vestiaire/seances_gps.csv", 5), key=lambda p: p.stat().st_mtime, reverse=True)
    return autres[0] if autres else None


def trouver_projet_r():
    for p in chercher("Projet Suivi Charge F*", 3):
        if p.is_dir():
            return p
    return None


def fr(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--gps-seances")
    a.add_argument("--subjectif")
    a.add_argument("--correspondance")
    a.add_argument("--joueuse", default="A-19")
    a.add_argument("--jour", help="forcer le jour affiché (aaaa-mm-jj)")
    a.add_argument("--sortie", default="prototype_donnees_reelles.json")
    a = a.parse_args()

    # ---------------------------------------------------------------- fichiers
    f_seances = trouver_seances(a.gps_seances)
    projet_r = trouver_projet_r()
    d_subj = Path(a.subjectif).expanduser() if a.subjectif else (projet_r / "data" / "raw" if projet_r else None)
    f_corr = Path(a.correspondance).expanduser() if a.correspondance else (
        projet_r / "outputs" / "tables" / "correspondance_joueuses.csv" if projet_r else None)
    print("Séances GPS     :", f_seances or "INTROUVABLES")
    print("Questionnaires  :", d_subj or "INTROUVABLES")
    print("Correspondance  :", f_corr if f_corr and f_corr.exists() else "absente (noms recalculés)")
    if not f_seances or not f_seances.exists():
        sys.exit("\nLance d'abord : python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS")
    if not d_subj or not d_subj.exists():
        sys.exit("\nDossier des questionnaires introuvable : indique-le avec --subjectif")

    # ---------------------------------------------------------------- données
    s = pd.read_csv(f_seances, parse_dates=["date"])
    s = s[s["retenue"].astype(bool)] if "retenue" in s else s
    sm = soccermon.charger_dossier(d_subj, indicateurs=VARIABLES)
    manquants = [v for v in VARIABLES if v not in sm]
    if manquants:
        sys.exit(f"\nIndicateurs absents des questionnaires : {manquants}. Trouvés : {soccermon.lister_indicateurs(d_subj)}")
    if f_corr and f_corr.exists():
        noms = gps.lire_correspondance(f_corr)
    else:
        pj = sm[sm["daily_load"] > 0].groupby("joueuse", as_index=False)["date"].min().rename(columns={"date": "premier_jour"})
        noms = gps.noms_lisibles(pj)
    pj_gps = s.groupby("joueuse", as_index=False)["date"].min().rename(columns={"date": "premier_jour"})
    noms, _ = gps.completer_noms(noms, pj_gps)
    sm["label"], sm["equipe"] = gps.appliquer_noms(sm["joueuse"], noms)
    s["label"], eq = gps.appliquer_noms(s["joueuse"], noms)
    s["equipe"] = eq.fillna(s.get("equipe"))
    sm = sm.dropna(subset=["label"])
    cible = a.joueuse
    equipe = "Équipe " + cible[0]
    if cible not in set(s["label"]):
        sys.exit(f"{cible} absente des séances GPS.")

    # Charge quotidienne (sRPE cumulé par jour). Dans SoccerMon, 0 = rien déclaré.
    q = sm.pivot_table(index="date", columns="label", values="daily_load", aggfunc="sum")
    q = q.reindex(pd.date_range(q.index.min(), q.index.max(), freq="D")).fillna(0.0)
    q.index.name = "date"

    # Forme sur 25 : sommeil, fatigue, courbatures, stress, humeur (1 à 5, 5 = favorable).
    w = sm.rename(columns={"sleep_quality": "sommeil", "soreness": "courbatures", "mood": "humeur"})
    w = w[["date", "label", "fatigue", "sommeil", "courbatures", "stress", "humeur"]].dropna()
    w = w[w[vm.QUESTIONS].apply(lambda c: c.between(1, 5)).all(axis=1)].rename(columns={"label": "joueuse"})
    ref = vm.reference_personnelle(w)

    # ---------------------------------------------------------------- choix du jour
    joueuses_eq = sorted(l for l in noms["label"] if l.startswith(cible[0]))
    rep_jour = ref[ref["joueuse"].isin(joueuses_eq)].groupby("date")["forme"].count()
    mp = s["match_probable"].astype(bool) if "match_probable" in s else pd.Series(False, index=s.index)
    matchs = sorted(s.loc[(s["equipe"] == equipe) & mp, "date"].unique())
    hist = q[cible].gt(0).rolling(35, min_periods=1).sum()
    if a.jour:
        jour = pd.Timestamp(a.jour)
    else:
        candidats = []
        for d in rep_jour.index:
            if rep_jour[d] < min(12, int(0.7 * len(joueuses_eq))) or d not in hist.index or hist[d] < 15:
                continue
            ok = ref[(ref["joueuse"] == cible) & (ref["date"] == d)]["moyenne_perso"].notna().any()
            prochain = [m for m in matchs if 1 <= (pd.Timestamp(m) - d).days <= 3]
            if ok:
                candidats.append((bool(prochain), rep_jour[d], d))
        if not candidats:
            sys.exit("Aucun jour avec assez de données : indique-en un avec --jour aaaa-mm-jj")
        jour = sorted(candidats)[-1][2]
    print(f"\nJour affiché : {jour:%d/%m/%Y}")

    # ---------------------------------------------------------------- effectif du jour
    qj = q.loc[:jour, [c for c in q.columns if c in joueuses_eq]]
    charge = vm.resume_charge(qj, jour)
    fj = ref[ref["date"] == jour].set_index("joueuse")[["forme", "moyenne_perso"]]
    actives = [j for j in qj.columns if qj[j].tail(14).gt(0).any()]
    charge = charge.loc[actives]
    fj = fj.reindex(actives)
    statut = vm.statut_du_jour(charge, fj, None, vm.Reperes())
    effectif = []
    for j, r in statut.iterrows():
        c = charge.loc[j]
        effectif.append({
            "joueuse": j, "statut": r["statut"], "pourquoi": r["pourquoi"],
            "forme": None if pd.isna(fj.loc[j, "forme"]) else int(fj.loc[j, "forme"]),
            "moyenne_perso": None if pd.isna(fj.loc[j, "moyenne_perso"]) else round(float(fj.loc[j, "moyenne_perso"]), 1),
            "charge_7j": round(float(c["charge_7j"])),
            "ratio": None if pd.isna(c["ratio"]) else round(float(c["ratio"]), 2),
        })

    # nuage : 4 derniers jours de match probables de l'équipe jusqu'au jour affiché
    m4 = [m for m in matchs if pd.Timestamp(m) <= jour][-4:]
    sm4 = s[(s["equipe"] == equipe) & s["date"].isin(m4)]
    source_nuage = "4 derniers jours de match probables"
    if sm4["label"].nunique() < 8:  # pas assez de matchs : 4 dernières semaines de séances
        sm4 = s[(s["equipe"] == equipe) & (s["date"] > jour - pd.Timedelta(days=28)) & (s["date"] <= jour)]
        source_nuage = "séances des 4 dernières semaines"
    nuage = (sm4.assign(explosives=sm4["nb_acc_hautes" + F] + sm4["nb_dec_hautes" + F])
             .groupby("label").agg(distance_m=("distance_m", "mean"), explosives=("explosives", "mean"),
                                   seances=("fichier", "size")).reset_index())

    # ---------------------------------------------------------------- fiche joueuse
    sj = q[cible]
    semaines = [float(sj.loc[jour - pd.Timedelta(days=7 * (k + 1) - 1): jour - pd.Timedelta(days=7 * k)].sum()) for k in range(6)][::-1]
    forme14 = ref[(ref["joueuse"] == cible) & (ref["date"] > jour - pd.Timedelta(days=14)) & (ref["date"] <= jour)]
    jours14 = pd.date_range(jour - pd.Timedelta(days=13), jour)
    f14 = forme14.set_index("date")["forme"].reindex(jours14)

    # profil match : percentiles parmi les joueuses de champ (au moins 10 séances), toutes séances
    champ = s.groupby("label").agg(n=("fichier", "size"), vmax=("vitesse_max_kmh", "median"))
    champ = champ[(champ["n"] >= 10) & (champ["vmax"] >= 20)].index
    base = s[s["label"].isin(champ)]
    dims = [("Volume (distance par séance)", "distance_m", None, "m"),
            ("Course à haute vitesse", "distance_hsr_m", True, "m"),
            ("Distance de sprint", "distance_sprint_m", True, "m"),
            ("Nombre de sprints", "nb_sprints", True, ""),
            ("Accélérations hautes", "nb_acc_hautes", True, ""),
            ("Décélérations hautes", "nb_dec_hautes", True, ""),
            ("Vitesse de pointe (médiane)", "vitesse_max_kmh", None, "km/h")]
    profil = []
    for nom, col, par_seuil, unite in dims:
        ligne = {"dimension": nom, "unite": unite}
        for suffixe, cle in ((M, "masculin"), (F, "feminin")) if par_seuil else (("", "commun"),):
            c = col + suffixe
            agg = base.groupby("label")[c].median() if col == "vitesse_max_kmh" else base.groupby("label")[c].mean()
            ligne[f"valeur_{cle}"] = round(float(agg[cible]), 1)
            ligne[f"percentile_{cle}"] = int(round(agg.rank(pct=True)[cible] * 100))
        profil.append(ligne)

    sortie = {
        "source": "SoccerMon (Midoglu et al., 2024, CC-BY 4.0), joueuses anonymisées",
        "jour": jour.strftime("%Y-%m-%d"),
        "equipe": equipe,
        "effectif": effectif,
        "resume_effectif": {k: int(v) for k, v in statut["statut"].value_counts().items()},
        "etats_recus": int(fj["forme"].notna().sum()),
        "joueuses_actives": len(actives),
        "nuage": {"source": source_nuage, "jours": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in m4],
                  "points": nuage.round(1).to_dict("records")},
        "fiche": {
            "joueuse": cible,
            "seances_gps": int((s["label"] == cible).sum()),
            "comparees_a": int(len(champ)),
            "forme": next((e["forme"] for e in effectif if e["joueuse"] == cible), None),
            "moyenne_perso": next((e["moyenne_perso"] for e in effectif if e["joueuse"] == cible), None),
            "statut": next((e["statut"] for e in effectif if e["joueuse"] == cible), None),
            "pourquoi": next((e["pourquoi"] for e in effectif if e["joueuse"] == cible), None),
            "charge_7j": round(float(charge.loc[cible, "charge_7j"])) if cible in charge.index else None,
            "moyenne_hebdo_4sem": None if cible not in charge.index or pd.isna(charge.loc[cible, "moyenne_hebdo_4sem"]) else round(float(charge.loc[cible, "moyenne_hebdo_4sem"])),
            "ratio": None if cible not in charge.index or pd.isna(charge.loc[cible, "ratio"]) else round(float(charge.loc[cible, "ratio"]), 2),
            "saisies_14j": int(f14.notna().sum()),
            "charge_6_semaines": [round(x) for x in semaines],
            "forme_14_jours": [None if pd.isna(x) else int(x) for x in f14],
            "profil_match": profil,
        },
    }
    Path(a.sortie).write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------------------------------------------------------- résumé lisible
    fi = sortie["fiche"]
    print(f"{equipe} : {len(actives)} joueuses actives, {sortie['etats_recus']} états du jour reçus, statuts {sortie['resume_effectif']}")
    print(f"{cible} : forme {fi['forme']}/25 (moyenne {fi['moyenne_perso']}), charge 7 j {fi['charge_7j']}, ratio {fi['ratio']}, {fi['statut']}")
    print(f"Profil match de {cible} (percentile parmi {fi['comparees_a']} joueuses de champ) :")
    for p in profil:
        if "percentile_commun" in p:
            print(f"  {p['dimension']:<32} {p['percentile_commun']:>3}e")
        else:
            print(f"  {p['dimension']:<32} masc. {p['percentile_masculin']:>3}e  ->  fém. {p['percentile_feminin']:>3}e")
    print(f"\n-> {Path(a.sortie).resolve()}  (fichier à m'envoyer)")


if __name__ == "__main__":
    main()
