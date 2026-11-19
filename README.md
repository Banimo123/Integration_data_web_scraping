# Module de scraping Daraz

## Finalisation et audit des galeries

Utiliser le Python de `.venv`. Le brut `output/produits_daraz.csv` et sa copie
`output/raw/produits_daraz_brut.csv` sont conservés sans nettoyage ni imputation.
L'empreinte figure dans `output/validation/integrite_brut.json`.

```powershell
.\.venv\Scripts\python.exe check_daraz.py
.\.venv\Scripts\python.exe validate_daraz.py --check-only
.\.venv\Scripts\python.exe audit_daraz.py output/validation/complet
.\.venv\Scripts\python.exe download_images_daraz.py --sample --workers 4
.\.venv\Scripts\python.exe download_images_daraz.py --workers 4
.\.venv\Scripts\python.exe finalise_daraz.py
.\.venv\Scripts\python.exe -m unittest discover -v
```

La validation `--check-only` est le mode adapté au CSV complet existant.
Les modes `--stage` conservent leur échantillon dans leur dossier de validation
et ne remplacent plus le CSV principal.

Le téléchargement conserve les octets et le format source, vérifie tous les pixels,
écrit d'abord un fichier `.part`, puis publie l'image validée. Les fichiers valides
sont ignorés à la reprise ; les fichiers incomplets sont retentés. Le journal
`output/validation/download_images.jsonl` conserve chaque tentative et son URL.
Les images sont associées à l'ID et à l'index dans `liens_images`.

`check_images_daraz.py` produit `images_audit.json` et des planches dérivées
dans `output/validation/planches/`, sans modifier les originaux.
`finalise_daraz.py` régénère les quatre rapports et le bilan JSON final à partir
des fichiers présents. La revue visuelle est consignée séparément dans
`revue_visuelle.json` ; les heuristiques techniques seules ne certifient pas
l'absence d'images d'autres produits. Les images ambiguës restent conservées.

Les résultats des autres plateformes ne sont pas présents dans ce workspace.
La méthode et le contrat de fusion sont décrits dans `audit_qualite_daraz.md`.

Ce dossier correspond à ta partie **Daraz** du projet de groupe.

## Volume détecté

Le fichier commun contient **400 produits**.

Parmi eux, **320 fiches Daraz avec une URL HTTP/HTTPS** sont disponibles.

Répartition observée :

- `www.daraz.com.bd` : 12
- `www.daraz.com.np` : 2
- `www.daraz.lk` : 52
- `www.daraz.pk` : 254

Les produits sans URL Daraz ne sont pas scrapés.

## Structure du projet

```text
daraz_scraping_groupe/
├── input/
│   └── scp_groupe_400.xlsx
├── output/
│   ├── produits_daraz.csv
│   └── images/
│       └── daraz/{id}/image_N.ext
├── scrapers/
│   ├── __init__.py
│   ├── daraz_scraper.py
│   └── playwright_manager.py
├── main_daraz.py
├── download_images_daraz.py
├── check_daraz.py
├── utils.py
├── requirements.txt
└── README.md
```

## Méthode choisie

La logique est volontairement proche de l'exemple du professeur :

1. `requests` télécharge d'abord la fiche.
2. `BeautifulSoup` analyse le HTML.
3. Les données structurées JSON-LD sont utilisées en priorité.
4. Si le titre, le prix ou les images ne sont pas accessibles, Playwright charge la page.
5. Le résultat est écrit immédiatement dans `output/produits_daraz.csv`.
6. Les images sont téléchargées dans une étape séparée.

## Installation

Dans le dossier du projet :

```bash
python -m venv .venv
```

Windows :

```bash
.venv\Scripts\activate
```

Puis :

```bash
pip install -r requirements.txt
playwright install chromium
```

## Test obligatoire avant le lancement complet

Commence par deux produits :

```bash
python main_daraz.py --limit 2 --no-resume
```

Pour afficher le navigateur pendant le test :

