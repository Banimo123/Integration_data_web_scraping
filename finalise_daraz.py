"""Genere les livrables a partir des preuves locales, sans modifier le CSV brut."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from check_daraz import analyse
from check_images_daraz import run as audit_images
from main_daraz import CSV_FIELDNAMES, INPUT_XLSX, read_products

OUT = Path("output/validation")


def write(name, text):
    (OUT / name).write_text(text + "\n", encoding="utf-8")


def run():
    raw = Path("output/produits_daraz.csv")
    backup = Path("output/raw/produits_daraz_brut.csv")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    assert digest == hashlib.sha256(backup.read_bytes()).hexdigest(), "Sauvegarde et original differents"
    integrity = OUT / "integrite_brut.json"
    if integrity.exists():
        assert json.loads(integrity.read_text(encoding="utf-8"))["sha256"] == digest, "Le brut differe de son empreinte initiale"
    with raw.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        assert reader.fieldnames == CSV_FIELDNAMES
        rows = list(reader)
    expected = {str(p["id"])+"_daraz": p for p in read_products(INPUT_XLSX)}
    counts = Counter(r["row_id"] for r in rows)
    missing = sorted(set(expected)-set(counts))
    extra = sorted(set(counts)-set(expected))
    duplicate_ids = {k: v for k, v in counts.items() if v > 1}
    duplicate_urls = {k: v for k, v in Counter(r["lien"] for r in rows).items() if v > 1}
    wrong_urls = [r["id"] for r in rows if r["row_id"] in expected and expected[r["row_id"]]["url"] != r["lien"]]
    q = analyse(raw)
    audit = json.loads((OUT / "complet/audit.json").read_text(encoding="utf-8"))
    prior = json.loads((OUT / "complet/bilan.json").read_text(encoding="utf-8"))
    image_report = audit_images()
    images = image_report["summary"]
    # Une revue semantique complete doit etre explicitement enregistree.
    review_path = OUT / "revue_visuelle.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    current_images = {(r["path"], r["sha256"]) for r in image_report["images"] if r["valid"]}
    reviewed_images = {(r["path"], r["sha256"]) for r in review.get("images", [])}
    review_complete = bool(current_images) and reviewed_images == current_images and review.get("complete") is True
    ready = not (missing or extra or duplicate_ids or wrong_urls or images["missing"] or images["invalid"] or images["unverified_associations"] or audit["fiches_avec_ecarts"] or q["devises_incoherentes"]) and review_complete
    decision = "Partie Daraz prête pour la fusion avec les autres plateformes" if ready else "Partie Daraz non prête pour la fusion"
    summary = {"qualite": q, "images": images, "sha256": digest, "missing": missing, "extra": extra, "duplicate_row_ids": duplicate_ids, "duplicate_urls": duplicate_urls, "wrong_urls": wrong_urls, "domains": dict(Counter(urlparse(r["lien"]).hostname for r in rows)), "categories": dict(Counter(r["sous_categorie"] for r in rows)), "erreurs": prior["erreurs_detaillees"], "audit_ecarts": audit["fiches_avec_ecarts"], "semantic_review_complete": review_complete, "ready": ready}
    summary["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    write("bilan_final.json", json.dumps(summary, ensure_ascii=False, indent=2))
    if not integrity.exists():
        write("integrite_brut.json", json.dumps({"sha256": digest, "original": str(raw), "backup": str(backup), "identiques": True}, indent=2))
    stats = "\n".join(f"- {k} : {v}" for k, v in q.items() if k != "anomalies")
    write("bilan_scraping_complet.md", f"# Bilan final Daraz\n\nURLs attendues : {len(expected)}. Fiches traitées : {len(rows)}.\n\n{stats}\n\nDomaines : {summary['domains']}\n\nSous-catégories : {summary['categories']}\n\nErreurs par cause : {prior['repartition_erreurs']}\n\nLignes manquantes : {missing}. Inattendues : {extra}. Doublons row_id : {duplicate_ids}. URLs dupliquées : {duplicate_urls}. URLs différentes de l'entrée : {wrong_urls}.\n\nÉcarts CSV/captures : {audit['fiches_avec_ecarts']}. Faux ok documentés : {prior['faux_ok']}.\n\nLes 13 fiches en erreur ont leurs champs inconnus conservés vides. Les preuves historiques ne garantissent pas l'état actuel des pages.\n\nSHA-256 original et sauvegarde : `{digest}`.\n\n{decision}")
    write("bilan_images_daraz.md", "# Bilan des images Daraz\n\n" + "\n".join(f"- {k} : {v}" for k, v in images.items()) + f"\n\nRevue visuelle complète : {review_complete}.\n\nDétails par URL, dimensions, taille, format, SHA-256 et anomalies : images_audit.json. Journal des tentatives : download_images.jsonl (les échecs anciens restent tracés ; le bilan courant compte les fichiers actuellement absents). Planches : planches/.\n\nCritères suspects : côté <200 pixels, ratio >5, taille <2048 octets ou URL indiquant un élément d'interface. Ces signaux ne prouvent pas un parasite. Aucune image supprimée. Les doublons exacts sont groupés par SHA-256 sans suppression, y compris entre produits. Les différentes vues sont conservées. Les quasi-doublons ne sont pas classés automatiquement. Les fichiers .part sont des tentatives incomplètes, exclus des images livrées.\n\n{decision}")
    write("erreurs_daraz.md", "# Erreurs de collecte Daraz\n\nLes statuts du brut sont conservés ; les causes ci-dessous reposent sur les preuves HTTP archivées.\n\n" + "\n".join(f"- ID {e['id']} : {e['type']} ; statut brut : {e['raison']} ; preuve : {e['http_evidence']} ; URL : {e['url']}" for e in prior["erreurs_detaillees"]) + "\n\nErreurs d'images : images_audit.json, section anomalies. Une page inaccessible ne permet pas de conclure qu'une donnée n'existe pas.")
    write("audit_qualite_daraz.md", f"""# Audit qualité Daraz

