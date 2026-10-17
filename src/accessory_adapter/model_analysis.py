#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect GLB mesh, scene, skin, skeleton and reference structure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .model_io import (
    GLBDocument, build_parent_map, node_hierarchy_path, node_name,
    read_accessor, read_glb, validate_glb,
)
from .skeleton_mapping import build_skeleton_mapping


def analyze_model(model: GLBDocument) -> dict[str, Any]:
    doc = model.json
    nodes = doc.get("nodes", [])
    meshes = doc.get("meshes", [])
    skins = doc.get("skins", [])
    parent_map = build_parent_map(doc)
    child_parents: dict[int, list[int]] = {}
    for parent, node in enumerate(nodes):
        for child in node.get("children", []):
            child_parents.setdefault(int(child), []).append(parent)

    mesh_nodes: dict[int, list[int]] = {}
    for node_index, node in enumerate(nodes):
        if "mesh" in node:
            mesh_nodes.setdefault(int(node["mesh"]), []).append(node_index)

    mesh_reports = []
    for mesh_index, mesh in enumerate(meshes):
        primitive_reports = []
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            attrs_report = {}
            for name, accessor_index in primitive.get("attributes", {}).items():
                accessor_index = int(accessor_index)
                accessor = doc.get("accessors", [])[accessor_index]
                attrs_report[name] = {
                    "accessor": accessor_index,
                    "count": accessor.get("count"),
                    "type": accessor.get("type"),
                    "component_type": accessor.get("componentType"),
                    "normalized": accessor.get("normalized", False),
                }
            position = primitive.get("attributes", {}).get("POSITION")
            bounds = None
            if position is not None:
                accessor = doc["accessors"][int(position)]
                if "min" in accessor and "max" in accessor:
                    bounds = {"min": accessor["min"], "max": accessor["max"]}
                else:
                    values = read_accessor(model, int(position))
                    if values:
                        vectors = [list(v) for v in values]
                        bounds = {
                            "min": [min(v[i] for v in vectors) for i in range(3)],
                            "max": [max(v[i] for v in vectors) for i in range(3)],
                        }
            primitive_reports.append({
                "index": primitive_index,
                "mode": primitive.get("mode", 4),
                "material": primitive.get("material"),
                "attributes": attrs_report,
                "position_bounds": bounds,
                "indices_accessor": primitive.get("indices"),
                "morph_target_count": len(primitive.get("targets", [])),
            })
        mesh_reports.append({
            "index": mesh_index,
            "name": mesh.get("name", f"mesh_{mesh_index}"),
            "node_indices": mesh_nodes.get(mesh_index, []),
            "primitive_count": len(primitive_reports),
            "primitives": primitive_reports,
        })

    skin_reports = []
    for skin_index, skin in enumerate(skins):
        joint_reports = []
        for joint_slot, node_index in enumerate(skin.get("joints", [])):
            node_index = int(node_index)
            joint_reports.append({
                "skin_joint_index": joint_slot,
                "node_index": node_index,
                "name": node_name(doc, node_index),
                "parent_node_index": parent_map.get(node_index),
                "parent_name": node_name(doc, parent_map[node_index]) if node_index in parent_map else None,
                "hierarchy_path": list(node_hierarchy_path(doc, node_index)),
            })
        ibm_info = None
        if "inverseBindMatrices" in skin:
            ai = int(skin["inverseBindMatrices"])
            accessor = doc.get("accessors", [])[ai]
            ibm_info = {"accessor": ai, "count": accessor.get("count"), "type": accessor.get("type")}
        skin_reports.append({
            "index": skin_index,
            "name": skin.get("name", f"skin_{skin_index}"),
            "skeleton_node": skin.get("skeleton"),
            "skeleton_name": node_name(doc, int(skin["skeleton"])) if "skeleton" in skin else None,
            "joint_count": len(joint_reports),
            "inverse_bind_matrices": ibm_info,
            "joints": joint_reports,
        })

    nodes_report = []
    for i, node in enumerate(nodes):
        nodes_report.append({
            "index": i,
            "name": node_name(doc, i),
            "parent_indices": child_parents.get(i, []),
            "children": node.get("children", []),
            "mesh": node.get("mesh"),
            "skin": node.get("skin"),
            "hierarchy_path": list(node_hierarchy_path(doc, i)),
        })

    errors = validate_glb(model)
    return {
        "file": str(model.source_path) if model.source_path else None,
        "asset": doc.get("asset", {}),
        "summary": {
            "node_count": len(nodes),
            "mesh_count": len(meshes),
            "skin_count": len(skins),
            "material_count": len(doc.get("materials", [])),
            "texture_count": len(doc.get("textures", [])),
            "image_count": len(doc.get("images", [])),
            "animation_count": len(doc.get("animations", [])),
            "accessor_count": len(doc.get("accessors", [])),
            "buffer_view_count": len(doc.get("bufferViews", [])),
            "validation_error_count": len(errors),
        },
        "validation_errors": errors,
        "nodes": nodes_report,
        "meshes": mesh_reports,
        "skins": skin_reports,
        "materials": [
            {"index": i, "name": material.get("name", f"material_{i}"),
             "alpha_mode": material.get("alphaMode", "OPAQUE"),
             "double_sided": material.get("doubleSided", False)}
            for i, material in enumerate(doc.get("materials", []))
        ],
    }


def make_comparison(source: GLBDocument, target: GLBDocument,
                    source_skin_index: int = 0, target_skin_index: int = 0) -> dict[str, Any]:
    mapping = build_skeleton_mapping(
        source.json, source_skin_index, target.json, target_skin_index
    )
    return {
        "source_file": str(source.source_path) if source.source_path else None,
        "target_file": str(target.source_path) if target.source_path else None,
        "source_skin_index": source_skin_index,
        "target_skin_index": target_skin_index,
        **mapping,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="只读分析 GLB 的网格、骨骼、蒙皮与引用关系。")
    parser.add_argument("input", help="输入 GLB 文件")
    parser.add_argument("-o", "--output", help="JSON 报告输出路径；默认打印到终端")
    parser.add_argument("--compare-to", help="可选：与另一个 GLB 比较骨架")
    parser.add_argument("--source-skin", type=int, default=0, help="输入模型 Skin 索引，默认 0")
    parser.add_argument("--target-skin", type=int, default=0, help="对比模型 Skin 索引，默认 0")
    args = parser.parse_args()
    try:
        source = read_glb(args.input)
        report = analyze_model(source)
        if args.compare_to:
            target = read_glb(args.compare_to)
            report["skeleton_comparison"] = make_comparison(
                source, target, args.source_skin, args.target_skin
            )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            print(f"分析完成：{output.resolve()}")
            print(f"网格 {report['summary']['mesh_count']}；Skin {report['summary']['skin_count']}；结构问题 {report['summary']['validation_error_count']}")
        else:
            print(rendered)
        return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"分析失败：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
