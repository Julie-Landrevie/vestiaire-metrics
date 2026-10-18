"""Seuils féminins contre seuils masculins sur les données GPS de SoccerMon, sur ton ordinateur.

Utilisation, depuis le dossier vestiaire-metrics :

    python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS --max-fichiers 200   # essai
    python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS                      # tout

Options :
    --subjectif DOSSIER       ajoute la charge (sRPE) et la forme des questionnaires
    --correspondance FICHIER  noms A-01, B-03… du projet R (trouvé automatiquement s'il est
                              dans ~/Desktop/Projet Suivi Charge Féminin/outputs/tables)
    --coeurs N                nombre de cœurs utilisés (par défaut : tous sauf deux)

L'analyse complète lit environ 10 000 fichiers. Elle peut être interrompue (Ctrl + C) et
relancée : les fichiers déjà traités ne sont pas relus.

Résultats dans « resultats_vestiaire » :
    rapport_vestiaire.html      le rapport, à ouvrir dans un navigateur
    seances_gps.csv             une ligne par joueuse et par séance retenue
    cache_gps_v2.csv            mémoire des fichiers déjà lus (permet de reprendre)
    joueuses_gps.csv            une ligne par joueuse, noms lisibles
    correspondance_joueuses.csv lien entre noms lisibles et identifiants SoccerMon
    exploration.txt             ce que le script a trouvé dans les dossiers
"""

from __future__ import annotations

import argparse
import base64
import io
import multiprocessing as mp
import os
import sys
import time
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vestiaire_metrics as vm  # noqa: E402
from vestiaire_metrics import gps, soccermon  # noqa: E402

BLEU_NUIT, TURQUOISE, ORANGE, GRIS, GRIS_CLAIR = "#0B1F3A", "#1EC8B0", "#A35F00", "#9AA8B8", "#D5DDE7"
F, M = "__feminins", "__masculins"
CORRESPONDANCE_R = Path("~/Desktop/Projet Suivi Charge Féminin/outputs/tables/correspondance_joueuses.csv").expanduser()
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
                     "font.size": 10})


