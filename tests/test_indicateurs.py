import numpy as np
import pandas as pd
import pytest

from vestiaire_metrics import (FEMININS, MASCULINS, Reperes, charge_quotidienne, contrainte,
                               monotonie, ratio_aigu_chronique, reference_personnelle,
                               resume_charge, resume_gps, srpe, statut_du_jour, zone_vitesse)
from vestiaire_metrics.demo import generer


def seances_constantes(nb_jours=42, charge_par_jour=(300, 0)):
    jours = pd.date_range("2026-09-01", periods=nb_jours, freq="D")
    lignes = []
    for i, d in enumerate(jours):
        c = charge_par_jour[i % len(charge_par_jour)]
        if c:
            lignes.append({"joueuse": "A", "date": d, "rpe": 5, "duree_min": c / 5})
    return pd.DataFrame(lignes)


def test_srpe_multiplie_rpe_et_duree():
    df = srpe(pd.DataFrame({"joueuse": ["A"], "date": ["2026-10-01"], "rpe": [7], "duree_min": [90]}))
    assert df["charge"].iloc[0] == 630


def test_srpe_refuse_rpe_hors_echelle():
    with pytest.raises(ValueError):
        srpe(pd.DataFrame({"joueuse": ["A"], "date": ["2026-10-01"], "rpe": [11], "duree_min": [60]}))


def test_jours_sans_seance_a_zero():
    q = charge_quotidienne(seances_constantes(10, (300, 0)))
    assert len(q) == 9  # du premier au dernier jour avec séance
    assert q["A"].iloc[1] == 0


def test_ratio_vaut_1_quand_la_charge_est_stable():
    q = charge_quotidienne(seances_constantes(70, (300, 0, 400, 0, 200, 600, 0)))
    for methode in ("decouple", "couple", "ewma"):
        # l'EWMA oscille selon le jour de la semaine : on regarde la moyenne sur 7 jours
        r = ratio_aigu_chronique(q, methode=methode).iloc[-7:, 0].mean()
        assert r == pytest.approx(1.0, abs=0.05), methode


def test_ratio_monte_apres_une_hausse_de_charge():
    s = seances_constantes(63, (300, 0, 400, 0, 200, 600, 0))
    hausse = s[s["date"] >= s["date"].max() - pd.Timedelta(days=6)].copy()
    s.loc[hausse.index, "duree_min"] *= 1.5
    q = charge_quotidienne(s)
    assert ratio_aigu_chronique(q, "decouple").iloc[-1, 0] == pytest.approx(1.5, abs=0.05)


def test_ratio_manquant_sans_historique():
    q = charge_quotidienne(seances_constantes(20))
    assert ratio_aigu_chronique(q).iloc[-1].isna().all()


def test_monotonie_et_contrainte():
    q = charge_quotidienne(seances_constantes(14, (300, 0)))
    m = monotonie(q).iloc[-1, 0]
    assert m == pytest.approx(q["A"].tail(7).mean() / q["A"].tail(7).std(ddof=0))
    assert contrainte(q).iloc[-1, 0] == pytest.approx(q["A"].tail(7).sum() * m)


def test_monotonie_indefinie_si_charge_identique_tous_les_jours():
    q = charge_quotidienne(seances_constantes(14, (300,)))
    assert np.isnan(monotonie(q).iloc[-1, 0])


def test_reference_personnelle_exclut_le_jour_meme():
    jours = pd.date_range("2026-09-01", periods=10)
    etats = pd.DataFrame({"joueuse": "A", "date": jours, "fatigue": 4, "sommeil": 4,
                          "courbatures": 4, "stress": 4, "humeur": 4})
    etats.loc[9, ["fatigue", "sommeil", "courbatures"]] = 1
    ref = reference_personnelle(etats)
    dernier = ref.iloc[-1]
    assert dernier["forme"] == 11
    assert dernier["moyenne_perso"] == 20
    assert dernier["ecart_points"] == -9


def test_reference_en_construction_sous_7_reponses():
    jours = pd.date_range("2026-09-01", periods=5)
    etats = pd.DataFrame({"joueuse": "A", "date": jours, "fatigue": 4, "sommeil": 4,
                          "courbatures": 4, "stress": 4, "humeur": 4})
    assert reference_personnelle(etats)["moyenne_perso"].isna().all()


def test_zones_feminines_et_masculines():
    assert list(zone_vitesse([12, 13, 19, 22.9, 23, 24])) == ["marche_trot", "course", "hsr", "hsr", "sprint", "sprint"]
    assert zone_vitesse(24, MASCULINS) == "hsr"


def test_un_sprint_a_24_kmh_compte_en_seuils_feminins_pas_masculins():
    v = np.r_[np.full(50, 10.0), np.full(30, 24.0), np.full(50, 10.0)]
    r = resume_gps(pd.DataFrame({"vitesse_kmh": v}), FEMININS, hz=10)
    assert r["nb_sprints"] == 1
    assert r["distance_sprint_m"] == pytest.approx(30 * 24 / 3.6 / 10)
    r_m = resume_gps(pd.DataFrame({"vitesse_kmh": v}), MASCULINS, hz=10)
    assert r_m["nb_sprints"] == 0
    assert r_m["distance_sprint_m"] == 0


def test_statut_du_jour_sur_les_donnees_de_demo():
    seances, etats, douleurs = generer()
    q = charge_quotidienne(seances)
    charge = resume_charge(q)
    ref = reference_personnelle(etats)
    dernier_jour = q.index.max()
    forme = (ref[ref["date"] == dernier_jour].set_index("joueuse")[["forme", "moyenne_perso"]]
             .reindex(charge.index))
    st = statut_du_jour(charge, forme, douleurs, Reperes())
    assert st.loc["Camille D.", "statut"] == "alerte"
    assert st.loc["Inès B.", "statut"] == "a_surveiller"
    assert "ratio" in st.loc["Inès B.", "pourquoi"]
    assert st.loc["Jade T.", "pourquoi"] == "État du jour pas encore reçu"
    assert st.iloc[0]["statut"] == "alerte"  # tri : alertes en premier


def test_statut_sans_seance_declaree_et_baisse_de_charge():
    charge = pd.DataFrame({"charge_7j": [0.0, 2600.0, 1080.0], "ratio": [0.0, 0.77, 0.31],
                           "evolution_pct": [-100.0, -23.0, -69.0]},
                          index=pd.Index(["A-05", "A-19", "A-12"], name="joueuse"))
    forme = pd.DataFrame({"forme": [15, 16, 14], "moyenne_perso": [14.9, 16.4, 15.2]}, index=charge.index)
    st = statut_du_jour(charge, forme, None, Reperes())
    assert st.loc["A-05", "statut"] == "sans_donnees"
    assert st.loc["A-05", "pourquoi"].startswith("Aucune séance déclarée")
    assert st.loc["A-19", "statut"] == "a_surveiller"
    assert st.loc["A-19", "pourquoi"] == "Charge en baisse : ratio 0,77 (2\u202f600 sur 7 jours)"
    assert st.loc["A-12", "pourquoi"].startswith("Forte baisse de charge")
    assert list(st["statut"]) == ["a_surveiller", "a_surveiller", "sans_donnees"]
