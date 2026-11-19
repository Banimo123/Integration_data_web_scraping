"""Fonctions communes aux modules d'audit 2 à 5.

Les scripts sont prévus pour être placés à la racine du projet Daraz.
Ils lisent images_inventory.json et écrivent les résultats dans output/validation/.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_VALIDATION_DIR = Path("output") / "validation"


def resolve_path(project_root: Path, value: str | Path) -> Path:
    """Résout un chemin absolu ou relatif à la racine du projet."""
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def load_json_records(path: Path, description: str) -> list[dict[str, Any]]:
    """Charge une liste JSON ou une liste contenue dans un objet JSON."""
    if not path.exists():
        raise FileNotFoundError(
            f"{description} introuvable : {path}\n"
            "Vérifie le chemin ou génère d'abord le livrable du module précédent."
        )

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = None
        for key in ("images", "records", "items", "inventory", "results"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
        if records is None:
            raise ValueError(
                f"Format JSON non reconnu dans {path}. "
                "Attendu : une liste d'enregistrements ou un objet contenant "
                "'images', 'records', 'items', 'inventory' ou 'results'."
            )
    else:
        raise ValueError(f"Le contenu de {path} doit être une liste ou un objet JSON.")

    if not all(isinstance(row, dict) for row in records):
        raise ValueError(f"Chaque élément de {description} doit être un objet JSON.")

    return records


def load_inventory(project_root: Path, inventory_arg: str) -> tuple[list[dict[str, Any]], Path]:
    inventory_path = resolve_path(project_root, inventory_arg)
    records = load_json_records(inventory_path, "Inventaire du Module 1")

    required = ("image_id", "platform", "entity_id", "file_path")
    errors = []
    for index, row in enumerate(records):
        missing = [field for field in required if row.get(field) in (None, "")]
        if missing:
            errors.append(f"Enregistrement {index}: champ(s) manquant(s) {', '.join(missing)}")

    if errors:
        preview = "\n".join(errors[:10])
        raise ValueError(
            "L'inventaire ne respecte pas le schéma attendu par le guide.\n"
            f"{preview}\n"
            "Le fichier images_inventory.json doit contenir au minimum "
            "image_id, platform, entity_id et file_path pour chaque image."
        )

    return records, inventory_path


def image_path_from_record(project_root: Path, record: dict[str, Any]) -> Path:
    return resolve_path(project_root, str(record["file_path"]))


def load_integrity_map(project_root: Path, integrity_arg: str) -> dict[str, dict[str, Any]]:
    integrity_path = resolve_path(project_root, integrity_arg)
    records = load_json_records(integrity_path, "Rapport d'intégrité du Module 2")
    result = {}
    for row in records:
        if row.get("image_id") is not None:
            result[str(row["image_id"])] = row
    return result


def valid_inventory_records(
    inventory: list[dict[str, Any]],
    integrity_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retourne uniquement les images déclarées valid par le Module 2."""
    valid = []
    for row in inventory:
        integrity = integrity_map.get(str(row["image_id"]))
        if integrity and integrity.get("integrity_status") == "valid" and integrity.get("is_readable") is True:
            valid.append(row)
    return valid


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def default_output_path(project_root: Path, filename: str) -> Path:
    return project_root / DEFAULT_VALIDATION_DIR / filename


def print_input_summary(inventory_path: Path, count: int) -> None:
    print(f"Inventaire utilisé : {inventory_path}")
    print(f"Nombre d'images dans l'inventaire : {count}")