# --------------------------------------------------------------------------- outils
def fr(x, d=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def pct(x, d=0):
    return fr(100 * x, d) + " %"


DOSSIER_FIGURES: Path | None = None


def image(fig, alt) -> str:
    """Graphique intégré au rapport, et copie PNG dans resultats_vestiaire/figures (pour le README)."""
    if DOSSIER_FIGURES is not None:
        import unicodedata
        nom = unicodedata.normalize("NFKD", alt.lower()).encode("ascii", "ignore").decode()
        nom = "".join(c if c.isalnum() else "_" for c in nom).strip("_")
        fig.savefig(DOSSIER_FIGURES / f"{nom}.png", dpi=150, bbox_inches="tight")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return f'<img alt="{alt}" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def tableau(df: pd.DataFrame) -> str:
    return df.to_html(index=False, classes="t", escape=True, na_rep="–")


# --------------------------------------------------------------------------- exploration
def explorer(dossier: Path, titre: str, lignes: list[str]) -> None:
    fichiers = [p for p in dossier.rglob("*") if p.is_file() and not p.name.startswith(".")]
    lignes += [f"=== {titre} : {dossier}",
               f"{len(fichiers)} fichiers, {sum(p.stat().st_size for p in fichiers) / 1e9:,.1f} Go",
               "Extensions : " + ", ".join(f"{e or '(aucune)'} x{n}" for e, n in Counter(p.suffix.lower() for p in fichiers).most_common())]
    exemples = gps.lister_fichiers(dossier)[:2] if titre == "GPS" else sorted(dossier.rglob("*.csv"))[:3]
    for p in exemples:
        lignes.append(f"\n--- Exemple : {p.relative_to(dossier)}")
        try:
            df = gps.lire(p, nrows=12)
            lignes.append("Colonnes : " + ", ".join(f"{c} ({t})" for c, t in df.dtypes.astype(str).items()))
            lignes.append(df.iloc[:, :8].to_string()[:2000])
        except Exception as e:
            lignes.append(f"Lecture impossible : {e}")
    lignes.append("")


# --------------------------------------------------------------------------- GPS
def traiter_gps(dossier: Path, cache: Path, max_fichiers: int | None, coeurs: int) -> pd.DataFrame:
    fichiers = gps.echantillon(gps.lister_fichiers(dossier), max_fichiers)
    deja = set(pd.read_csv(cache, usecols=["fichier"])["fichier"]) if cache.exists() else set()
    a_faire = [p for p in fichiers if p.name not in deja]
    print(f"  {len(fichiers)} fichiers GPS, {len(a_faire)} à traiter ({len(deja)} déjà faits), {coeurs} cœur(s)")
    debut, tampon, n = time.time(), [], 0

    def vider():
        if tampon:
            pd.DataFrame(tampon).to_csv(cache, mode="a", header=not cache.exists(), index=False)
            tampon.clear()

    if a_faire:
        with mp.Pool(coeurs) as pool:
            for lignes in pool.imap_unordered(gps.analyser_fichier, a_faire, chunksize=4):
                tampon += lignes
                n += 1
                if n % 200 == 0 or n == len(a_faire):
                    vider()
                    ecoule = time.time() - debut
                    print(f"  {n}/{len(a_faire)} fichiers ({100 * n / len(a_faire):.0f} %), "
                          f"{ecoule / 60:.1f} min écoulées, environ {ecoule / n * (len(a_faire) - n) / 60:.0f} min restantes")
        vider()
    s = pd.read_csv(cache)
    noms = {p.name for p in fichiers}
    return s[s["fichier"].isin(noms)].reset_index(drop=True)


def choisir_noms(seances: pd.DataFrame, correspondance: Path | None, sm: pd.DataFrame | None) -> tuple[pd.DataFrame, str]:
    if correspondance and correspondance.exists():
        noms = gps.lire_correspondance(correspondance)
        if len(seances):
            pj = seances.groupby("joueuse", as_index=False)["date"].min().rename(columns={"date": "premier_jour"})
            noms, ajoutes = gps.completer_noms(noms, pj)
            if ajoutes:
                return noms, (f"noms repris du projet R ({correspondance.name}) ; {len(ajoutes)} joueuse(s) absente(s) de ce fichier, "
                              f"présente(s) seulement dans le GPS, numérotée(s) à la suite : {', '.join(sorted(ajoutes))}")
        return noms, f"noms repris du projet R ({correspondance.name})"
    if sm is not None and "daily_load" in sm:
        pj = sm[sm["daily_load"] > 0].groupby("joueuse", as_index=False)["date"].min().rename(columns={"date": "premier_jour"})
        return gps.noms_lisibles(pj), "noms calculés comme dans le projet R (premier jour avec une charge)"
    pj = seances.groupby("joueuse", as_index=False)["date"].min().rename(columns={"date": "premier_jour"})
    return gps.noms_lisibles(pj), "noms calculés sur le premier jour de GPS (peuvent différer du projet R)"


def section_gps(s_all: pd.DataFrame, noms: pd.DataFrame, source_noms: str) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    erreurs = s_all["erreur"].notna() if "erreur" in s_all else pd.Series(False, index=s_all.index)
    lues = s_all[~erreurs]
    s = lues[lues["retenue"].astype(bool)].copy()
    if s.empty:
        return "<p><strong>Aucune séance exploitable.</strong> Voir exploration.txt.</p>", pd.DataFrame(), pd.DataFrame()
    equipe_fichier = s["equipe"] if "equipe" in s else pd.Series("Équipe ?", index=s.index)
    s["label"], eq = gps.appliquer_noms(s["joueuse"], noms)
    s["equipe"] = eq.fillna(equipe_fichier)
    s["label"] = s["label"].fillna("?")
    s["date"] = pd.to_datetime(s["date"], errors="coerce")
    h = []

    # Gardiennes probables : vitesse max médiane sous 20 km/h sur au moins 10 séances.
    # Leur activité n'est pas comparable à celle des joueuses de champ : elles sont écartées.
    vmax_j = s.groupby("label").agg(n=("fichier", "size"), vmax=("vitesse_max_kmh", "median"))
    gardiennes = sorted(vmax_j[(vmax_j["n"] >= 10) & (vmax_j["vmax"] < 20)].index)
    toutes = s
    s = s[~s["label"].isin(gardiennes)].copy()

    # Jours de match probables : SoccerMon ne distingue pas match et entraînement. On retient les
    # jours où au moins 8 joueuses d'une équipe ont du GPS et où leur distance médiane dépasse 7 km.
    jour = s.groupby(["equipe", "date"]).agg(n=("label", "size"), dmed=("distance_m", "median")).reset_index()
    jours_match = jour[(jour["n"] >= 8) & (jour["dmed"] >= 7000)][["equipe", "date"]]
    s["match_probable"] = s.merge(jours_match.assign(m=True), on=["equipe", "date"], how="left")["m"].fillna(False).astype(bool).to_numpy()

    # ---- en bref
    avec_f = (s["nb_sprints" + F] > 0).mean()
    avec_m = (s["nb_sprints" + M] > 0).mean()
    med_f, med_m = s["distance_sprint_m" + F].median(), s["distance_sprint_m" + M].median()
    h.append('<div class="kpis">'
             f'<div><span>Séances analysées</span><strong>{fr(len(s), 0)}</strong><em>{s["label"].nunique()} joueuses, '
             f'{s["date"].min():%m/%Y} à {s["date"].max():%m/%Y}</em></div>'
             f'<div><span>Distance médiane</span><strong>{fr(s["distance_m"].median() / 1000)} km</strong><em>par joueuse et par séance</em></div>'
             f'<div><span>Séances avec au moins un sprint</span><strong>{pct(avec_f)}</strong><em>contre {pct(avec_m)} avec les seuils masculins</em></div>'
             f'<div><span>Distance de sprint médiane</span><strong>{fr(med_f, 0)} m</strong><em>contre {fr(med_m, 0)} m avec les seuils masculins</em></div>'
             '</div>')
    h.append(f"<p class='lead'>Avec un sprint à 25 km/h, {pct(1 - avec_m)} des séances ne contiennent aucun sprint. "
             f"Avec le seuil féminin de 23 km/h, cette part tombe à {pct(1 - avec_f)} : le seuil masculin efface une grande partie "
             "des efforts rapides des joueuses, comme l'a montré SkillCorner en match.</p>")

    # ---- par équipe
    eq = s.groupby("equipe").agg(**{
        "Séances": ("label", "size"), "Joueuses": ("label", "nunique"),
        "Distance médiane (km)": ("distance_m", lambda x: x.median() / 1000),
        "Vitesse max médiane (km/h)": ("vitesse_max_kmh", "median"),
        "Sprint médian, seuil masc. (m)": ("distance_sprint_m" + M, "median"),
        "Sprint médian, seuil fém. (m)": ("distance_sprint_m" + F, "median"),
    }).reset_index().rename(columns={"equipe": "Équipe"})
    for c in eq.columns[3:]:
        eq[c] = eq[c].map(lambda x: fr(x, 1))
    h.append("<h3>Par équipe</h3>" + tableau(eq))

    # ---- couverture
    h.append("<h2>1. Couverture : combien de séances ont au moins un effort ?</h2>")
    ind = [("nb_sprints", "Sprint"), ("distance_hsr_m", "Course à haute vitesse"),
           ("nb_acc_hautes", "Accélération haute"), ("nb_dec_hautes", "Décélération haute")]
    cov = pd.DataFrame({"indicateur": [n for _, n in ind],
                        "masc": [(s[c + M] > 0).mean() * 100 for c, _ in ind],
                        "fem": [(s[c + F] > 0).mean() * 100 for c, _ in ind]})
    fig, ax = plt.subplots(figsize=(9, 3.4))
    y = np.arange(len(cov))
    ax.barh(y + .2, cov["masc"], .38, color=GRIS, label="seuils masculins")
    ax.barh(y - .2, cov["fem"], .38, color=BLEU_NUIT, label="seuils féminins")
    for i, r in cov.iterrows():
        ax.text(r["masc"] + 1, i + .2, f"{r['masc']:.0f} %", va="center", fontsize=9, color="#4A5B72")
        ax.text(r["fem"] + 1, i - .2, f"{r['fem']:.0f} %", va="center", fontsize=9, color=BLEU_NUIT, fontweight="bold")
    ax.set_yticks(y, cov["indicateur"])
    ax.invert_yaxis()
    ax.set_xlim(0, 110)
    ax.set_xlabel("Part des séances avec au moins un effort (%)")
    ax.set_title("Les seuils féminins font apparaître des efforts dans beaucoup plus de séances")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.22), ncol=2, fontsize=9)
    h.append(image(fig, "Couverture par indicateur"))
    h.append("<p class='note'>Sprint : au moins 1 s au-delà de 23 km/h (25 km/h en masculin). "
             "Accélération et décélération hautes : au moins 0,5 s au-delà de 2,7 m/s² (3 m/s² en masculin). "
             "Course à haute vitesse : 19-23 km/h (20-25 km/h en masculin).</p>")

    # ---- distributions
    h.append("<h2>2. Distribution par séance</h2>")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, col, titre, unite in [(axes[0], "distance_sprint_m", "Distance de sprint par séance", "m"),
                                  (axes[1], "nb_acc_hautes", "Accélérations hautes par séance", "")]:
        hi = max(np.nanpercentile(s[col + F], 98), 1)
        bins = np.linspace(0, hi, 30) if unite else np.arange(0, hi + 2) - .5
        ax.hist(s[col + M].clip(upper=hi), bins=bins, color=GRIS, alpha=.85, label="seuils masculins")
        ax.hist(s[col + F].clip(upper=hi), bins=bins, color=TURQUOISE, alpha=.65, label="seuils féminins")
        ax.set_title(titre)
        ax.set_ylabel("Nombre de séances")
        ax.legend(frameon=False, fontsize=9)
    h.append(image(fig, "Distributions par séance"))
    h.append("<p class='note'>Les séances au-delà du 98e centile sont regroupées dans la dernière barre.</p>")
    h.append("<p>Avec les seuils masculins, les séances s'entassent à zéro : il devient difficile de distinguer les joueuses. "
             "Avec les seuils féminins, la distribution s'étale.</p>")

    # ---- matchs probables
    m = s[s["match_probable"]]
    if len(m) >= 30:
        h.append("<h2>3. Les jours de match probables</h2>")
        h.append(f"<p>SoccerMon ne distingue pas matchs et entraînements. En retenant les jours où au moins 8 joueuses d'une équipe "
                 f"ont couru plus de 7 km en médiane, on isole <strong>{fr(len(jours_match), 0)} jours</strong> "
                 f"({fr(len(m), 0)} séances de joueuses) qui ressemblent à des matchs. C'est le contexte des seuils de SkillCorner.</p>")
        lignes = []
        for nom, d in (("Jours de match probables", m), ("Autres jours", s[~s["match_probable"]])):
            lignes.append({"": nom, "Séances": fr(len(d), 0),
                           "Distance médiane (km)": fr(d["distance_m"].median() / 1000, 1),
                           "Au moins un sprint (masc.)": pct((d["nb_sprints" + M] > 0).mean()),
                           "Au moins un sprint (fém.)": pct((d["nb_sprints" + F] > 0).mean()),
                           "Sprint médian masc. (m)": fr(d["distance_sprint_m" + M].median(), 0),
                           "Sprint médian fém. (m)": fr(d["distance_sprint_m" + F].median(), 0)})
        h.append(tableau(pd.DataFrame(lignes)))
        h.append(f"<p>En match, avec le seuil masculin, {pct((m['nb_sprints' + M] == 0).mean())} des séances de joueuses "
                 f"n'ont toujours aucun sprint, contre {pct((m['nb_sprints' + F] == 0).mean())} avec le seuil féminin.</p>")

    # ---- joueuses
    j = s.groupby(["equipe", "label"]).agg(
        seances=("fichier", "size"),
        distance_km=("distance_m", lambda x: x.median() / 1000),
        vmax=("vitesse_max_kmh", "median"),
        sprint_m=("distance_sprint_m" + M, "mean"), sprint_f=("distance_sprint_m" + F, "mean"),
        acc_m=("nb_acc_hautes" + M, "mean"), acc_f=("nb_acc_hautes" + F, "mean"),
    ).reset_index()
    j = j[j["seances"] >= 10].copy()
    h.append("<h2>4. Les joueuses de champ</h2>")
    h.append(f"<p>{len(j)} joueuses de champ avec au moins 10 séances. Noms : {source_noms}.</p>")
    if gardiennes:
        h.append(f"<p class='note'>Écartées comme gardiennes probables (vitesse max médiane sous 20 km/h) : {', '.join(gardiennes)}. "
                 "Si l'une d'elles n'est pas gardienne, me le signaler.</p>")
    jj = j.sort_values("sprint_f")
    fig, ax = plt.subplots(figsize=(9, max(3.5, .24 * len(jj) + 1)))
    y = np.arange(len(jj))
    ax.barh(y + .2, jj["sprint_m"], .4, color=GRIS, label="seuils masculins")
    ax.barh(y - .2, jj["sprint_f"], .4, color=BLEU_NUIT, label="seuils féminins")
    ax.set_yticks(y, jj["label"], fontsize=8)
    ax.set_xlabel("Distance de sprint moyenne par séance (m)")
    ax.set_title("Distance de sprint par séance, par joueuse")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    h.append(image(fig, "Sprint par joueuse"))

    # ---- profils cachés
    for c in ("sprint", "acc"):
        j[f"rang_{c}_m"] = j[f"{c}_m"].rank(pct=True) * 100
        j[f"rang_{c}_f"] = j[f"{c}_f"].rank(pct=True) * 100
    corr_s = j["rang_sprint_m"].corr(j["rang_sprint_f"])
    corr_a = j["rang_acc_m"].corr(j["rang_acc_f"])
    caches = j[((j["rang_sprint_m"] <= 25) & (j["rang_sprint_f"] >= 50)) | ((j["rang_acc_m"] <= 25) & (j["rang_acc_f"] >= 50))]
    h.append("<h2>5. Des profils cachés par les seuils masculins ?</h2>")
    h.append(f"<p>Chaque joueuse est classée parmi les {len(j)} joueuses (rang en percentile), une fois avec chaque jeu de seuils. "
             f"Corrélation entre les deux classements : <strong>{fr(corr_s, 2)}</strong> pour le sprint, "
             f"<strong>{fr(corr_a, 2)}</strong> pour les accélérations hautes. Une joueuse « cachée » est dans le quart inférieur "
             "avec les seuils masculins mais au-dessus de la médiane avec les seuils féminins.</p>")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, c, titre in [(axes[0], "sprint", "Distance de sprint"), (axes[1], "acc", "Accélérations hautes")]:
        cache = (j[f"rang_{c}_m"] <= 25) & (j[f"rang_{c}_f"] >= 50)
        ax.axvspan(0, 25, ymin=50 / 102, color=ORANGE, alpha=.08)
        ax.plot([0, 100], [0, 100], color=GRIS_CLAIR, lw=1, ls="--")
        ax.scatter(j.loc[~cache, f"rang_{c}_m"], j.loc[~cache, f"rang_{c}_f"], s=28, color=GRIS)
        ax.scatter(j.loc[cache, f"rang_{c}_m"], j.loc[cache, f"rang_{c}_f"], s=46, color=ORANGE, zorder=3)
        for _, r in j[cache].iterrows():
            ax.annotate(r["label"], (r[f"rang_{c}_m"], r[f"rang_{c}_f"]), xytext=(5, 3),
                        textcoords="offset points", fontsize=8, color=ORANGE, fontweight="bold")
        ax.set_xlim(0, 102); ax.set_ylim(0, 102)
        ax.set_xlabel("Rang avec les seuils masculins (percentile)")
        ax.set_ylabel("Rang avec les seuils féminins (percentile)")
        nb = int(cache.sum())
        ax.set_title(f"{titre} : " + ("aucune joueuse cachée" if nb == 0 else f"{nb} joueuse{'s' if nb > 1 else ''} cachée{'s' if nb > 1 else ''}"))
    h.append(image(fig, "Profils cachés"))
    if len(caches):
        t = caches.assign(**{
            "Sprint masc. (m)": caches["sprint_m"].map(lambda x: fr(x, 0)), "Sprint fém. (m)": caches["sprint_f"].map(lambda x: fr(x, 0)),
            "Rang sprint masc. → fém.": caches.apply(lambda r: f"{r['rang_sprint_m']:.0f}e → {r['rang_sprint_f']:.0f}e", axis=1),
            "Rang accél. masc. → fém.": caches.apply(lambda r: f"{r['rang_acc_m']:.0f}e → {r['rang_acc_f']:.0f}e", axis=1),
        })[["label", "equipe", "seances", "Sprint masc. (m)", "Sprint fém. (m)", "Rang sprint masc. → fém.", "Rang accél. masc. → fém."]]
        h.append(tableau(t.rename(columns={"label": "Joueuse", "equipe": "Équipe", "seances": "Séances"})))
    else:
        h.append("<p>Aucune joueuse ne remplit les deux conditions. Sur des moyennes de plusieurs dizaines de séances, le classement "
                 "des joueuses bouge peu : les seuils féminins changent surtout ce qu'on mesure chez chacune (plus de sprints, plus "
                 "d'accélérations), pas leur ordre. L'effet « Beever-Jones » montré par SkillCorner portait sur des actions rares "
                 "(accélérations explosives menant à un sprint) mesurées en match, où un seuil trop haut ramène beaucoup de joueuses à zéro.</p>")

    # ---- tableau complet
    t = j.sort_values(["equipe", "label"]).assign(**{
        "Distance médiane (km)": j["distance_km"].map(lambda x: fr(x, 1)),
        "Vitesse max médiane (km/h)": j["vmax"].map(lambda x: fr(x, 1)),
        "Sprint / séance masc. (m)": j["sprint_m"].map(lambda x: fr(x, 0)),
        "Sprint / séance fém. (m)": j["sprint_f"].map(lambda x: fr(x, 0)),
        "Accél. hautes / séance masc.": j["acc_m"].map(lambda x: fr(x, 1)),
        "Accél. hautes / séance fém.": j["acc_f"].map(lambda x: fr(x, 1)),
    })
    cols = ["label", "equipe", "seances", "Distance médiane (km)", "Vitesse max médiane (km/h)", "Sprint / séance masc. (m)",
            "Sprint / séance fém. (m)", "Accél. hautes / séance masc.", "Accél. hautes / séance fém."]
    h.append("<details><summary>Tableau complet des joueuses</summary>" +
             tableau(t[cols].rename(columns={"label": "Joueuse", "equipe": "Équipe", "seances": "Séances"})) + "</details>")

    # ---- qualité
    q = [("Fichiers lus", fr(len(s_all), 0)), ("Fichiers illisibles", fr(int(erreurs.sum()), 0)),
         ("Séances écartées (moins de 10 min de signal ou de 300 m)", fr(len(lues) - len(s), 0)),
         ("Séances retenues", fr(len(toutes), 0)),
         ("Dont séances de gardiennes probables (écartées des comparaisons)", fr(len(toutes) - len(s), 0)),
         ("Lignes par instant dans les fichiers (doublons retirés)", fr(lues["lignes_par_instant"].median(), 0)),
         ("Fréquence GPS (médiane)", fr(lues["frequence_hz"].median(), 0) + " Hz"),
         ("Unité de vitesse lue", ", ".join(lues["unite_vitesse"].dropna().unique())),
         ("Format du temps", ", ".join(lues["format_temps"].dropna().unique())),
         ("Signal perdu (médiane par séance)", pct(s["part_signal_perdu"].median(), 1)),
         ("Instants sans satellite (médiane)", pct(s["part_sans_satellite"].median(), 1)),
         ("Vitesse max médiane", fr(s["vitesse_max_kmh"].median(), 1) + " km/h")]
    h.append("<h2>6. Qualité des données</h2>" + tableau(pd.DataFrame(q, columns=["Contrôle", "Valeur"])))
    if erreurs.any():
        ex = s_all.loc[erreurs, "erreur"].value_counts().head(3)
        h.append("<p class='note'>Erreurs les plus fréquentes : " + " · ".join(f"{k} ({v})" for k, v in ex.items()) + "</p>")
    return "\n".join(h), j, s


