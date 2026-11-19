# Finaliser l'inventaire physique Daraz (Module 1)

## Ce que nous avons déjà vérifié à partir des fichiers fournis

- `images_inventory_csv_test.json` contient 1 379 enregistrements.
- Le CSV produits contient 320 produits.
- La somme de `nb_images` dans le CSV est 1 379.
- 307 produits possèdent au moins une image et 13 n'en possèdent aucune.
- Les `entity_id` du JSON correspondent aux identifiants `id` du CSV.
- Pour chaque produit, le nombre d'images et l'ordre des URL dans le JSON correspondent au CSV.
- Les deux CSV fournis (`produits_daraz(1).csv` et `produits_daraz_brut.csv`) ont le même contenu octet par octet.

## Fichiers à placer à la racine du projet

- `images_inventory_csv_test.json`
- `build_images_inventory.py`
- `images_inventory.json` (inventaire de départ fourni dans cette archive)

Le projet doit conserver les images dans `output/images/daraz/<entity_id>/`.

## Recommandation

Le fichier `images_inventory.json` fourni contient les chemins attendus :
`output/images/daraz/<entity_id>/<image_name>`.

Ces chemins sont construits à partir des identifiants et noms de fichiers du JSON source.
La présence réelle des images sur ton ordinateur n'a pas pu être vérifiée ici, car le dossier local `output/images/daraz/` n'a pas été joint.

Pour effectuer le contrôle physique sur ton PC, place `build_images_inventory.py` à la racine du projet et lance :

```powershell
.\.venv\Scripts\python.exe build_images_inventory.py
```

Le script va :
- scanner les fichiers réels de `output/images/daraz/`;
- associer les fichiers par dossier produit (`entity_id`) et nom d'image;
- renseigner `file_path` et `file_size_bytes`;
- générer/actualiser `images_inventory.json`;
- générer `output/validation/module1_inventory_build_report.json`;
- lister les images manquantes, ambiguës et les fichiers physiques non référencés.

Aucune image n'est modifiée ou supprimée.

## Après le contrôle physique

Si les chemins et les correspondances sont corrects, exécute les modules dans cet ordre :

```powershell
.\.venv\Scripts\python.exe module2_integrity.py
.\.venv\Scripts\python.exe module3_formats_color.py
.\.venv\Scripts\python.exe module4_exif_orientation.py
.\.venv\Scripts\python.exe module5_visual_duplicates.py
```

Ne lance pas les modules 3 à 5 si le Module 2 n'a pas produit son rapport.
