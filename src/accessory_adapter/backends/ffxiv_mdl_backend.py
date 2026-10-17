#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conservative FFXIV MDL probe and external-converter adapter.

Important: the byte/string probe is forensic triage, NOT a structural MDL parser.
It does not decode vertex buffers, mesh tables, bone indices, weights, or transforms.
For real MDL<->FBX conversion this module calls the external FFXIVModelConverter
CLI documented by its upstream project. The converter remains an optional dependency.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

# Observed at the beginning of the supplied sample MDLs. Treat as an observation,
# not as a complete/authoritative format signature.
OBSERVED_SAMPLE_PREFIX = bytes.fromhex("06 00 00 01")
_ASCII_RUN = re.compile(rb"[\x20-\x7e]{4,}")
_BONE_CANDIDATE = re.compile(r"^(?:j_[A-Za-z0-9_]+|atr_[A-Za-z0-9_]+|n_root)$")
_MATERIAL_REF = re.compile(r"/?mt_[A-Za-z0-9_]+\.mtrl", re.IGNORECASE)
_INTERNAL_MDL_PATH = re.compile(r"^(?:chara|bg|ui|vfx|common)/.+\.mdl$", re.IGNORECASE)


class MdlBackendError(RuntimeError):
    """Raised when an MDL inspection or external conversion cannot be completed."""


def probe_mdl_bytes(data: bytes, source_name: str = "<memory>", source_path: str | None = None) -> dict[str, Any]:
    """Extract safe, limited metadata from MDL bytes without claiming full parsing."""
    if not data:
        raise MdlBackendError("MDL 文件为空。")

    ascii_strings: list[str] = []
    seen_strings: set[str] = set()
    for match in _ASCII_RUN.finditer(data):
        try:
            value = match.group().decode("ascii")
        except UnicodeDecodeError:
            continue
        if value not in seen_strings:
            seen_strings.add(value)
            ascii_strings.append(value)

    bones = sorted({s for s in ascii_strings if _BONE_CANDIDATE.fullmatch(s)}, key=str.casefold)
    materials = sorted({m.lstrip("/") for s in ascii_strings for m in _MATERIAL_REF.findall(s)}, key=str.casefold)
    internal_paths = sorted({s for s in ascii_strings if _INTERNAL_MDL_PATH.fullmatch(s)}, key=str.casefold)
    prefix = data[:16]
    observed_prefix_match = data.startswith(OBSERVED_SAMPLE_PREFIX)

    return {
        "source_name": source_name,
        "source_path": source_path,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "header_prefix_hex": prefix.hex(" "),
        "matches_supplied_sample_prefix": observed_prefix_match,
        "ascii_string_count": len(ascii_strings),
        "bone_name_candidates": bones[:500],
        "bone_name_candidate_count": len(bones),
        "material_reference_candidates": materials[:200],
        "material_reference_candidate_count": len(materials),
        "internal_mdl_path_candidates": internal_paths[:100],
        "internal_mdl_path_candidate_count": len(internal_paths),
        "parser_status": "forensic_string_probe_only",
        "limitations": [
            "Not a structural FFXIV MDL parser.",
            "String presence does not prove a string is an active bone, material, or reference.",
            "Does not decode mesh tables, LODs, vertex attributes, bone indices, skin weights, or transforms.",
            "Does not establish whether the file is vanilla or modded.",
        ],
    }


def probe_mdl_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"找不到 MDL 文件：{file_path}")
    if file_path.suffix.casefold() != ".mdl":
        raise MdlBackendError(f"预期 .mdl 文件，收到：{file_path.name}")
    return probe_mdl_bytes(file_path.read_bytes(), file_path.name, str(file_path))