# --------------------------------------------------------------------------- questionnaires
def section_subjectif(sm: pd.DataFrame, noms: pd.DataFrame) -> str:
    lab, _ = gps.appliquer_noms(sm["joueuse"], noms)
    sm = sm.assign(joueuse=lab.fillna(sm["joueuse"]))
    cols = {c.lower(): c for c in sm.columns}
    h = [f"<p>Indicateurs trouvés : {', '.join(c for c in sm.columns if c not in ('date', 'joueuse'))}.</p>"]
    c_rpe, c_duree = cols.get("rpe"), next((cols[k] for k in ("duration", "duree") if k in cols), None)
    if c_rpe and c_duree:
        seances = soccermon.vers_seances_vestiaire(sm, c_rpe, c_duree)
        q = vm.charge_quotidienne(seances)
        h.append(f"<p>{fr(len(seances), 0)} séances notées, {q.shape[1]} joueuses, du {q.index.min():%d/%m/%Y} au {q.index.max():%d/%m/%Y}.</p>")
        if "acwr" in cols:
            fourni = sm.pivot_table(index="date", columns="joueuse", values=cols["acwr"])
            calc = vm.ratio_aigu_chronique(q, "couple")
            a, b = calc.stack(), fourni.stack()
            commun = a.index.intersection(b.index)
            a, b = a[commun], b[commun]
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() > 10:
                fig, ax = plt.subplots(figsize=(4.8, 4.2))
                ax.scatter(b[ok], a[ok], s=4, alpha=.25, color=BLEU_NUIT)
                lim = np.nanpercentile(np.r_[a[ok], b[ok]], 99.5)
                ax.plot([0, lim], [0, lim], color=ORANGE, lw=1)
                ax.set_xlim(0, lim); ax.set_ylim(0, lim)
                ax.set_xlabel("ACWR fourni par SoccerMon"); ax.set_ylabel("Ratio calculé par Vestiaire")
                ax.set_title(f"Corrélation : {fr(a[ok].corr(b[ok]), 2)}")
                h.append(f"<p>Comparaison du ratio aigu / chronique sur {fr(int(ok.sum()), 0)} jours-joueuses.</p>" + image(fig, "Comparaison ACWR"))
    etats = soccermon.vers_etats_vestiaire(sm)
    if len(etats):
        ref = vm.reference_personnelle(etats)
        h.append(f"<p>Forme : {fr(len(etats), 0)} questionnaires complets, score médian {fr(ref['forme'].median(), 0)}/25. "
                 f"Réponses à 3 points ou plus sous la moyenne personnelle : {pct((ref['ecart_points'] <= -3).mean(), 1)}.</p>")
    return "\n".join(h)


