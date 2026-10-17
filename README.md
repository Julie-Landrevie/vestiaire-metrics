# vestiaire-metrics

Les indicateurs de **Vestiaire**, l'application de suivi pour les staffs de football féminin, en Python.

Ce module calcule ce que le prototype affiche :

| Indicateur | Fonction | Écran du prototype |
| --- | --- | --- |
| Charge d'une séance (note × durée, sRPE) | `srpe`, `charge_quotidienne` | Séances, Ma semaine |
| Ratio aigu / chronique (découplé, couplé, EWMA) | `ratio_aigu_chronique` | Effectif, Fiche joueuse |
| Monotonie et contrainte | `monotonie`, `contrainte` | Fiche joueuse |
| Forme du jour sur 25 et écart à la moyenne personnelle | `score_forme`, `reference_personnelle` | Mon état du jour, Effectif |
| Statut du jour et phrase « Pourquoi » | `statut_du_jour` | Effectif du jour |
| Zones de vitesse et d'accélération féminines | `zone_vitesse`, `resume_gps` | Réglages, Profil match |

Les seuils de vitesse féminins par défaut (course 13-19 km/h, HSR 19-23 km/h, sprint au-delà de 23 km/h, accélération haute au-delà de 2,7 m/s²) reprennent les bandes présentées par SkillCorner en octobre 2026. Les seuils masculins restent disponibles pour comparer.

## Installation

```bash
git clone <ce dépôt>
cd vestiaire-metrics
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[notebook,test]"
```

## Utilisation rapide

```python
import vestiaire_metrics as vm
from vestiaire_metrics.demo import generer

seances, etats, douleurs = generer()          # effectif fictif du prototype
quotidien = vm.charge_quotidienne(seances)
charge = vm.resume_charge(quotidien)          # charge 7 j, évolution, ratio, monotonie
ref = vm.reference_personnelle(etats)         # forme et moyenne personnelle
```

Le carnet `notebooks/01_indicateurs_vestiaire.ipynb` montre tout le calcul, avec les graphiques des fiches joueuses.

## Valider sur SoccerMon

[SoccerMon](https://osf.io/uryz9/) (Midoglu et al., *Scientific Data*, 2024, licence CC-BY 4.0) contient les données de bien-être, de charge et de GPS de deux équipes féminines norvégiennes en 2020 et 2021. Après téléchargement, indiquer le dossier des données subjectives dans la partie 2 du carnet. Le module `soccermon` lit les fichiers CSV « une colonne par joueuse » et les convertit au format Vestiaire.

## Tests

```bash
pytest
```

## Ce que ces indicateurs ne sont pas

Des repères pour aider le staff à décider. Ce ne sont ni un diagnostic ni une prédiction de blessure, et Vestiaire ne les présente jamais ainsi. Tous les seuils sont réglables par le club.

## Références

- Foster C. et al. (2001). A new approach to monitoring exercise training. *J Strength Cond Res*.
- Foster C. (1998). Monitoring training in athletes with reference to overtraining syndrome. *Med Sci Sports Exerc*.
- Williams S. et al. (2017). Better way to determine the acute:chronic workload ratio? *Br J Sports Med*.
- Midoglu C. et al. (2024). A large-scale multivariate soccer athlete health, performance, and position monitoring dataset. *Scientific Data*.

Auteure : Julie Landrevie.
