#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Head-accessory GLB adapter, extracted into the reusable package layer.

This is intentionally a rule-based prototype for the previously tested Inu ear GLB.
It is not yet a universal headwear retargeter and does not compile FF14 MDL.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from ..model_io import (GLBDocument, accessor_layout, node_name, read_model, read_accessor, write_glb)


def _rebind_skin_to_target(model: GLBDocument, skin_index: int,
                           target_path: str | Path,
                           head_joint_name: str = "j_kao") -> dict[str, Any]:
    """Replace the active mesh skin's joint hierarchy and inverse-bind matrices
    with those from the target-race reference GLB, matching bones by unique name.

    The source mesh stays in model coordinates. The caller applies the source-to-target
    head-position delta to the mesh vertices, while this function ensures the GLB skin
    actually uses the target skeleton rather than merely writing the source j_kao slot.
    """
    target_model = read_model(target_path)
    source_doc = model.json
    target_doc = target_model.json
    source_skin = source_doc["skins"][skin_index]

    candidates = []
    for index, skin in enumerate(target_doc.get("skins", [])):
        names = [node_name(target_doc, int(n)) for n in skin.get("joints", [])]
        if head_joint_name in names and skin.get("inverseBindMatrices") is not None:
            candidates.append((len(names), index, skin, names))
    if not candidates:
        raise ValueError(f"目标骨架 {Path(target_path).name} 中找不到带逆绑定矩阵的 {head_joint_name} Skin。")
    _count, target_skin_index, target_skin, target_names = max(candidates, key=lambda x: x[0])

    source_joint_ids = [int(x) for x in source_skin.get("joints", [])]
    source_names = [node_name(source_doc, n) for n in source_joint_ids]
    if len(source_names) != len(set(source_names)):
        duplicates = sorted({n for n in source_names if source_names.count(n) > 1})
        raise ValueError(f"源 Skin 存在重复骨骼名称，不能安全重定向：{duplicates[:8]}")
    target_names_unique = set(target_names)
    if len(target_names) != len(target_names_unique):
        raise ValueError("目标 Skin 存在重复骨骼名称，不能安全重定向。")
    source_node_by_name = {name: node_id for name, node_id in zip(source_names, source_joint_ids)}
    missing = [name for name in target_names if name not in source_node_by_name]
    if missing:
        raise ValueError(
            f"源模型缺少目标骨架所需的 {len(missing)} 个骨骼，不能安全重定向；"
            f"示例：{missing[:8]}"
        )

    target_joint_ids = [int(x) for x in target_skin["joints"]]
    target_node_by_name = {
        node_name(target_doc, node_id): node_id for node_id in target_joint_ids
    }
    source_node_for_target_name = {
        name: source_node_by_name[name] for name in target_names
    }

    # Copy target-race local transforms and hierarchy to the corresponding source nodes.
    transform_keys = ("translation", "rotation", "scale", "matrix")
    for target_name, target_node_id in target_node_by_name.items():
        source_node_id = source_node_for_target_name[target_name]
        source_node = source_doc["nodes"][source_node_id]
        target_node = target_doc["nodes"][target_node_id]
        for key in transform_keys:
            source_node.pop(key, None)
            if key in target_node:
                source_node[key] = list(target_node[key]) if isinstance(target_node[key], list) else target_node[key]
        target_children = target_node.get("children", [])
        mapped_children = []
        for child_id in target_children:
            child_name = node_name(target_doc, int(child_id))
            if child_name not in source_node_for_target_name:
                raise ValueError(
                    f"目标骨架节点 {target_name} 的子节点 {child_name} 不在目标 Skin 中；"
                    "当前原型拒绝生成不完整层级。"
                )
            mapped_children.append(source_node_for_target_name[child_name])
        if mapped_children:
            source_node["children"] = mapped_children
        else:
            source_node.pop("children", None)

    # Use the target Skin's exact joint order, mapped to nodes in the source GLB.
    source_skin["joints"] = [source_node_for_target_name[name] for name in target_names]
    source_skin.pop("skeleton", None)
    if target_skin.get("skeleton") is not None:
        skeleton_name = node_name(target_doc, int(target_skin["skeleton"]))
        if skeleton_name in source_node_for_target_name:
            source_skin["skeleton"] = source_node_for_target_name[skeleton_name]

    # Append a fresh IBM accessor so unused source skins/accessors are not modified.
    target_ibms = read_accessor(target_model, int(target_skin["inverseBindMatrices"]))
    if len(target_ibms) != len(target_names):
        raise ValueError("目标骨架逆绑定矩阵数量与 joints 数量不一致。")
    packed = b"".join(struct.pack("<16f", *(float(v) for v in matrix)) for matrix in target_ibms)
    while len(model.binary) % 4:
        model.binary.append(0)
    byte_offset = len(model.binary)
    model.binary.extend(packed)
    buffer_views = source_doc.setdefault("bufferViews", [])
    accessors = source_doc.setdefault("accessors", [])
    view_index = len(buffer_views)
    buffer_views.append({"buffer": 0, "byteOffset": byte_offset, "byteLength": len(packed)})
    accessor_index = len(accessors)
    accessors.append({
        "bufferView": view_index,
        "componentType": 5126,
        "count": len(target_ibms),
        "type": "MAT4",
    })
    source_skin["inverseBindMatrices"] = accessor_index

    return {
        "target_skeleton_file": str(Path(target_path).resolve()),
        "target_skin_index": target_skin_index,
        "source_skin_index": skin_index,
        "target_joint_count": len(target_names),
        "source_joint_count_before_rebind": len(source_names),
        "target_head_joint_name": head_joint_name,
        "target_head_joint_slot": target_names.index(head_joint_name),
        "inverse_bind_matrices_replaced": True,
        "hierarchy_and_local_transforms_replaced": True,
        "source_only_joint_names": sorted(set(source_names) - target_names_unique),
    }

