import numpy as np
import pandas as pd
import pytest

from vestiaire_metrics import gps


def trace_soccermon(vitesses_ms, repetitions=10, lat=63.4):
    sec = 17 * 3600 + np.arange(len(vitesses_ms)) * 0.1
    t = [f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:04.1f}" for s in sec]
    return pd.DataFrame({"time": np.repeat(t, repetitions), "speed": np.repeat(vitesses_ms, repetitions),
                         "lat": np.repeat(np.full(len(sec), lat) if np.isscalar(lat) else lat, repetitions)})


def test_doublons_de_l_accelerometre_retires():
    r = gps.resumer_trace(trace_soccermon(np.full(6000, 5.0)), "speed", "time", "lat")
    assert r["distance_m"] == pytest.approx(5.0 * 600, rel=0.01)  # 10 min à 5 m/s, pas 10 fois plus
    assert r["lignes_par_instant"] == 10
    assert r["frequence_hz"] == 10


def test_sprint_a_24_kmh_feminin_pas_masculin():
    v = np.r_[np.full(3000, 2.0), np.full(30, 24 / 3.6), np.full(3000, 2.0)]
    r = gps.resumer_trace(trace_soccermon(v), "speed", "time", "lat")
    assert r["nb_sprints__feminins"] == 1 and r["nb_sprints__masculins"] == 0
    assert r["distance_sprint_m__feminins"] == pytest.approx(30 * 0.1 * 24 / 3.6, rel=0.05)


def test_instants_sans_satellite_ignores():
    lat = np.full(6000, 63.4)
    lat[:3000] = 0
    r = gps.resumer_trace(trace_soccermon(np.full(6000, 5.0), lat=lat), "speed", "time", "lat")
    assert r["distance_m"] == pytest.approx(5.0 * 300, rel=0.01)


def test_noms_lisibles_par_ordre_d_arrivee():
    pj = pd.DataFrame({"joueuse": ["TeamA-zzz", "TeamA-aaa", "TeamB-xxx"],
                       "premier_jour": pd.to_datetime(["2020-06-01", "2020-07-01", "2020-06-05"])})
    n = gps.noms_lisibles(pj).set_index("identifiant_soccermon")
    assert n.loc["TeamA-zzz", "label"] == "A-01" and n.loc["TeamA-aaa", "label"] == "A-02"
    assert n.loc["TeamB-xxx", "label"] == "B-01" and n.loc["TeamB-xxx", "equipe"] == "Équipe B"