# --------------------------------------------------------------------------- main
STYLE = """body{font-family:Inter,-apple-system,system-ui,sans-serif;color:#0B1F3A;max-width:1040px;margin:32px auto;padding:0 20px;line-height:1.55;background:#fff}
h1{font-size:30px;margin-bottom:4px}h2{margin-top:44px;font-size:22px;border-bottom:2px solid #1EC8B0;padding-bottom:4px}h3{margin-top:24px}
img{max-width:100%;margin:8px 0}.sous{color:#4A5B72;margin-top:0}.lead{font-size:17px}.note{color:#4A5B72;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:20px 0}
.kpis div{background:#F5F7FA;border-radius:12px;padding:14px 16px;display:flex;flex-direction:column}
.kpis span{font-size:13px;color:#4A5B72;font-weight:600}.kpis strong{font-size:30px;line-height:1.2}.kpis em{font-size:13px;color:#4A5B72;font-style:normal}
.t{border-collapse:collapse;font-size:14px;margin:8px 0}.t td,.t th{border-bottom:1px solid #D5DDE7;padding:6px 10px;text-align:left}
.t th{background:#F5F7FA}.t td:first-child,.t td:nth-child(2){white-space:nowrap}details{margin:16px 0}summary{cursor:pointer;font-weight:600;color:#0E7C6D}
.cadre{background:#F5F7FA;border-radius:12px;padding:12px 16px;font-size:14px}"""


