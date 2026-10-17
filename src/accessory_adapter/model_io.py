#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small, dependency-free GLB 2.0 reader/writer and accessor helpers.

This module deliberately does not convert FF14 MDL files. It reads/writes glTF 2.0
GLB containers and exposes the data needed by analysis/adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import struct
import base64
import mimetypes
from urllib.parse import unquote
from pathlib import Path
from typing import Any, Iterable

GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = b"JSON"
BIN_CHUNK = b"BIN\x00"

_COMPONENTS: dict[int, tuple[str, int, bool]] = {
    5120: ("b", 1, True),
    5121: ("B", 1, False),
    5122: ("h", 2, True),
    5123: ("H", 2, False),
    5125: ("I", 4, False),
    5126: ("f", 4, True),
}
_TYPE_COMPONENTS = {
    "SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
    "MAT2": 4, "MAT3": 9, "MAT4": 16,
}


@dataclass
class GLBDocument:
    """Parsed GLB. `binary` is the first embedded BIN chunk."""
    json: dict[str, Any]
    binary: bytearray
    chunks: list[tuple[bytes, bytes]]
    source_path: Path | None = None


def read_glb(path: str | Path) -> GLBDocument:
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) < 12:
        raise ValueError("文件太小，不是有效的 GLB 文件。")
    magic, version, total_length = struct.unpack_from("<4sII", raw, 0)
    if magic != GLB_MAGIC:
        raise ValueError("文件头不是 glTF；当前只支持二进制 GLB，不支持独立 .gltf JSON。")
    if version != GLB_VERSION:
        raise ValueError(f"只支持 GLB 2.0，文件版本为 {version}。")
    if total_length < 12 or total_length > len(raw):
        raise ValueError("GLB 声明长度超出文件范围，文件可能损坏。")

    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < total_length:
        if offset + 8 > total_length:
            raise ValueError("GLB chunk 头不完整。")
        chunk_length, chunk_type = struct.unpack_from("<I4s", raw, offset)
        offset += 8
        end = offset + chunk_length
        if end > total_length:
            raise ValueError("GLB chunk 数据超出文件范围。")
        chunks.append((chunk_type, raw[offset:end]))
        offset = end

    json_chunks = [data for kind, data in chunks if kind == JSON_CHUNK]
    bin_chunks = [data for kind, data in chunks if kind == BIN_CHUNK]
    if len(json_chunks) != 1:
        raise ValueError(f"GLB 应恰好包含一个 JSON chunk，实际为 {len(json_chunks)} 个。")
    if len(bin_chunks) > 1:
        raise ValueError("当前读写器暂不支持多个 BIN chunk。")
    try:
        doc = json.loads(json_chunks[0].decode("utf-8-sig").rstrip(" \t\r\n\x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"GLB JSON chunk 无法解析：{exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("GLB JSON 根对象不是字典。")
    binary = bytearray(bin_chunks[0] if bin_chunks else b"")
    return GLBDocument(doc, binary, chunks, path)


def read_model(path: str | Path) -> GLBDocument:
    """Read GLB 2.0 or standalone glTF 2.0 (.gltf) with local/data-URI buffers.

    External buffer files are packed into the in-memory BIN chunk. External image
    files are converted to data URIs so the resulting GLB remains self-contained.
    Remote URLs and multiple glTF buffers are deliberately rejected: this tool
    must not fetch network resources and its accessor layer currently supports one
    binary buffer.
    """
    path = Path(path)
    if path.suffix.casefold() == ".glb":
        return read_glb(path)
    if path.suffix.casefold() != ".gltf":
        raise ValueError(f"不支持的模型格式：{path.suffix or '无扩展名'}。请选择 .glb 或 .gltf。")
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"独立 glTF JSON 无法解析：{exc}") from exc
    if not isinstance(doc, dict) or str(doc.get("asset", {}).get("version", "")) != "2.0":
        raise ValueError("文件不是有效的 glTF 2.0 JSON。")

    def load_uri(uri: str, description: str) -> tuple[bytes, str | None]:
        if uri.startswith("data:"):
            header, sep, payload = uri.partition(",")
            if not sep:
                raise ValueError(f"{description} 的 data URI 格式无效。")
            mime = header[5:].split(";", 1)[0] or None
            try:
                if ";base64" in header:
                    return base64.b64decode(payload, validate=True), mime
                from urllib.parse import unquote_to_bytes
                return unquote_to_bytes(payload), mime
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError(f"{description} 的 data URI 解码失败。") from exc
        if "://" in uri or uri.startswith(("file:", "http:", "https:")):
            raise ValueError(f"{description} 使用外部 URL；为避免网络访问，请先把资源下载到本地并改用相对路径。")
        resource = (path.parent / unquote(uri)).resolve()
        if not resource.is_file():
            raise FileNotFoundError(f"{description} 的配套文件不存在：{resource}")
        return resource.read_bytes(), mimetypes.guess_type(resource.name)[0]

    buffers = doc.get("buffers", [])
    if len(buffers) > 1:
        raise ValueError("当前版本暂不支持包含多个 buffers 的 .gltf；请在 Penumbra 中重新导出为单一 GLB。")
    binary = bytearray()
    if buffers:
        buffer = buffers[0]
        uri = buffer.get("uri")
        if not uri:
            raise ValueError("独立 .gltf 的 buffer 缺少 uri；请检查导出是否完整。")
        data, _mime = load_uri(str(uri), "glTF buffer")
        declared = int(buffer.get("byteLength", len(data)))
        if len(data) < declared:
            raise ValueError(f"glTF buffer 实际长度 {len(data)} 小于声明长度 {declared}。")
        binary = bytearray(data[:declared])
        buffer["byteLength"] = len(binary)
        buffer.pop("uri", None)

    # Keep textures available when the user chooses a different output directory.
    for image in doc.get("images", []):
        uri = image.get("uri")
        if uri and not str(uri).startswith("data:"):
            data, mime = load_uri(str(uri), "glTF image")
            mime = mime or "application/octet-stream"
            image["uri"] = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")

    json_bytes = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    chunks: list[tuple[bytes, bytes]] = [(JSON_CHUNK, json_bytes)]
    if binary:
        chunks.append((BIN_CHUNK, bytes(binary)))
    return GLBDocument(doc, binary, chunks, path)


def write_glb(model: GLBDocument, path: str | Path) -> Path:
    """Write a GLB while preserving unknown chunks and chunk order."""
    path = Path(path)
    doc = model.json
    buffers = doc.get("buffers", [])
    if buffers:
        # Preserve the logical buffer length (the BIN chunk may include padding).
        # If views now extend past it, expand to the greatest referenced view end.
        required_length = max(
            (int(view.get("byteOffset", 0)) + int(view.get("byteLength", 0))
             for view in doc.get("bufferViews", []) if int(view.get("buffer", 0)) == 0),
            default=0,
        )
        old_length = int(buffers[0].get("byteLength", 0))
        if old_length < required_length:
            buffers[0]["byteLength"] = required_length
    json_bytes = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_bytes = bytes(model.binary)
    bin_bytes += b"\x00" * ((4 - len(bin_bytes) % 4) % 4)

    out_chunks: list[tuple[bytes, bytes]] = []
    json_written = False
    bin_written = False
    for kind, data in model.chunks:
        if kind == JSON_CHUNK and not json_written:
            out_chunks.append((JSON_CHUNK, json_bytes))
            json_written = True
        elif kind == BIN_CHUNK and not bin_written:
            out_chunks.append((BIN_CHUNK, bin_bytes))
            bin_written = True
        else:
            out_chunks.append((kind, data))
    if not json_written:
        out_chunks.insert(0, (JSON_CHUNK, json_bytes))
    if model.binary and not bin_written:
        out_chunks.append((BIN_CHUNK, bin_bytes))

    body = bytearray()
    for kind, data in out_chunks:
        body.extend(struct.pack("<I4s", len(data), kind))
        body.extend(data)
    result = struct.pack("<4sII", GLB_MAGIC, GLB_VERSION, 12 + len(body)) + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result)
    return path


def accessor_layout(model: GLBDocument, accessor_index: int) -> tuple[dict[str, Any], dict[str, Any], int, int, str, int, int]:
    doc = model.json
    accessors = doc.get("accessors", [])
    if accessor_index < 0 or accessor_index >= len(accessors):
        raise ValueError(f"Accessor 索引越界：{accessor_index}。")
    accessor = accessors[accessor_index]
    if "sparse" in accessor:
        raise ValueError(f"Accessor {accessor_index} 使用 sparse 数据，当前版本暂不支持。")
    if "bufferView" not in accessor:
        raise ValueError(f"Accessor {accessor_index} 没有 bufferView。")
    views = doc.get("bufferViews", [])
    view_index = int(accessor["bufferView"])
    if view_index < 0 or view_index >= len(views):
        raise ValueError(f"Accessor {accessor_index} 引用了无效 bufferView {view_index}。")
    view = views[view_index]
    if int(view.get("buffer", 0)) != 0:
        raise ValueError("当前 GLB 读写器只支持访问器引用第一个内嵌 buffer。")
    ctype = int(accessor["componentType"])
    if ctype not in _COMPONENTS:
        raise ValueError(f"不支持的 accessor componentType：{ctype}。")
    fmt, component_size, _ = _COMPONENTS[ctype]
    type_name = accessor["type"]
    if type_name not in _TYPE_COMPONENTS:
        raise ValueError(f"不支持的 accessor type：{type_name}。")
    component_count = _TYPE_COMPONENTS[type_name]
    element_size = component_size * component_count
    stride = int(view.get("byteStride", element_size))
    if stride < element_size or stride % component_size:
        raise ValueError(f"Accessor {accessor_index} 的 byteStride 无效：{stride}。")
    base = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor["count"])
    if base < 0 or count < 0:
        raise ValueError(f"Accessor {accessor_index} 的 offset/count 无效。")
    if count:
        last_end = base + (count - 1) * stride + element_size
    else:
        last_end = base
    view_end = int(view.get("byteOffset", 0)) + int(view["byteLength"])
    if base < int(view.get("byteOffset", 0)) or last_end > view_end or last_end > len(model.binary):
        raise ValueError(f"Accessor {accessor_index} 超出 bufferView 或 BIN 数据范围。")
    return accessor, view, base, stride, fmt, component_size, component_count