def find_converter(explicit_path: str | Path | None = None) -> Path | None:
    """Resolve FFXIVModelConverter executable from argument, env var, or PATH."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    env_path = os.environ.get("FFXIV_MODEL_CONVERTER")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    for executable_name in ("FFXIVModelConverter.exe", "FFXIVModelConverter"):
        found = shutil.which(executable_name)
        if found:
            return Path(found).resolve()
    return None


def _validate_game_path(game_path: str) -> str:
    clean = str(game_path).replace("\\", "/").strip("/")
    if not _INTERNAL_MDL_PATH.fullmatch(clean):
        raise MdlBackendError(
            "--game-path 必须是 FF14 游戏内部的相对 MDL 路径，例如 "
            "chara/equipment/e6047/model/c0501e6047_met.mdl；不能填写本地磁盘路径。"
        )
    return clean


def build_mdl_to_fbx_command(
    converter: str | Path,
    input_mdl: str | Path,
    output_fbx: str | Path,
    game_path: str,
) -> list[str]:
    return [
        str(Path(converter).resolve()), "mdl2fbx",
        "--input", str(Path(input_mdl).resolve()),
        "--output", str(Path(output_fbx).resolve()),
        "--game-path", _validate_game_path(game_path),
    ]


def build_fbx_to_mdl_command(
    converter: str | Path,
    input_fbx: str | Path,
    output_mdl: str | Path,
    game_path: str,
    base_model: str | Path,
    override_incoming_race: str | None = None,
) -> list[str]:
    command = [
        str(Path(converter).resolve()), "fbx2mdl",
        "--input", str(Path(input_fbx).resolve()),
        "--output", str(Path(output_mdl).resolve()),
        "--base-model", str(Path(base_model).resolve()),
        "--game-path", _validate_game_path(game_path),
    ]
    if override_incoming_race:
        command.extend(["--override-incoming-race", override_incoming_race])
    return command


def run_converter_command(
    command: Sequence[str],
    converter_path: str | Path,
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    """Run an upstream converter command and return logs; do not assume success."""
    exe = Path(converter_path).resolve()
    if not exe.is_file():
        raise FileNotFoundError(f"找不到 FFXIVModelConverter：{exe}")
    try:
        completed = subprocess.run(
            list(command), cwd=str(exe.parent), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MdlBackendError(f"模型转换超时（{timeout_seconds} 秒）。") from exc
    except OSError as exc:
        raise MdlBackendError(f"无法启动模型转换器：{exc}") from exc
    return {
        "return_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "command": list(command),
        "converter_path": str(exe),
        "working_directory": str(exe.parent),
    }


def export_mdl_to_fbx(
    input_mdl: str | Path,
    output_fbx: str | Path,
    game_path: str,
    converter_path: str | Path | None = None,
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    input_path = Path(input_mdl).expanduser().resolve()
    output_path = Path(output_fbx).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"找不到输入 MDL：{input_path}")
    converter = find_converter(converter_path)
    if converter is None:
        raise MdlBackendError(
            "未找到 FFXIVModelConverter。请下载兼容版本，并通过 --converter 或环境变量 "
            "FFXIV_MODEL_CONVERTER 指定可执行文件。转换器还需要正确配置其 settings.json。"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_mdl_to_fbx_command(converter, input_path, output_path, game_path)
    result = run_converter_command(command, converter, timeout_seconds)
    result["output_path"] = str(output_path)
    result["output_exists"] = output_path.is_file()
    result["output_size_bytes"] = output_path.stat().st_size if output_path.is_file() else None
    if result["return_code"] != 0 or not result["output_exists"]:
        raise MdlBackendError(
            "MDL→FBX 转换未通过验证。"
            f"退出码={result['return_code']}，输出存在={result['output_exists']}。"
            f" stderr: {result['stderr'][-2000:]}"
        )
    return result


def import_fbx_to_mdl(
    input_fbx: str | Path,
    output_mdl: str | Path,
    game_path: str,
    base_model: str | Path,
    converter_path: str | Path | None = None,
    override_incoming_race: str | None = None,
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    input_path = Path(input_fbx).expanduser().resolve()
    base_path = Path(base_model).expanduser().resolve()
    output_path = Path(output_mdl).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"找不到输入 FBX：{input_path}")
    if not base_path.is_file():
        raise FileNotFoundError(f"找不到目标基础 MDL：{base_path}")
    converter = find_converter(converter_path)
    if converter is None:
        raise MdlBackendError("未找到 FFXIVModelConverter，请通过 --converter 或 FFXIV_MODEL_CONVERTER 指定。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_fbx_to_mdl_command(converter, input_path, output_path, game_path, base_path, override_incoming_race)
    result = run_converter_command(command, converter, timeout_seconds)
    result["output_path"] = str(output_path)
    result["output_exists"] = output_path.is_file()
    result["output_size_bytes"] = output_path.stat().st_size if output_path.is_file() else None
    if result["return_code"] != 0 or not result["output_exists"]:
        raise MdlBackendError(
            "FBX→MDL 转换未通过验证。"
            f"退出码={result['return_code']}，输出存在={result['output_exists']}。"
            f" stderr: {result['stderr'][-2000:]}"
        )
    return result
