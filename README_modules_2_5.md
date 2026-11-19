# Modules d'audit 2 à 5 — Projet Daraz

Ces scripts sont conçus pour être placés à la racine du projet `daraz_scraping_groupe`,
au même niveau que `README.md`, `requirements.txt` et `main_daraz.py`.

## 1. Fichiers fournis

- `audit_common.py` : fonctions communes de lecture d'inventaire, de chemins et d'écriture JSON.
- `module2_integrity.py` : vérification existence, taille, ouverture et décodage complet.
- `module3_formats_color.py` : format réel, extension, mode couleur, canal alpha, transparence et profil ICC.
- `module4_exif_orientation.py` : lecture de la balise EXIF Orientation (274).
- `module5_visual_duplicates.py` : SHA-256 et pHash dans le même dossier produit uniquement.

## 2. Prérequis obligatoire : l'inventaire final du Module 1

Le guide demande un fichier `images_inventory.json` contenant une entrée par image et au minimum :

- `image_id`
- `platform`
- `entity_id`
- `image_name`
- `file_path`
- `file_extension`
- `file_size_bytes`

Par défaut, les scripts cherchent `images_inventory.json` à la racine du projet.

**Attention :** `images_inventory_csv_test.json` est un fichier de test du Module 1. Il ne sera pas utilisé automatiquement.
Il faut d'abord générer l'inventaire final basé sur les fichiers physiques du dossier `output/images/daraz/`.
Les chemins `file_path` doivent être relatifs à la racine du projet, par exemple :
`output/images/daraz/1/image_1.jpg`.

Si l'inventaire final est enregistré ailleurs, utilise `--inventory "chemin/vers/images_inventory.json"`.

## 3. Installation

Dans le terminal PowerShell de VS Code, à la racine du projet :

```powershell
python -m pip install Pillow ImageHash
```

## 4. Ordre d'exécution

Exécuter les modules dans cet ordre, après avoir généré `images_inventory.json` :

```powershell
python module2_integrity.py
python module3_formats_color.py
python module4_exif_orientation.py
python module5_visual_duplicates.py
```

Les rapports sont enregistrés dans `output/validation/`.

## 5. Seuil pHash du Module 5

Le seuil initial est une distance de Hamming maximale de 6 sur un pHash de 64 bits.
Cela correspond à une similarité normalisée minimale de 0,90625.

Ce seuil est un paramètre de départ, pas une vérité universelle : les paires `near_duplicate`
restent en `pending` et doivent être examinées humainement. Pour changer le seuil :

```powershell
python module5_visual_duplicates.py --max-phash-distance 4
```

## 6. Principes de sécurité de l'audit

- Aucun script ne supprime, ne déplace, ne redimensionne, ne convertit ni ne modifie les images originales.
- Les modules 3 et 4 ne traitent que les images déclarées `valid` dans le rapport du Module 2.
- Le Module 5 compare uniquement les images appartenant au même couple `(platform, entity_id)`.
- Les doublons exacts sont recommandés pour `remove_one_copy`, mais restent `pending` : aucune suppression n'est effectuée.
- Les doublons visuellement similaires sont recommandés pour `manual_review`.
