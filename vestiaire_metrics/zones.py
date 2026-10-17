"""Zones de vitesse et d'accélération, seuils féminins par défaut.

Seuils féminins présentés par SkillCorner (webinaire du 12 octobre 2026) :
course 13-19 km/h, HSR 19-23 km/h, sprint au-delà de 23 km/h,
accélération moyenne 1,4-2,7 m/s², haute au-delà de 2,7 m/s².
Les seuils masculins habituels restent disponibles pour comparaison.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Seuils:
    course: float
    hsr: float
    sprint: float
    acc_moyenne: float
    acc_haute: float


FEMININS = Seuils(course=13, hsr=19, sprint=23, acc_moyenne=1.4, acc_haute=2.7)
MASCULINS = Seuils(course=15, hsr=20, sprint=25, acc_moyenne=1.5, acc_haute=3.0)


def zone_vitesse(v_kmh, seuils: Seuils = FEMININS):
    """Nom de la zone pour une ou plusieurs vitesses en km/h."""
    v = np.asarray(v_kmh, dtype=float)
    bords = [seuils.course, seuils.hsr, seuils.sprint]
    noms = np.array(["marche_trot", "course", "hsr", "sprint"])
    return noms[np.digitize(v, bords, right=False)]


def resume_gps(trace: pd.DataFrame, seuils: Seuils = FEMININS, hz: float = 10.0,
               duree_min_effort_s: float = 1.0) -> dict:
    """Résumé d'une trace GPS d'une joueuse (colonne ``vitesse_kmh``, échantillonnée à ``hz``).

    Renvoie distance totale, distance par zone, nombre de sprints, accélérations et
    décélérations hautes (effort compté s'il dure au moins ``duree_min_effort_s``),
    vitesse de pointe.
    """
    v = trace["vitesse_kmh"].to_numpy(dtype=float)
    dt = 1.0 / hz
    dist = v / 3.6 * dt
    zones = zone_vitesse(v, seuils)
    acc = np.gradient(v / 3.6, dt)
    n_min = max(1, int(round(duree_min_effort_s * hz)))

    def efforts(masque: np.ndarray) -> int:
        n, run = 0, 0
        for m in masque:
            run = run + 1 if m else 0
            if run == n_min:
                n += 1
        return n

    return {
        "distance_m": dist.sum(),
        **{f"distance_{z}_m": dist[zones == z].sum() for z in ["course", "hsr", "sprint"]},
        "nb_sprints": efforts(v >= seuils.sprint),
        "nb_acc_hautes": efforts(acc >= seuils.acc_haute),
        "nb_dec_hautes": efforts(acc <= -seuils.acc_haute),
        "vitesse_pointe_kmh": v.max() if len(v) else np.nan,
    }