def adapt_head_accessory(input_path: str | Path, output_path: str | Path,
                         y_offset: float = 0.2545, mesh_index: int = 0,
                         head_joint_name: str = "j_kao",
                         target_skeleton_path: str | Path | None = None) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("输出路径不能与源文件相同，避免覆盖原模型。")
    model = read_model(input_path)
    doc, binary = model.json, model.binary
    meshes, nodes, skins = doc.get("meshes", []), doc.get("nodes", []), doc.get("skins", [])
    if mesh_index < 0 or mesh_index >= len(meshes):
        raise ValueError(f"找不到网格索引 {mesh_index}。")
    if not skins:
        raise ValueError("模型没有 Skin，无法执行骨骼绑定。")
    mesh_nodes = [(i, node) for i, node in enumerate(nodes) if node.get("mesh") == mesh_index]
    if not mesh_nodes:
        raise ValueError(f"没有节点引用网格 {mesh_index}。")
    if len(mesh_nodes) != 1:
        raise ValueError(f"网格 {mesh_index} 被 {len(mesh_nodes)} 个节点引用；当前原型不安全地支持重复实例。")
    node_index, mesh_node = mesh_nodes[0]
    if "skin" not in mesh_node:
        raise ValueError(f"引用网格 {mesh_index} 的节点没有绑定 Skin。")
    skin_index = int(mesh_node["skin"])
    if not 0 <= skin_index < len(skins):
        raise ValueError(f"节点 {node_index} 引用了无效 Skin {skin_index}。")
    skin = skins[skin_index]
    target_binding_report = None
    if target_skeleton_path is not None:
        target_binding_report = _rebind_skin_to_target(
            model, skin_index, target_skeleton_path, head_joint_name=head_joint_name
        )
        # _rebind_skin_to_target mutates the active Skin's joint order and IBM accessor.
        skin = doc["skins"][skin_index]
    joint_nodes = skin.get("joints", [])
    matching = [i for i, node_id in enumerate(joint_nodes) if node_name(doc, int(node_id)) == head_joint_name]
    if not matching:
        raise ValueError(f"Skin {skin_index} 中找不到头部骨骼 {head_joint_name!r}。")
    head_joint_index = matching[0]
    if head_joint_index > 255:
        raise ValueError("头部骨骼索引超出当前 JOINTS_0 的 8 位索引范围。")

    primitives = meshes[mesh_index].get("primitives", [])
    if len(primitives) != 1:
        raise ValueError("当前原型要求目标网格恰好包含一个 Primitive。")
    attrs = primitives[0].get("attributes", {})
    if "JOINTS_1" in attrs or "WEIGHTS_1" in attrs:
        raise ValueError("当前原型不支持 JOINTS_1/WEIGHTS_1 的第二组蒙皮影响；为避免静默损坏模型，已停止。")
    required = ("POSITION", "JOINTS_0", "WEIGHTS_0")
    for name in required:
        if name not in attrs:
            raise ValueError(f"网格缺少必要属性 {name}。")
    pos_i, joints_i, weights_i = (int(attrs[name]) for name in required)
    pos_acc, _pos_view, pos_base, pos_stride, pos_fmt, pos_size, pos_n = accessor_layout(model, pos_i)
    joints_acc, _jv, joints_base, joints_stride, joints_fmt, joints_size, joints_n = accessor_layout(model, joints_i)
    weights_acc, _wv, weights_base, weights_stride, weights_fmt, weights_size, weights_n = accessor_layout(model, weights_i)
    if pos_acc.get("componentType") != 5126 or pos_acc.get("type") != "VEC3":
        raise ValueError("POSITION 必须是 FLOAT VEC3。")
    if joints_acc.get("componentType") != 5121 or joints_acc.get("type") != "VEC4":
        raise ValueError("当前原型要求 JOINTS_0 为 UNSIGNED_BYTE VEC4。")
    if weights_acc.get("componentType") != 5126 or weights_acc.get("type") != "VEC4":
        raise ValueError("当前原型要求 WEIGHTS_0 为 FLOAT VEC4。")
    vertex_count = int(pos_acc["count"])
    if int(joints_acc["count"]) != vertex_count or int(weights_acc["count"]) != vertex_count:
        raise ValueError("POSITION、JOINTS_0、WEIGHTS_0 的顶点数量不一致。")

    pos_stride = pos_stride or 12
    joints_stride = joints_stride or 4
    weights_stride = weights_stride or 16
    pos_min = [float("inf")] * 3
    pos_max = [float("-inf")] * 3
    for vertex in range(vertex_count):
        offset = pos_base + vertex * pos_stride
        x, y, z = struct.unpack_from("<3f", binary, offset)
        y = struct.unpack("<f", struct.pack("<f", y + y_offset))[0]
        struct.pack_into("<3f", binary, offset, x, y, z)
        pos_min = [min(pos_min[0], x), min(pos_min[1], y), min(pos_min[2], z)]
        pos_max = [max(pos_max[0], x), max(pos_max[1], y), max(pos_max[2], z)]
        joff = joints_base + vertex * joints_stride
        binary[joff:joff + 4] = bytes((head_joint_index, 0, 0, 0))
        woff = weights_base + vertex * weights_stride
        struct.pack_into("<4f", binary, woff, 1.0, 0.0, 0.0, 0.0)
    pos_acc["min"], pos_acc["max"] = pos_min, pos_max

    # Keep only the selected mesh and nodes reachable from the active scene after
    # the target skeleton has been transplanted. This prevents an importer from
    # accidentally picking an unselected source mesh (which may sit near the torso).
    hidden_nodes = [i for i, node in enumerate(nodes)
                    if "mesh" in node and int(node.get("mesh", -1)) != mesh_index]
    scenes = doc.get("scenes", [])
    for scene in scenes:
        scene["nodes"] = [int(n) for n in scene.get("nodes", []) if int(n) not in hidden_nodes]

    reachable: set[int] = set()
    stack = [int(n) for scene in scenes for n in scene.get("nodes", [])]
    while stack:
        current = stack.pop()
        if current in reachable or current in hidden_nodes:
            continue
        if not 0 <= current < len(nodes):
            raise ValueError(f"场景引用无效节点 {current}。")
        reachable.add(current)
        stack.extend(int(c) for c in nodes[current].get("children", []))
    if node_index not in reachable:
        raise ValueError("选中的网格节点在目标骨架重建后不属于活动场景，拒绝输出。")

    kept_old_ids = sorted(reachable)
    node_remap = {old: new for new, old in enumerate(kept_old_ids)}
    kept_nodes = [nodes[old] for old in kept_old_ids]
    for old_id, node in zip(kept_old_ids, kept_nodes):
        if "children" in node:
            node["children"] = [node_remap[int(child)] for child in node["children"]
                                if int(child) in node_remap]
        if "mesh" in node:
            if int(node["mesh"]) != mesh_index:
                raise ValueError("非目标网格节点意外进入活动场景。")
            node["mesh"] = 0
        if "skin" in node:
            if old_id == node_index and int(node["skin"]) == skin_index:
                node["skin"] = 0
            else:
                node.pop("skin", None)

    selected_skin = doc["skins"][skin_index]
    selected_skin["joints"] = [node_remap[int(j)] for j in selected_skin["joints"]]
    if "skeleton" in selected_skin:
        if int(selected_skin["skeleton"]) in node_remap:
            selected_skin["skeleton"] = node_remap[int(selected_skin["skeleton"])]
        else:
            selected_skin.pop("skeleton", None)
    doc["nodes"] = kept_nodes
    doc["meshes"] = [meshes[mesh_index]]
    doc["skins"] = [selected_skin]
    for scene in scenes:
        scene["nodes"] = [node_remap[int(n)] for n in scene.get("nodes", []) if int(n) in node_remap]
    for animation in doc.get("animations", []):
        for channel in animation.get("channels", []):
            target = channel.get("target", {})
            if "node" in target:
                old_target = int(target["node"])
                if old_target in node_remap:
                    target["node"] = node_remap[old_target]
                else:
                    target.pop("node", None)

    output_node_index = node_remap[node_index]
    write_glb(model, output_path)
    return {
        "input": str(input_path), "output": str(output_path),
        "mesh_index": 0, "mesh_node_index": output_node_index,
        "skin_index": 0, "vertex_count": vertex_count,
        "head_joint_name": head_joint_name, "head_joint_index": head_joint_index,
        "y_offset": y_offset, "removed_scene_mesh_nodes": hidden_nodes,
        "target_skeleton_rebind": target_binding_report,
        "warning": ("已按目标 GLB 重建活动 Skin 的骨骼层级与逆绑定矩阵；仍需 Penumbra/游戏内验证。"
                    if target_binding_report else "未提供目标骨架 GLB，当前只使用源模型骨架；不得用于正式目标种族输出。"),
    }
