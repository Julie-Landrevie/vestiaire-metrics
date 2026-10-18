"""Analyse des données SoccerMon (ou de tout dossier GPS) sur ton propre ordinateur.

Utilisation, depuis le dossier vestiaire-metrics :

    python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS
    python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS --subjectif ~/Desktop/SoccerMon_subjective

Le script crée un dossier « resultats_vestiaire » avec :
- exploration.txt : ce qu'il a trouvé dans les dossiers (à m'envoyer en premier si quelque chose bloque) ;
- detection_gps.csv : pour chaque fichier, les colonnes et unités qu'il a reconnues ;
- seances_gps.csv : une ligne par joueuse et par séance, seuils féminins et masculins côte à côte ;
- rapport_vestiaire.html : le rapport avec les graphiques, à ouvrir dans un navigateur.
"""

from __future__ import annotations

import argparse
import base64
import io
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

BLEU_NUIT, TURQUOISE, ORANGE, GRIS = "#0B1F3A", "#1EC8B0", "#A35F00", "#9AA8B8"
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 12})


def fr(x, d=1):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def image(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return '<img alt="graphique" src="data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode() + '">'


def explorer(dossier: Path, titre: str, lignes: list[str]) -> None:
    fichiers = [p for p in dossier.rglob("*") if p.is_file()]
    lignes += [f"=== {titre} : {dossier}", f"{len(fichiers)} fichiers, {sum(p.stat().st_size for p in fichiers) / 1e6:,.0f} Mo"]
    lignes.append("Extensions : " + ", ".join(f"{e or '(aucune)'} x{n}" for e, n in Counter(p.suffix.lower() for p in fichiers).most_common()))
    sous = sorted({str(p.parent.relative_to(dossier)) for p in fichiers})
    lignes.append(f"Sous-dossiers ({len(sous)}) : " + ", ".join(sous[:15]) + (" ..." if len(sous) > 15 else ""))
    for p in gps.lister_fichiers(dossier)[:3]:
        lignes.append(f"\n--- Exemple : {p.relative_to(dossier)}")
        try:
            df = gps.lire(p, nrows=5)
            lignes.append("Colonnes : " + ", ".join(f"{c} ({t})" for c, t in df.dtypes.astype(str).items()))
            lignes.append(df.to_string(max_cols=12)[:1500])
        except Exception as e:  # on note l'erreur et on continue
            lignes.append(f"Lecture impossible : {e}")
    lignes.append("")


def analyser_gps(dossier: Path, max_fichiers: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    fichiers = gps.lister_fichiers(dossier)[:max_fichiers]
    resultats, detections, debut = [], [], time.time()
    for i, p in enumerate(fichiers, 1):
        try:
            lignes, info = gps.analyser_fichier(p)
        except Exception as e:
            lignes, info = [], {"fichier": str(p), "probleme": f"erreur : {e}"}
        resultats += lignes
        detections.append(info)
        if i % 10 == 0 or i == len(fichiers):
            print(f"  {i}/{len(fichiers)} fichiers ({time.time() - debut:.0f} s)")
    return pd.DataFrame(resultats), pd.DataFrame(detections)


def section_gps(s: pd.DataFrame) -> str:
    if s.empty:
        return "<p><strong>Aucune séance GPS exploitable.</strong> Regarder exploration.txt et detection_gps.csv.</p>"
    n_s, n_j = len(s), s["joueuse"].nunique()
    f, m = "__feminins", "__masculins"
    zero_f = (s["nb_sprints" + f] == 0).mean() * 100
    zero_m = (s["nb_sprints" + m] == 0).mean() * 100
    html = [f"<p>{n_s} séances de plus de 10 minutes, {n_j} joueuses, durée médiane {fr(s['duree_min'].median(), 0)} min, "
            f"distance médiane {fr(s['distance_m' + f].median() / 1000)} km.</p>"]
    html.append(f"<p class='chiffre'>Séances sans aucun sprint : <strong>{fr(zero_m, 0)} %</strong> avec les seuils masculins, "
                f"<strong>{fr(zero_f, 0)} %</strong> avec les seuils féminins.</p>")

    tab = pd.DataFrame({
        "Indicateur (médiane par séance)": ["Distance sprint (m)", "Nombre de sprints", "Distance HSR (m)",
                                            "Accélérations hautes", "Décélérations hautes"],
        "Seuils masculins": [s[c + m].median() for c in ["distance_sprint_m", "nb_sprints", "distance_hsr_m", "nb_acc_hautes", "nb_dec_hautes"]],
        "Seuils féminins": [s[c + f].median() for c in ["distance_sprint_m", "nb_sprints", "distance_hsr_m", "nb_acc_hautes", "nb_dec_hautes"]],
    })
    html.append(tab.to_html(index=False, float_format=lambda x: fr(x, 1), classes="t"))

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, col, titre in [(axes[0], "distance_sprint_m", "Distance sprint par séance (m)"), (axes[1], "nb_acc_hautes", "Accélérations hautes par séance")]:
        hi = np.nanpercentile(s[col + f], 99)
        bins = np.linspace(0, max(hi, 1), 30)
        ax.hist(s[col + m].clip(upper=hi), bins=bins, color=GRIS, alpha=.8, label="seuils masculins")
        ax.hist(s[col + f].clip(upper=hi), bins=bins, color=TURQUOISE, alpha=.7, label="seuils féminins")
        ax.set_title(titre)
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle("Avec les seuils masculins, les séances s'entassent près de zéro", fontweight="bold", y=1.03)
    html.append(image(fig))

    par_j = s.groupby("joueuse")[["nb_sprints" + m, "nb_sprints" + f]].mean().sort_values("nb_sprints" + f)
    fig, ax = plt.subplots(figsize=(9, max(3, .28 * len(par_j))))
    y = np.arange(len(par_j))
    ax.barh(y - .2, par_j["nb_sprints" + m], .4, color=GRIS, label="seuils masculins")
    ax.barh(y + .2, par_j["nb_sprints" + f], .4, color=BLEU_NUIT, label="seuils féminins")
    ax.set_yticks(y, par_j.index, fontsize=8)
    ax.set_title("Sprints par séance, moyenne par joueuse")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    html.append(image(fig))

    # rang des joueuses : est-ce que le classement change ?
    rangs = par_j.rank(ascending=False)
    corr = rangs.iloc[:, 0].corr(rangs.iloc[:, 1])  # Pearson sur les rangs = Spearman, sans scipy
    html.append(f"<p>Corrélation de rang (Spearman) entre les deux classements de joueuses : <strong>{fr(corr, 2)}</strong>. "
                "Plus elle est basse, plus le choix des seuils change la hiérarchie.</p>")
    return "\n".join(html)


def section_subjectif(dossier: Path) -> str:
    sm = soccermon.charger_dossier(dossier)
    html = [f"<p>Indicateurs trouvés : {', '.join(c for c in sm.columns if c not in ('date', 'joueuse'))}.</p>"]
    cols = {c.lower(): c for c in sm.columns}
    c_rpe = next((cols[k] for k in ("rpe",) if k in cols), None)
    c_duree = next((cols[k] for k in ("duration", "duree", "session_duration") if k in cols), None)
    if c_rpe and c_duree:
        seances = soccermon.vers_seances_vestiaire(sm, c_rpe, c_duree)
        q = vm.charge_quotidienne(seances)
        html.append(f"<p>{len(seances)} séances notées, {q.shape[1]} joueuses, du {q.index.min():%d/%m/%Y} au {q.index.max():%d/%m/%Y}.</p>")
        for nom_fourni, methode in (("acwr", "couple"),):
            if nom_fourni in cols:
                fourni = sm.pivot_table(index="date", columns="joueuse", values=cols[nom_fourni])
                calc = vm.ratio_aigu_chronique(q, methode)
                a, b = calc.stack(), fourni.stack()
                commun = a.index.intersection(b.index)
                a, b = a[commun], b[commun]
                ok = a.notna() & b.notna() & np.isfinite(a) & np.isfinite(b)
                if ok.sum() > 10:
                    fig, ax = plt.subplots(figsize=(4.8, 4.2))
                    ax.scatter(b[ok], a[ok], s=4, alpha=.3, color=BLEU_NUIT)
                    lim = np.nanpercentile(np.r_[a[ok], b[ok]], 99.5)
                    ax.plot([0, lim], [0, lim], color=ORANGE, lw=1)
                    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
                    ax.set_xlabel("ACWR fourni par SoccerMon"); ax.set_ylabel("Ratio calculé par Vestiaire")
                    ax.set_title(f"Corrélation : {fr(a[ok].corr(b[ok]), 2)}")
                    html.append(f"<p>Comparaison sur {ok.sum()} jours-joueuses (méthode {methode}).</p>" + image(fig))
        if "daily_load" in cols:
            fourni = sm.pivot_table(index="date", columns="joueuse", values=cols["daily_load"]).stack()
            calc = q.stack()
            commun = calc.index.intersection(fourni.index)
            ecart = (calc[commun] - fourni[commun]).abs()
            html.append(f"<p>Charge quotidienne : écart médian avec SoccerMon de {fr(ecart.median(), 1)} "
                        f"(identique à 1 près dans {fr((ecart <= 1).mean() * 100, 0)} % des cas).</p>")
    else:
        html.append("<p>Colonnes RPE ou durée non reconnues : m'envoyer exploration.txt.</p>")

    etats = soccermon.vers_etats_vestiaire(sm)
    if len(etats):
        ref = vm.reference_personnelle(etats)
        bas = (ref["ecart_points"] <= -3).mean() * 100
        html.append(f"<p>Forme : {len(etats)} questionnaires complets. Score médian {fr(ref['forme'].median(), 0)}/25. "
                    f"Jours « 3 points sous sa moyenne » : {fr(bas, 1)} % des réponses.</p>")
        ex = ref.groupby("joueuse")["forme"].count().idxmax()
        d = ref[ref.joueuse == ex].set_index("date").tail(120)
        fig, ax = plt.subplots(figsize=(10, 3.2))
        ax.plot(d.index, d["moyenne_perso"], color=GRIS, ls="--", label="sa moyenne (28 j précédents)")
        ax.plot(d.index, d["forme"], color=BLEU_NUIT, lw=1, label="forme du jour")
        b = d[d["ecart_points"] <= -3]
        ax.scatter(b.index, b["forme"], color=ORANGE, s=20, zorder=3, label="3 points ou plus sous sa moyenne")
        ax.set_title(f"Joueuse {ex} : 120 derniers jours de réponses")
        ax.legend(frameon=False, fontsize=8, ncol=3)
        html.append(image(fig))
    return "\n".join(html)


def main() -> None:
    p = argparse.ArgumentParser(description="Analyse SoccerMon avec les indicateurs Vestiaire")
    p.add_argument("--gps", type=Path, help="dossier des données GPS")
    p.add_argument("--subjectif", type=Path, help="dossier des données subjectives (questionnaires)")
    p.add_argument("--sortie", type=Path, default=Path("resultats_vestiaire"))
    p.add_argument("--max-fichiers", type=int, default=None, help="pour un premier essai rapide, ex. 20")
    a = p.parse_args()
    if not a.gps and not a.subjectif:
        p.error("indiquer au moins --gps ou --subjectif")
    a.sortie.mkdir(parents=True, exist_ok=True)

    expl, corps = [], []
    for dossier, titre in ((a.gps, "GPS"), (a.subjectif, "Subjectif")):
        if dossier:
            dossier = dossier.expanduser()
            if not dossier.exists():
                sys.exit(f"Dossier introuvable : {dossier}")
            print(f"Exploration du dossier {titre}...")
            explorer(dossier, titre, expl)
    (a.sortie / "exploration.txt").write_text("\n".join(expl), encoding="utf-8")
    print(f"-> {a.sortie / 'exploration.txt'}")

    if a.gps:
        print("Analyse GPS...")
        seances, detections = analyser_gps(a.gps.expanduser(), a.max_fichiers)
        seances.to_csv(a.sortie / "seances_gps.csv", index=False)
        detections.to_csv(a.sortie / "detection_gps.csv", index=False)
        corps.append("<h2>GPS : seuils féminins contre seuils masculins</h2>" + section_gps(seances))
        if not detections.empty:
            resume = detections.drop(columns=["fichier", "lignes"], errors="ignore").fillna("—").astype(str).value_counts(dropna=False).head(8).reset_index()
            corps.append("<h3>Ce que le script a reconnu dans les fichiers</h3>" + resume.to_html(index=False, classes="t"))
    if a.subjectif:
        print("Analyse des questionnaires...")
        try:
            corps.append("<h2>Charge et forme</h2>" + section_subjectif(a.subjectif.expanduser()))
        except Exception as e:
            corps.append(f"<h2>Charge et forme</h2><p>Erreur : {e}. M'envoyer exploration.txt.</p>")

    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Vestiaire · test SoccerMon</title>
<style>body{{font-family:Inter,system-ui,sans-serif;color:#0B1F3A;max-width:1000px;margin:32px auto;padding:0 16px;line-height:1.5}}
h1{{font-size:28px}}h2{{margin-top:36px;border-bottom:2px solid #1EC8B0;padding-bottom:4px}}img{{max-width:100%}}
.t{{border-collapse:collapse;font-size:14px}}.t td,.t th{{border-bottom:1px solid #D5DDE7;padding:6px 10px;text-align:left}}
.chiffre{{font-size:18px;background:#F5F7FA;padding:12px 16px;border-radius:10px}}</style></head><body>
<h1>Vestiaire · test sur SoccerMon</h1>
<p>Généré le {pd.Timestamp.now():%d/%m/%Y à %H:%M} avec vestiaire-metrics {vm.__version__}. Données : SoccerMon (Midoglu et al., 2024, CC-BY 4.0).
Seuils féminins : sprint au-delà de 23 km/h, HSR 19-23 km/h, accélération haute au-delà de 2,7 m/s². Seuils masculins : 25 km/h, 20-25 km/h, 3 m/s².</p>
{''.join(corps)}
<p style="color:#4A5B72;font-size:13px;margin-top:40px">Repères pour le staff, pas un diagnostic ni une prédiction de blessure.</p>
</body></html>"""
    (a.sortie / "rapport_vestiaire.html").write_text(html, encoding="utf-8")
    print(f"-> {a.sortie / 'rapport_vestiaire.html'}  (à ouvrir dans un navigateur)")


if __name__ == "__main__":
    main()