def read_accessor(model: GLBDocument, accessor_index: int, *, apply_normalization: bool = False) -> list[Any]:
    accessor, _view, base, stride, fmt, component_size, component_count = accessor_layout(model, accessor_index)
    count = int(accessor["count"])
    element_size = component_size * component_count
    normalized = bool(accessor.get("normalized", False)) and apply_normalization
    ctype = int(accessor["componentType"])
    result: list[Any] = []
    unpack_fmt = "<" + fmt * component_count
    for i in range(count):
        values = list(struct.unpack_from(unpack_fmt, model.binary, base + i * stride))
        if normalized and ctype != 5126:
            if ctype == 5120:
                values = [max(v / 127.0, -1.0) for v in values]
            elif ctype == 5121:
                values = [v / 255.0 for v in values]
            elif ctype == 5122:
                values = [max(v / 32767.0, -1.0) for v in values]
            elif ctype == 5123:
                values = [v / 65535.0 for v in values]
        result.append(values[0] if component_count == 1 else values)
    return result


def write_accessor(model: GLBDocument, accessor_index: int, values: Iterable[Any]) -> None:
    accessor, _view, base, stride, fmt, component_size, component_count = accessor_layout(model, accessor_index)
    values = list(values)
    if len(values) != int(accessor["count"]):
        raise ValueError(f"写入数量 {len(values)} 与 accessor {accessor_index} 的 count 不一致。")
    ctype = int(accessor["componentType"])
    unpack_fmt = "<" + fmt * component_count
    element_size = component_size * component_count
    for i, value in enumerate(values):
        parts = [value] if component_count == 1 else list(value)
        if len(parts) != component_count:
            raise ValueError(f"第 {i} 项应包含 {component_count} 个分量。")
        try:
            packed = struct.pack(unpack_fmt, *parts)
        except (struct.error, TypeError) as exc:
            raise ValueError(f"第 {i} 项无法写入 accessor {accessor_index}：{exc}") from exc
        offset = base + i * stride
        model.binary[offset:offset + element_size] = packed