def main() -> None:
    p = argparse.ArgumentParser(description="Analyse SoccerMon avec les indicateurs Vestiaire")
    p.add_argument("--gps", type=Path)
    p.add_argument("--subjectif", type=Path)
    p.add_argument("--correspondance", type=Path)
    p.add_argument("--sortie", type=Path, default=Path("resultats_vestiaire"))
    p.add_argument("--max-fichiers", type=int, default=None)
    p.add_argument("--coeurs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = p.parse_args()
    if not a.gps and not a.subjectif:
        p.error("indiquer au moins --gps ou --subjectif")
    a.sortie.mkdir(parents=True, exist_ok=True)
    global DOSSIER_FIGURES
    DOSSIER_FIGURES = a.sortie / "figures"
    DOSSIER_FIGURES.mkdir(exist_ok=True)

    expl = []
    for dossier, titre in ((a.gps, "GPS"), (a.subjectif, "Subjectif")):
        if dossier:
            if not dossier.expanduser().exists():
                sys.exit(f"Dossier introuvable : {dossier}")
            explorer(dossier.expanduser(), titre, expl)
    (a.sortie / "exploration.txt").write_text("\n".join(expl), encoding="utf-8")

    sm = None
    if a.subjectif:
        print("Lecture des questionnaires...")
        sm = soccermon.charger_dossier(a.subjectif.expanduser())

    corresp = a.correspondance or (CORRESPONDANCE_R if CORRESPONDANCE_R.exists() else None)
    corps, seances = [], pd.DataFrame(columns=["joueuse", "date"])
    if a.gps:
        print("Analyse GPS...")
        seances = traiter_gps(a.gps.expanduser(), a.sortie / "cache_gps_v2.csv", a.max_fichiers, a.coeurs)
    noms, source_noms = choisir_noms(seances.dropna(subset=["joueuse"]) if len(seances) else seances, corresp, sm)
    noms.sort_values("label").to_csv(a.sortie / "correspondance_joueuses.csv", index=False)

    if a.gps:
        html_gps, joueuses, retenues = section_gps(seances, noms, source_noms)
        joueuses.to_csv(a.sortie / "joueuses_gps.csv", index=False)
        if len(retenues):
            avant = ["label", "equipe", "date"]
            retenues = retenues.assign(date=retenues["date"].dt.strftime("%Y-%m-%d"))
            retenues[avant + [c for c in retenues.columns if c not in avant]].round(2).to_csv(a.sortie / "seances_gps.csv", index=False)
        corps.append(html_gps)
    if sm is not None:
        try:
            corps.append("<h2>7. Charge et forme (questionnaires)</h2>" + section_subjectif(sm, noms))
        except Exception as e:
            corps.append(f"<h2>6. Charge et forme (questionnaires)</h2><p>Partie non calculée ({type(e).__name__} : {e}).</p>")

    essai = f" Essai sur {a.max_fichiers} fichiers répartis entre les équipes et sur toute la période." if a.max_fichiers else ""
    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vestiaire · seuils féminins sur SoccerMon</title><style>{STYLE}</style></head><body>
<h1>Seuils féminins contre seuils masculins</h1>
<p class="sous">Données GPS d'entraînement et de match de deux équipes féminines norvégiennes (SoccerMon, 2020-2021).{essai}</p>
<div class="cadre"><strong>Seuils comparés.</strong> Féminins : course à haute vitesse 19-23 km/h, sprint au-delà de 23 km/h, accélération haute au-delà de 2,7 m/s².
Masculins : 20-25 km/h, 25 km/h, 3 m/s². Les seuils féminins reprennent ceux présentés par SkillCorner le 12 octobre 2026, calibrés sur des matchs.</div>
{''.join(corps)}
<h2>Méthode</h2>
<p class="note">Une ligne gardée par instant GPS (l'accéléromètre à 100 Hz répète chaque instant). Distance intégrée avec le vrai pas de temps ;
trous de plus d'une seconde non comblés ; instants sans satellite et vitesses au-delà de 36 km/h écartés. Vitesse lissée par une médiane sur 0,5 s
pour la vitesse maximale, les sprints et les accélérations. Séances retenues : au moins 10 minutes de signal et 300 m. Joueuses au classement :
au moins 10 séances. Données : Midoglu et al. (2024), <em>Scientific Data</em>, licence CC-BY 4.0. Généré le {pd.Timestamp.now():%d/%m/%Y à %H:%M}
avec vestiaire-metrics {vm.__version__}.</p>
<p class="note">Repères pour le staff, pas un diagnostic ni une prédiction de blessure.</p>
</body></html>"""
    (a.sortie / "rapport_vestiaire.html").write_text(html, encoding="utf-8")
    print(f"-> {a.sortie / 'rapport_vestiaire.html'}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
