"""Figures du README tirées des écrans du prototype Vestiaire (vraies données SoccerMon, anonymisées).

Lit le fichier produit par ``exporter_prototype.py`` et écrit trois images dans
``docs/figures/vestiaire/`` :

1. ``a19_seuils.png``      : le profil d'A-19 sous seuils masculins et féminins (fiche joueuse) ;
2. ``effectif_ratio.png``  : le ratio aigu / chronique de l'effectif la veille d'un match (écran Effectif) ;
3. ``volume_explosivite.png`` : volume et actions explosives en match (écran Effectif).

Usage :
    python exporter_prototype.py          # crée prototype_donnees_reelles.json
    python figures_vestiaire.py           # crée les trois images
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from vestiaire_metrics.charte_jl import C, F, finish, fr, label, new_card, style_axes

SOURCE = ("Données : SoccerMon (Midoglu et al., 2024, CC-BY 4.0), joueuses anonymisées.\n"
          "Seuils féminins : SkillCorner. Calculs : vestiaire-metrics.")


def jour_fr(iso: str) -> str:
    a, m, j = iso.split("-")
    return f"{j}/{m}/{a}"


def profil_a19(d: dict, out: Path) -> None:
    f = d["fiche"]
    dims = [p for p in f["profil_match"] if "percentile_feminin" in p]
    noms = {"Course à haute vitesse": "Course à haute vitesse",
            "Distance de sprint": "Distance de sprint",
            "Nombre de sprints": "Nombre de sprints",
            "Accélérations hautes": "Accélérations hautes",
            "Décélérations hautes": "Décélérations hautes"}
    fig = new_card(f"{f['joueuse']} : une joueuse rapide\nque les seuils masculins cachaient",
                   f"Percentile parmi {f['comparees_a']} joueuses de champ, moyenne par séance\n"
                   f"sur {f['seances_gps']} séances GPS. Gris : seuils masculins. Couleur : seuils féminins.")
    ax = fig.add_axes([0.30, 0.24, 0.60, 0.48])
    style_axes(ax, xgrid=True)
    for i, p in enumerate(reversed(dims)):
        m, fe = p["percentile_masculin"], p["percentile_feminin"]
        accent = p["dimension"] == "Nombre de sprints"
        col = C["rust"] if accent else C["teal"]
        ax.plot([m, fe], [i, i], color=C["compare"], lw=3.5, zorder=1)
        ax.scatter([m], [i], s=160, color=C["compare"], edgecolor=C["bg"], lw=2, zorder=2)
        ax.scatter([fe], [i], s=160, color=col, edgecolor=C["bg"], lw=2, zorder=3)
        gauche, droite = sorted([(m, "m"), (fe, "f")])
        label(ax, gauche[0] - 3, i + 0.22, f"{gauche[0]}e", ha="right", va="bottom", fontsize=13,
              color=C["ink2"] if gauche[1] == "m" else C["ink"])
        label(ax, droite[0] + 3, i + 0.22, f"{droite[0]}e", ha="left", va="bottom", fontsize=13,
              color=C["ink2"] if droite[1] == "m" else C["ink"])
        fig.text(0.07, 0.24 + 0.48 * (i + 0.5) / len(dims), noms[p["dimension"]],
                 fontproperties=F["bold"], fontsize=15, color=C["ink"], va="center")
    ax.axvline(50, color=C["muted"], lw=1.2, ls=(0, (4, 3)), zorder=0)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, len(dims) - 0.4)
    ax.set_yticks([])
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0", "25e", "50e", "75e", "100e"])
    style_axes(ax, xgrid=True)
    ns = next(p for p in dims if p["dimension"] == "Nombre de sprints")
    fig.text(0.07, 0.15, f"Nombre de sprints : du {ns['percentile_masculin']}e au {ns['percentile_feminin']}e percentile. "
            "Ses sprints entre 23 et 25 km/h existent :\nle seuil de 25 km/h les effaçait.",
            ha="left", va="top", linespacing=1.4, fontproperties=F["body"], fontsize=13, color=C["ink2"])
    finish(fig, SOURCE, out)


def ratio_effectif(d: dict, out: Path) -> None:
    lignes = [e for e in d["effectif"] if e["ratio"] is not None]
    actives = [e for e in lignes if e["charge_7j"] > 0]
    sans = [e["joueuse"] for e in lignes if e["charge_7j"] == 0]
    actives.sort(key=lambda e: e["ratio"])
    fig = new_card("Veille de match : une baisse\nde charge, pas un signal d’alerte",
                   f"Ratio charge des 7 derniers jours / 4 semaines précédentes, {d['equipe']},\n"
                   f"{jour_fr(d['jour'])}. Bande : repère 0,8 à 1,3, réglable par le staff.")
    ax = fig.add_axes([0.17, 0.235, 0.73, 0.495])
    ax.axvspan(0.8, 1.3, color=C["grid"], alpha=0.6, zorder=0, lw=0)
    for i, e in enumerate(actives):
        r = e["ratio"]
        accent = r < 0.5
        col = C["rust"] if accent else (C["teal"] if r < 0.8 or r > 1.3 else C["compare"])
        ax.barh(i, r, color=col, height=0.68, zorder=2)
        if accent or r < 0.8:
            label(ax, r + 0.02, i, fr(r, 2), va="center", fontsize=12)
    ax.set_yticks(range(len(actives)))
    ax.set_yticklabels([e["joueuse"] for e in actives])
    ax.set_xlim(0, 1.5)
    ax.set_xticks([0, 0.5, 0.8, 1.0, 1.3])
    ax.set_xticklabels(["0", "0,5", "0,8", "1", "1,3"])
    style_axes(ax, xgrid=True)
    for t in ax.get_yticklabels():
        t.set_fontsize(11)
    med = sorted(e["ratio"] for e in actives)[len(actives) // 2]
    note = (f"Ratio médian de l’équipe : {fr(med, 2)}. Autour de 0,77, la baisse est cohérente avec un affûtage ;\n"
            f"seule la forte baisse (en rouille) mérite une question au staff."
            + (f"\n{', '.join(sans)} : aucune séance déclarée sur 7 jours, à relancer (non représentée)." if sans else ""))
    fig.text(0.07, 0.185, note, ha="left", va="top", linespacing=1.4,
             fontproperties=F["body"], fontsize=12, color=C["ink2"])
    finish(fig, SOURCE, out)


def volume_explosivite(d: dict, out: Path) -> None:
    pts = [p for p in d["nuage"]["points"] if p["seances"] >= 2]
    mx, my = mean(p["distance_m"] for p in pts), mean(p["explosives"] for p in pts)
    plus_explosive = max(pts, key=lambda p: p["explosives"])
    fig = new_card("Courir beaucoup et être explosive :\ndeux qualités différentes",
                   f"Moyenne par match sur les {len(d['nuage']['jours'])} derniers jours de match probables, "
                   f"{len(pts)} joueuses de champ\n(au moins 2 matchs). Seuils féminins.")
    ax = fig.add_axes([0.12, 0.19, 0.78, 0.52])
    style_axes(ax)
    ax.axvline(mx, color=C["muted"], lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.axhline(my, color=C["muted"], lw=1.2, ls=(0, (4, 3)), zorder=1)
    for p in pts:
        accent = p is plus_explosive
        ax.scatter(p["distance_m"], p["explosives"], s=150, zorder=3,
                   color=C["rust"] if accent else C["teal"], edgecolor=C["bg"], lw=2)
    ecarts = sorted(pts, key=lambda p: abs(p["distance_m"] - mx) / 1500 + abs(p["explosives"] - my) / 2, reverse=True)
    for p in ecarts[:5]:
        dy = -0.75 if abs(p["explosives"] - my) < 0.6 else 0.25
        ax.text(p["distance_m"] + 120, p["explosives"] + dy, p["label"], fontproperties=F["bold"],
                fontsize=13, color=C["ink"], zorder=4)
    ax.set_xlim(6000, 12500)
    ax.set_ylim(0, 12)
    ax.set_xticks([6000, 8000, 10000, 12000])
    ax.set_xticklabels([fr(x, 0) + " m" for x in [6000, 8000, 10000, 12000]])
    style_axes(ax)
    ax.set_xlabel("Distance totale par match", fontproperties=F["body"], fontsize=13, color=C["ink2"])
    ax.set_ylabel("Accélérations + décélérations hautes", fontproperties=F["body"], fontsize=13, color=C["ink2"])
    ax.text(mx + 80, 0.3, f"moyenne {fr(mx, 0)} m", fontproperties=F["body"], fontsize=11, color=C["ink2"])
    ax.text(6080, my + 0.2, f"moyenne {fr(my, 1)}", fontproperties=F["body"], fontsize=11, color=C["ink2"])
    finish(fig, SOURCE, out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--donnees", default="prototype_donnees_reelles.json")
    ap.add_argument("--sortie", default="docs/figures/vestiaire")
    a = ap.parse_args()
    d = json.loads(Path(a.donnees).read_text(encoding="utf-8"))
    out = Path(a.sortie)
    out.mkdir(parents=True, exist_ok=True)
    profil_a19(d, out / "a19_seuils.png")
    ratio_effectif(d, out / "effectif_ratio.png")
    volume_explosivite(d, out / "volume_explosivite.png")
    print(f"3 figures écrites dans {out}/")


if __name__ == "__main__":
    main()