def node_name(doc: dict[str, Any], node_index: int) -> str:
    nodes = doc.get("nodes", [])
    if node_index < 0 or node_index >= len(nodes):
        return f"<invalid-node-{node_index}>"
    return str(nodes[node_index].get("name") or f"<unnamed-node-{node_index}>")


def build_parent_map(doc: dict[str, Any]) -> dict[int, int]:
    """Return child node -> first parent node. Multiple parents are reported elsewhere."""
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(doc.get("nodes", [])):
        for child in node.get("children", []):
            child_index = int(child)
            parents.setdefault(child_index, parent_index)
    return parents


def node_hierarchy_path(doc: dict[str, Any], node_index: int) -> tuple[str, ...]:
    parents = build_parent_map(doc)
    names = [node_name(doc, node_index)]
    seen = {node_index}
    current = node_index
    while current in parents:
        current = parents[current]
        if current in seen:
            names.append("<cycle>")
            break
        seen.add(current)
        names.append(node_name(doc, current))
    return tuple(reversed(names))


def validate_glb(model: GLBDocument) -> list[str]:
    """Return structural issues; an empty list means no known issues were found."""
    doc = model.json
    errors: list[str] = []
    nodes = doc.get("nodes", [])
    meshes = doc.get("meshes", [])
    skins = doc.get("skins", [])
    scenes = doc.get("scenes", [])
    for i, node in enumerate(nodes):
        if "mesh" in node and not (0 <= int(node["mesh"]) < len(meshes)):
            errors.append(f"nodes[{i}].mesh 引用无效索引 {node['mesh']}")
        if "skin" in node and not (0 <= int(node["skin"]) < len(skins)):
            errors.append(f"nodes[{i}].skin 引用无效索引 {node['skin']}")
        for child in node.get("children", []):
            if not (0 <= int(child) < len(nodes)):
                errors.append(f"nodes[{i}].children 包含无效节点 {child}")
    for i, scene in enumerate(scenes):
        for node_index in scene.get("nodes", []):
            if not (0 <= int(node_index) < len(nodes)):
                errors.append(f"scenes[{i}].nodes 包含无效节点 {node_index}")
    for si, skin in enumerate(skins):
        for joint in skin.get("joints", []):
            if not (0 <= int(joint) < len(nodes)):
                errors.append(f"skins[{si}].joints 包含无效节点 {joint}")
        if "inverseBindMatrices" in skin:
            acc_index = int(skin["inverseBindMatrices"])
            try:
                accessor, *_ = accessor_layout(model, acc_index)
                if accessor.get("type") != "MAT4":
                    errors.append(f"skins[{si}].inverseBindMatrices accessor 不是 MAT4")
                if int(accessor.get("count", 0)) != len(skin.get("joints", [])):
                    errors.append(f"skins[{si}] 的 inverseBindMatrices 数量与 joints 数量不一致")
            except (ValueError, KeyError, IndexError) as exc:
                errors.append(f"skins[{si}].inverseBindMatrices 无效：{exc}")
    for mi, mesh in enumerate(meshes):
        for pi, primitive in enumerate(mesh.get("primitives", [])):
            attrs = primitive.get("attributes", {})
            counts: dict[str, int] = {}
            for attr_name, accessor_index in attrs.items():
                try:
                    accessor, *_ = accessor_layout(model, int(accessor_index))
                    counts[attr_name] = int(accessor["count"])
                except (ValueError, KeyError, IndexError) as exc:
                    errors.append(f"meshes[{mi}].primitives[{pi}].attributes.{attr_name} 无效：{exc}")
            if len(set(counts.values())) > 1:
                errors.append(f"meshes[{mi}].primitives[{pi}] 顶点属性 count 不一致：{counts}")
            for special in ("indices",):
                if special in primitive:
                    try:
                        accessor_layout(model, int(primitive[special]))
                    except (ValueError, KeyError, IndexError) as exc:
                        errors.append(f"meshes[{mi}].primitives[{pi}].{special} 无效：{exc}")
    return errors
