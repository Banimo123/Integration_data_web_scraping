"""
MODULE 1 - TEST CSV
------------------
Ce script fait un premier test du Module 1 à partir d'un fichier CSV.

IMPORTANT :
- Il utilise les URLs d'images présentes dans la colonne "liens_images".
- Il ne parcourt PAS les vrais dossiers d'images sur le disque.
- Les champs "file_path" et "file_size_bytes" restent donc à None.
- Pour le test, la colonne "id" est utilisée comme entity_id si la colonne
  "entity_id" n'existe pas dans le CSV.

Fichiers générés :
1. images_inventory_csv_test.json
2. module1_volumetry_csv_test.json

Place ce script dans le même dossier que produits_daraz.csv.
"""

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, unquote


# ---------------------------------------------------------------------
# 1. CHEMINS DES FICHIERS
# ---------------------------------------------------------------------

# Dossier dans lequel se trouve ce script Python.
DOSSIER_PROJET = Path(__file__).resolve().parent

# Le CSV doit être placé dans le même dossier que ce script.
FICHIER_CSV = DOSSIER_PROJET / "output" / "produits_daraz.csv"

# Fichiers JSON qui seront créés automatiquement.
FICHIER_INVENTAIRE = DOSSIER_PROJET / "images_inventory_csv_test.json"
FICHIER_VOLUMETRIE = DOSSIER_PROJET / "module1_volumetry_csv_test.json"


# ---------------------------------------------------------------------
# 2. FONCTIONS UTILITAIRES
# ---------------------------------------------------------------------

def extraire_urls_images(texte):
    """
    Transforme la chaîne de la colonne 'liens_images' en une liste d'URLs.

    Dans notre CSV, plusieurs URLs sont séparées par le caractère '|'.
    Les cellules vides donnent une liste vide.
    """
    if not texte:
        return []

    urls = []

    for url in texte.split("|"):
        url = url.strip()

        if url:
            urls.append(url)

    return urls


def obtenir_extension(url):
    """
    Extrait l'extension du fichier à partir de l'URL.

    Exemple :
    https://site.com/photo123.jpg  -> .jpg
    """
    chemin_url = urlparse(url).path
    nom_fichier = unquote(Path(chemin_url).name)

    return Path(nom_fichier).suffix.lower()


def obtenir_nom_image(url, numero):
    """
    Extrait le nom du fichier depuis l'URL.

    Si l'URL ne contient pas de nom exploitable, on crée un nom temporaire.
    """
    chemin_url = urlparse(url).path
    nom_fichier = unquote(Path(chemin_url).name)

    if nom_fichier:
        return nom_fichier

    return f"image_{numero}"


def convertir_en_entier(valeur, valeur_par_defaut=None):
    """
    Convertit une valeur en entier sans arrêter le programme en cas d'erreur.
    """
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return valeur_par_defaut


# ---------------------------------------------------------------------
# 3. VÉRIFICATION DU FICHIER CSV
# ---------------------------------------------------------------------

if not FICHIER_CSV.exists():
    raise FileNotFoundError(
        f"Fichier introuvable : {FICHIER_CSV}\n"
        "Place produits_daraz.csv dans le même dossier que ce script."
    )


# Chaque clé représente une entité sur une plateforme :
# (plateforme, entity_id) -> liste des URLs d'images.
#
# On utilise une liste pour préserver l'ordre des images.
# Les doublons d'URLs seront supprimés plus tard.
images_par_entite = defaultdict(list)

# Nombre d'images déclaré dans le CSV, utilisé pour vérifier la cohérence.
nb_images_declare_par_entite = defaultdict(int)

# Ensemble des plateformes associées à chaque entity_id.
# Cela permet de repérer les produits présents sur plusieurs plateformes.
plateformes_par_entite = defaultdict(set)

nombre_lignes_csv = 0
nombre_lignes_sans_identifiant = 0
nombre_ecarts_nb_images = 0


# ---------------------------------------------------------------------
# 4. LECTURE DU CSV ET REGROUPEMENT DES IMAGES
# ---------------------------------------------------------------------