## Méthode et preuves

Requests et BeautifulSoup permettent une première extraction légère du HTML et des blocs structurés du produit. Playwright intervient lorsque le rendu dynamique ne fournit pas les données nécessaires. Le prix visible dans le bloc produit est prioritaire sur les offres SEO. La disponibilité repose sur les commandes du produit : un bouton actif prouve la disponibilité ; une mention explicite prouve le hors stock ; une zone vide reste indéterminée. Les recommandations ne servent pas de source de remplacement.

Les domaines diffèrent par leur devise et leurs données de rendu : daraz.pk/PKR, daraz.lk/LKR, daraz.com.bd/BDT, daraz.com.np/NPR. Aucune conversion monétaire n'est appliquée. Les galeries proviennent de la variante sélectionnée et sont comparées aux captures archivées. Les 404 sont documentées dans complet/preuve_ID.json. Les champs absents restent absents ; un prix absent hors stock n'est pas imputé.

## Corrections et contrôle

Le scraper de métadonnées est conservé. La validation par échantillon ne remplace plus le CSV principal ; les contrôles sans argument utilisent le dataset complet. Le téléchargement est séparé et amélioré : décodage avant reprise, fichier temporaire .part, publication après validation, extension déterminée par le format réel sans conversion, journal par produit/vue/URL et SHA-256. Pillow est ajouté car une réponse HTTP réussie ne suffit pas à vérifier une image. Concurrence : quatre workers. Les vues de galerie restent associées à leur index CSV. Les originaux ne sont pas redimensionnés.

Les contrôles techniques vérifient tous les pixels, dimensions, octets et doublons exacts. Les planches sont des dérivés pour inspection ; elles ne remplacent pas les originaux. Les seuils et limites sémantiques sont décrits dans bilan_images_daraz.md. Aucune suppression automatique. La similitude visuelle seule ne prouve pas un doublon inutile. Revue visuelle complète : {review_complete}.

## Fusion du groupe

Le CSV UTF-8 avec BOM utilise le séparateur point-virgule, exactement 14 colonnes dans l'ordre contractuel. row_id doit rester unique à travers les plateformes ; la clé recommandée est id_site. Les prix restent dans leur devise d'origine ; toute comparaison impose une conversion ultérieure documentée. Les galeries sont séparées par |. Le statut et les données manquantes doivent être conservés lors de la fusion. Les fichiers des collègues ne sont pas modifiés. Aucun script de fusion n'est exécuté. Le classeur commun d'entrée n'est pas un dataset de résultats.

## Section pour le rapport académique

La collecte Daraz porte sur {len(rows)} URLs réparties dans quatre pays. Elle fournit {q['ok']} fiches disponibles et {q['hors_stock']} fiches hors stock ; {q['erreurs']} erreurs HTTP 404 sont conservées avec leurs preuves. Le schéma commun de 14 champs est respecté. Les devises sont identifiées par domaine et les images sont collectées séparément, avec contrôle de reprise et audit technique. Les données brutes et leur copie de sécurité ont la même empreinte SHA-256. L'audit des captures archivées relève {audit['fiches_avec_ecarts']} écart. Les limitations concernent les produits supprimés, l'évolution des sites et la validation sémantique des images, qui ne peut être certifiée par des heuristiques techniques seules.

## Décision

{decision}

La décision porte sur la fusion des données brutes documentées. Les images ambiguës signalées dans observations_visuelles.json et images_audit.json restent conservées avec leurs motifs et nécessitent une décision manuelle avant un éventuel entraînement. Une galerie source peut elle-même mélanger des modèles ; ce constat ne justifie pas de changer artificiellement son extraction. La revue sur planches repère les anomalies manifestes et ne certifie pas chaque détail commercial ou le modèle exact.

Si la décision est négative, consulter bilan_images_daraz.md : fichiers absents/corrompus ou revue sémantique incomplète. Les erreurs 404 documentées ne sont pas masquées et n'empêchent pas à elles seules la fusion. Les doublons exacts ne sont pas supprimés, car ils peuvent appartenir légitimement à plusieurs fiches.
""")
    print(json.dumps({"decision": decision, "images": images, "sha256": digest}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    run()
