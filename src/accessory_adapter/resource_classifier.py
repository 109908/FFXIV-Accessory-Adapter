#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Heuristic file classifier for local FFXIV/Penumbra resources.

Classification is deliberately conservative: a file name can suggest a role, but
never proves that a model is vanilla or that its species is verified.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

EXTENSION_TYPES = {
    ".pmp": "penumbra_mod_archive",
    ".zip": "zip_archive",
    ".mdl": "ffxiv_model_mdl",
    ".sklb": "ffxiv_skeleton_sklb",
    ".mtrl": "ffxiv_material_mtrl",
    ".tex": "ffxiv_texture_tex",
    ".glb": "gltf_binary_model",
    ".gltf": "gltf_json_model",
    ".json": "json_configuration_or_data",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".dds": "texture_or_image",
}

# Examples: c0501e6047_met.mdl, c1701e6047_met.glb, c0501b0002_top.mdl
_MODEL_CODE_RE = re.compile(r"(?i)(c\d{4})([a-z]\d{4})_([a-z0-9]+)")
_SKLB_CODE_RE = re.compile(r"(?i)skl_(c\d{4})([a-z]\d{4})")
_EQUIPMENT_RE = re.compile(r"(?i)(?:^|[/_])e(\d{4})(?:[/_.]|$)")


def classify_resource(path: str, assigned_role: str | None = None, size_bytes: int | None = None) -> dict[str, Any]:
    """Classify a path and return evidence-based hints without overclaiming provenance."""
    normalized = str(path).replace("\\", "/").strip("/")
    pure = PurePosixPath(normalized)
    name = pure.name
    lower = normalized.casefold()
    suffix = pure.suffix.casefold()
    stem = pure.stem
    if lower.endswith(".json.bak"):
        resource_type = "backup_mod_configuration"
    else:
        resource_type = EXTENSION_TYPES.get(suffix, "other_file")
    hints: list[str] = []
    if lower.endswith(".json.bak"):
        hints.extend(["backup_configuration_candidate", "not_active_configuration_by_default"])
    model_code = None
    model_component = None
    model_variant = None
    equipment_id = None

    match = _MODEL_CODE_RE.search(name)
    if match:
        model_code, model_component, model_variant = (part.lower() for part in match.groups())
    else:
        sklb_match = _SKLB_CODE_RE.search(name)
        if sklb_match:
            model_code, model_component = (part.lower() for part in sklb_match.groups())

    equipment_match = _EQUIPMENT_RE.search(lower)
    if equipment_match:
        equipment_id = f"e{equipment_match.group(1)}"
    elif model_component and model_component.startswith("e"):
        equipment_id = model_component

    if suffix == ".json":
        if name.casefold() == "meta.json" or name.casefold().startswith("group_") or name.casefold() == "default_mod.json":
            hints.append("penumbra_or_mod_configuration")
    if suffix in {".pmp", ".zip"}:
        hints.append("archive_candidate")
    if suffix == ".mdl":
        hints.append("ffxiv_model_candidate")
        if model_component and model_component.startswith("e"):
            hints.append("equipment_model_candidate")
        if model_component and model_component.startswith("b"):
            hints.append("body_part_model_candidate")
        if model_component and model_component.startswith("f"):
            hints.append("face_or_head_model_candidate")
        if "chara/equipment/" in lower or "/equipment/" in lower:
            hints.append("equipment_path")
    if suffix == ".sklb":
        hints.append("skeleton_candidate")
    if suffix in {".glb", ".gltf"}:
        hints.append("interchange_model_candidate")
        if model_component and model_component.startswith("e"):
            hints.append("equipment_model_candidate")
    if equipment_id:
        hints.append("equipment_id_from_name_or_path")
    if model_code:
        hints.append("character_model_code_candidate")
    if "e6047" in lower:
        hints.append("e6047_werewolf_head_equipment_candidate")
    if "elezen male" in lower or "c0501" in lower:
        hints.append("c0501_elezen_male_candidate")
    if "viera" in lower or "c1701" in lower or "c1801" in lower:
        hints.append("viera_resource_candidate")
    if "body" in lower or "_top" in lower or "b0002" in lower:
        hints.append("body_reference_candidate")
    if "skl_" in name.casefold():
        hints.append("skeleton_file_name_pattern")

    return {
        "path": normalized,
        "name": name,
        "extension": suffix,
        "size_bytes": size_bytes,
        "resource_type": resource_type,
        "assigned_input_role": assigned_role,
        "model_code_candidate": model_code,
        "model_component_candidate": model_component,
        "model_variant_candidate": model_variant,
        "equipment_id_candidate": equipment_id,
        "hints": sorted(set(hints)),
        "provenance_verified": False,
        "provenance_note": "文件名/路径仅用于候选分类；不能据此证明是官方原版或已验证的目标模型。",
    }
