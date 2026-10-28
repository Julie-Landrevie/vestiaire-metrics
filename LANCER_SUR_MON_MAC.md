# Lancer l'analyse SoccerMon sur ton Mac

Le dossier `vestiaire-metrics` et les données `SoccerMon_GPS` sont sur le bureau.

## Mettre à jour le code (après chaque nouveau zip)

Place le nouveau `vestiaire-metrics.zip` sur le bureau, à la place de l'ancien, puis :

```bash
cd ~/Desktop && unzip -oq vestiaire-metrics.zip
cd ~/Desktop/vestiaire-metrics && source .venv/bin/activate
pip install -q -r requirements.txt && pip install -q -e .
pytest -q
```

`pytest` doit afficher « 19 passed ».

## Lancer l'analyse

Essai rapide sur 300 fichiers (une à deux minutes) :

```bash
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS --max-fichiers 300
open resultats_vestiaire/rapport_vestiaire.html
```

Analyse complète (environ 10 000 fichiers, compter plusieurs dizaines de minutes) :

```bash
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS
open resultats_vestiaire/rapport_vestiaire.html
```

Elle peut être arrêtée avec Ctrl + C et relancée : les fichiers déjà lus ne sont pas relus.

## Noms des joueuses

Le rapport utilise les noms A-01, B-03… du projet R. Si le fichier
`~/Desktop/Projet Suivi Charge Féminin/outputs/tables/correspondance_joueuses.csv` existe, il est
repris tel quel. Sinon, ajoute le dossier des questionnaires pour obtenir la même numérotation :

```bash
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS --subjectif ~/Desktop/<dossier_subjectif>
```

## Ce qu'il faut m'envoyer

Dans `vestiaire-metrics/resultats_vestiaire` : des captures du rapport, `exploration.txt`, et en cas
d'erreur les dernières lignes affichées dans le Terminal.

## Exporter les vraies données pour le prototype

Après une analyse GPS complète :

```bash
python exporter_prototype.py
```

Le script trouve seul les séances GPS, les questionnaires et les noms du projet R sur le bureau, choisit un jour
et produit `prototype_donnees_reelles.json` (quelques Ko) pour l'écran Effectif et la fiche d'A-19.