# utf-8-sig permet aussi de gérer un éventuel BOM au début du fichier.
# Le séparateur de notre fichier est le point-virgule ';'.
with open(FICHIER_CSV, mode="r", encoding="utf-8-sig", newline="") as fichier:
    lecteur = csv.DictReader(fichier, delimiter=";")

    colonnes = lecteur.fieldnames or []

    # Vérification minimale des colonnes nécessaires.
    colonnes_obligatoires = {"site", "liens_images"}

    colonnes_manquantes = colonnes_obligatoires - set(colonnes)

    if colonnes_manquantes:
        raise ValueError(
            "Colonnes manquantes dans le CSV : "
            + ", ".join(sorted(colonnes_manquantes))
        )

    # Si entity_id existe, on l'utilise.
    # Sinon, on utilise id comme identifiant provisoire du produit.
    if "entity_id" in colonnes:
        colonne_identifiant = "entity_id"
    elif "id" in colonnes:
        colonne_identifiant = "id"
    elif "row_id" in colonnes:
        colonne_identifiant = "row_id"
    else:
        raise ValueError(
            "Aucune colonne d'identification trouvée : "
            "il faut au minimum entity_id, id ou row_id."
        )

    for numero_ligne, ligne in enumerate(lecteur, start=2):
        nombre_lignes_csv += 1

        plateforme = (ligne.get("site") or "unknown").strip().lower()
        entity_id = (ligne.get(colonne_identifiant) or "").strip()

        # Si l'identifiant est absent, on utilise un identifiant temporaire.
        if not entity_id:
            nombre_lignes_sans_identifiant += 1
            entity_id = f"identifiant_manquant_ligne_{numero_ligne}"

        cle_entite = (plateforme, entity_id)

        # On ajoute l'entité même si elle n'a aucune image.
        # C'est important pour calculer le nombre d'entités vides.
        images_par_entite.setdefault(cle_entite, [])

        # Récupération des URLs d'images.
        urls = extraire_urls_images(ligne.get("liens_images", ""))

        # On ajoute les URLs sans doublons pour cette entité/plateforme.
        for url in urls:
            if url not in images_par_entite[cle_entite]:
                images_par_entite[cle_entite].append(url)

        # Vérification entre nb_images et le nombre réel d'URLs dans la cellule.
        nombre_declare = convertir_en_entier(ligne.get("nb_images"), None)

        if nombre_declare is not None and nombre_declare != len(urls):
            nombre_ecarts_nb_images += 1

        # Mémorisation du nombre déclaré pour les contrôles.
        if nombre_declare is not None:
            nb_images_declare_par_entite[cle_entite] += nombre_declare

        plateformes_par_entite[entity_id].add(plateforme)


# ---------------------------------------------------------------------
# 5. CRÉATION DE L'INVENTAIRE DES IMAGES
# ---------------------------------------------------------------------

inventaire_images = []

compteur_images = 0

for (plateforme, entity_id), urls in sorted(images_par_entite.items()):

    for numero_image, url in enumerate(urls, start=1):
        compteur_images += 1

        inventaire_images.append({
            "image_id": f"IMG_{compteur_images:06d}",
            "platform": plateforme,
            "entity_id": entity_id,
            "image_name": obtenir_nom_image(url, numero_image),

            # Ces deux champs ne peuvent pas être calculés depuis une URL CSV.
            # Ils seront renseignés lors de l'audit des vrais dossiers locaux.
            "file_path": None,
            "file_extension": obtenir_extension(url),
            "file_size_bytes": None,

            # Champ supplémentaire pour conserver l'URL source.
            "image_url": url
        })


# ---------------------------------------------------------------------
# 6. CALCUL DE LA VOLUMÉTRIE PAR PLATEFORME
# ---------------------------------------------------------------------

# On récupère la liste des plateformes présentes dans le CSV.
plateformes = sorted({
    plateforme
    for plateforme, entity_id in images_par_entite.keys()
})

rapport_volumetrie = []

