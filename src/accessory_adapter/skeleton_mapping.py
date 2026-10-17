#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conservative skeleton comparison and joint-name mapping helpers.

No automatic geometric retargeting is performed here. This module only reports
explicitly defensible name matches and leaves unknown joints unmapped.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .model_io import build_parent_map, node_hierarchy_path, node_name


def _skin(doc: dict[str, Any], skin_index: int) -> dict[str, Any]:
    skins = doc.get("skins", [])
    if skin_index < 0 or skin_index >= len(skins):
        raise ValueError(f"Skin 索引越界：{skin_index}；该模型共有 {len(skins)} 个 Skin。")
    return skins[skin_index]


def build_skeleton_mapping(source_doc: dict[str, Any], source_skin_index: int,
                           target_doc: dict[str, Any], target_skin_index: int,
                           aliases: dict[str, str] | None = None) -> dict[str, Any]:
    """Map source Skin joint slots to target Skin slots by exact names or explicit aliases.

    `aliases` is source joint name -> target joint name. Ambiguous target names are not
    guessed; they are returned in `ambiguous` for manual resolution.
    """
    source_skin = _skin(source_doc, source_skin_index)
    target_skin = _skin(target_doc, target_skin_index)
    aliases = aliases or {}
    target_nodes = target_doc.get("nodes", [])
    target_slots: dict[str, list[int]] = defaultdict(list)
    for target_slot, node_index in enumerate(target_skin.get("joints", [])):
        target_slots[node_name(target_doc, int(node_index))].append(target_slot)

    matches = []
    unmatched = []
    ambiguous = []
    for source_slot, source_node_index in enumerate(source_skin.get("joints", [])):
        source_name = node_name(source_doc, int(source_node_index))
        wanted_name = aliases.get(source_name, source_name)
        candidates = target_slots.get(wanted_name, [])
        if len(candidates) == 1:
            target_slot = candidates[0]
            target_node_index = int(target_skin["joints"][target_slot])
            matches.append({
                "source_joint_index": source_slot,
                "source_node_index": int(source_node_index),
                "source_name": source_name,
                "target_joint_index": target_slot,
                "target_node_index": target_node_index,
                "target_name": node_name(target_doc, target_node_index),
                "match_type": "explicit_alias" if source_name in aliases else "exact_name",
                "source_hierarchy_path": list(node_hierarchy_path(source_doc, int(source_node_index))),
                "target_hierarchy_path": list(node_hierarchy_path(target_doc, target_node_index)),
            })
        elif len(candidates) > 1:
            ambiguous.append({
                "source_joint_index": source_slot,
                "source_node_index": int(source_node_index),
                "source_name": source_name,
                "requested_target_name": wanted_name,
                "candidate_target_joint_indices": candidates,
                "reason": "目标 Skin 中存在同名骨骼；没有自动猜测。",
            })
        else:
            unmatched.append({
                "source_joint_index": source_slot,
                "source_node_index": int(source_node_index),
                "source_name": source_name,
                "requested_target_name": wanted_name,
                "source_hierarchy_path": list(node_hierarchy_path(source_doc, int(source_node_index))),
            })

    source_count = len(source_skin.get("joints", []))
    target_count = len(target_skin.get("joints", []))
    return {
        "source_joint_count": source_count,
        "target_joint_count": target_count,
        "matched_count": len(matches),
        "unmatched_count": len(unmatched),
        "ambiguous_count": len(ambiguous),
        "coverage": (len(matches) / source_count) if source_count else 1.0,
        "matches": matches,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "notes": [
            "此结果仅为名称映射建议，不会自动改写蒙皮权重或 inverse bind matrices。",
            "层级路径用于人工核验；同名但层级不同的骨骼仍会列为名称匹配，需要进一步验证。",
        ],
    }