PowerShell :

```powershell
$env:DARAZ_HEADLESS="0"
python main_daraz.py --limit 2 --no-resume
```

CMD :

```cmd
set DARAZ_HEADLESS=0
python main_daraz.py --limit 2 --no-resume
```

## Vérifier le résultat

```bash
python check_daraz.py
```

Le CSV contient exactement les 14 champs demandés :

```text
id
site
row_id
lien
titre
marque
categorie
sous_categorie
prix
devise
description
liens_images
nb_images
statut_scraping
```

## Scraping complet

Quand le test est correct :

```bash
python main_daraz.py
```

Le script reprend automatiquement les lignes déjà terminées.

Pour une plage précise :

```bash
python main_daraz.py --start-id 1 --end-id 100
```

## Télécharger les images

Après le scraping des métadonnées :

```bash
python download_images_daraz.py --workers 4
```

Tester un seul produit :

```bash
python download_images_daraz.py --id 1 --workers 2
```

## Statut hors stock

Une fiche hors stock est conservée avec :

```text
statut_scraping = hors_stock
```

Le prix peut alors rester vide. Il ne faut pas confondre ce cas avec une erreur d'extraction.

## Devise

La devise est adaptée au domaine Daraz :

- Pakistan : PKR
- Sri Lanka : LKR
- Bangladesh : BDT
- Népal : NPR
- Myanmar : MMK

Cela est nécessaire car le fichier du groupe ne contient pas uniquement `daraz.pk`.


## Validation limitee avant le lancement complet

Les 14 colonnes du CSV brut restent identiques. Les images ne sont pas telechargees
pendant ces tests : seules les URLs de la galerie de la variante sont collectees.

```powershell
.\.venv\Scripts\python.exe main_daraz.py --limit 10 --no-resume
.\.venv\Scripts\python.exe check_daraz.py
.\.venv\Scripts\python.exe validate_daraz.py --stage first10
.\.venv\Scripts\python.exe validate_daraz.py --stage representative --select-only
.\.venv\Scripts\python.exe validate_daraz.py --stage representative --exclude-ids 306
.\.venv\Scripts\python.exe validate_daraz.py --stage final
.\.venv\Scripts\python.exe audit_daraz.py output/validation/final
.\.venv\Scripts\python.exe -m unittest test_daraz -v
```

`validate_daraz.py` choisit automatiquement une fiche par combinaison disponible
pays/sous-categorie, ou 36 fiches reparties dans ces groupes pour le test final.
Il refuse les echantillons de plus de 40 fiches. Chaque etape conserve sa selection,
son CSV de 14 colonnes, son rapport et ses captures HTTP/Playwright dans
`output/validation/`. Le CSV principal reste conserve.
`main_daraz.py --ids 1,3 --output output/test.csv --no-resume`
permet un diagnostic cible.

Le stock est interprete uniquement dans les commandes du produit :
? Almost sold out ? reste disponible avec un bouton d'achat actif ;
une zone vide ou un bouton desactive ne prouve pas une disponibilite.
Un stock impossible a confirmer est signale comme erreur et ne sera pas ignore
par la reprise. Le JSON-LD generique InStock ne suffit pas a lui seul.
Le prix affiche dans le bloc produit prime sur les offres SEO ; le prix de suivi
integre au produit reste un repli quand aucun prix affiche n'est disponible.
Le domaine determine la devise (PKR/LKR/BDT/NPR).

La fiche 306 a renvoye HTTP 404 et une page Daraz ? We seem to have lost this page ?
lors du diagnostic. L'exclusion ci-dessus sert seulement a choisir une autre fiche
representative pour les ecouteurs ; le test final conserve les URLs invalides
selectionnees afin de verifier leur signalement. Aucune URL du fichier Excel
n'est modifiee.

Le lancement complet des 320 URLs demande une confirmation explicite de l'utilisateur
apres revue des rapports. Les outils de validation ne le lancent jamais automatiquement.