for plateforme in plateformes:

    # On récupère toutes les entités de cette plateforme.
    entites_plateforme = {
        entity_id: urls
        for (nom_plateforme, entity_id), urls in images_par_entite.items()
        if nom_plateforme == plateforme
    }

    # Nombre d'images de chaque entité.
    # Une entité sans image aura une valeur égale à 0.
    nombres_images = [
        len(urls)
        for urls in entites_plateforme.values()
    ]

    total_entites = len(entites_plateforme)
    total_images = sum(nombres_images)

    # Les statistiques incluent les entités avec zéro image.
    if total_entites > 0:
        minimum = min(nombres_images)
        maximum = max(nombres_images)
        moyenne = round(statistics.mean(nombres_images), 2)
        mediane = round(statistics.median(nombres_images), 2)
    else:
        minimum = None
        maximum = None
        moyenne = None
        mediane = None

    nombre_entites_une_image = sum(
        1 for nombre in nombres_images if nombre == 1
    )

    nombre_entites_vides = sum(
        1 for nombre in nombres_images if nombre == 0
    )

    rapport_volumetrie.append({
        "platform_name": plateforme,
        "total_entities": total_entites,
        "total_images": total_images,
        "min_images_per_entity": minimum,
        "max_images_per_entity": maximum,
        "avg_images_per_entity": moyenne,
        "median_images_per_entity": mediane,
        "single_image_entities_count": nombre_entites_une_image,
        "empty_entities_count": nombre_entites_vides
    })


# ---------------------------------------------------------------------
# 7. SAUVEGARDE DES DEUX RAPPORTS JSON
# ---------------------------------------------------------------------

with open(FICHIER_INVENTAIRE, mode="w", encoding="utf-8") as fichier:
    json.dump(
        inventaire_images,
        fichier,
        ensure_ascii=False,
        indent=4
    )

with open(FICHIER_VOLUMETRIE, mode="w", encoding="utf-8") as fichier:
    json.dump(
        rapport_volumetrie,
        fichier,
        ensure_ascii=False,
        indent=4
    )


# ---------------------------------------------------------------------
# 8. ANALYSE DE LA COUVERTURE MULTI-PLATEFORME
# ---------------------------------------------------------------------

nombre_entites_distinctes = len(plateformes_par_entite)

nombre_entites_multi_plateformes = sum(
    1
    for plateformes_entite in plateformes_par_entite.values()
    if len(plateformes_entite) > 1
)


# ---------------------------------------------------------------------
# 9. AFFICHAGE DU RÉSUMÉ DANS LE TERMINAL
# ---------------------------------------------------------------------

print("\n" + "=" * 65)
print("       MODULE 1 - TEST DE VOLUMÉTRIE À PARTIR DU CSV")
print("=" * 65)

print(f"\nFichier analysé : {FICHIER_CSV.name}")
print(f"Nombre de lignes CSV : {nombre_lignes_csv}")
print(f"Colonne utilisée comme entity_id : {colonne_identifiant}")
print(f"Nombre d'images inventoriées (URLs) : {len(inventaire_images)}")

print("\n--- Résultats par plateforme ---")

for rapport in rapport_volumetrie:
    print(f"\nPlateforme : {rapport['platform_name']}")
    print(f"  Entités : {rapport['total_entities']}")
    print(f"  Images : {rapport['total_images']}")
    print(f"  Minimum d'images/entité : {rapport['min_images_per_entity']}")
    print(f"  Maximum d'images/entité : {rapport['max_images_per_entity']}")
    print(f"  Moyenne d'images/entité : {rapport['avg_images_per_entity']}")
    print(f"  Médiane d'images/entité : {rapport['median_images_per_entity']}")
    print(
        "  Entités avec une seule image : "
        f"{rapport['single_image_entities_count']}"
    )
    print(f"  Entités sans image : {rapport['empty_entities_count']}")

print("\n--- Couverture multi-plateforme ---")
print(f"Entités distinctes : {nombre_entites_distinctes}")
print(f"Entités présentes sur plusieurs plateformes : {nombre_entites_multi_plateformes}")

print("\n--- Contrôles ---")
print(f"Lignes sans identifiant : {nombre_lignes_sans_identifiant}")
print(f"Lignes avec un écart entre nb_images et les URLs : {nombre_ecarts_nb_images}")

print("\n--- Fichiers générés ---")
print(f"1. {FICHIER_INVENTAIRE.name}")
print(f"2. {FICHIER_VOLUMETRIE.name}")

print("\nATTENTION : c'est un test basé sur les URLs du CSV.")
print("Les chemins locaux et les tailles réelles des fichiers seront")
print("calculés pendant l'audit des vrais dossiers d'images.")
print("\n" + "=" * 65)
