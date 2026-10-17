# Lancer le test SoccerMon sur ton Mac

Compte 10 minutes la première fois. Tout se passe dans l'app **Terminal** (Applications > Utilitaires > Terminal).

## 1. Installer (une seule fois)

1. Décompresse `vestiaire-metrics.zip` dans ton dossier Documents. Tu obtiens `Documents/vestiaire-metrics`.
2. Dans le Terminal, copie-colle ces lignes une par une :

```bash
cd ~/Documents/vestiaire-metrics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

La dernière commande doit afficher « 13 passed ». Si `python3` est inconnu, macOS propose d'installer les outils de développement : accepte, puis recommence.

## 2. Premier essai rapide (20 fichiers)

```bash
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS --max-fichiers 20
open resultats_vestiaire/rapport_vestiaire.html
```

Si le nom d'un dossier contient des espaces, mets le chemin entre guillemets : `--gps "~/Desktop/Soccer Mon GPS"`.
Astuce : tu peux aussi glisser le dossier depuis le Finder dans le Terminal, le chemin s'écrit tout seul.

## 3. Analyse complète

```bash
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS
```

Si tu as aussi le dossier des questionnaires (données « subjective ») :

```bash
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS --subjectif ~/Desktop/<dossier_subjectif>
```

Le script affiche sa progression. Selon la taille des données, l'analyse complète peut prendre plusieurs minutes.

## 4. Ce qu'il faut m'envoyer

Dans le dossier `resultats_vestiaire` :

- `exploration.txt` : toujours, c'est ce qui me permet de corriger le code si un format n'est pas reconnu ;
- `rapport_vestiaire.html` (ou des captures d'écran du rapport) ;
- `detection_gps.csv` si le rapport dit « aucune séance exploitable ».

`seances_gps.csv` contient une ligne par joueuse et par séance : tu peux l'ouvrir dans Excel ou Numbers.

## La prochaine fois

```bash
cd ~/Documents/vestiaire-metrics
source .venv/bin/activate
python analyser_soccermon.py --gps ~/Desktop/SoccerMon_GPS
```
