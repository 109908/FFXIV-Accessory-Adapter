#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only local resource scanner for folders, ZIP files and Penumbra PMP archives."""
from __future__ import annotations

import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .resource_classifier import classify_resource

SUPPORTED_ARCHIVE_SUFFIXES = {".zip", ".pmp"}
IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules"}


def normalize_relative_path(value: str) -> str:
    value = str(value).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return str(PurePosixPath(value)).strip("/").casefold()


def _choose_meta_name(names: list[str]) -> str | None:
    candidates = [n for n in names if PurePosixPath(n.replace("\\", "/")).name.casefold() == "meta.json"]
    if not candidates:
        return None
    candidates.sort(key=lambda n: (len(PurePosixPath(n.replace("\\", "/")).parts), n.casefold()))
    shallowest = len(PurePosixPath(candidates[0].replace("\\", "/")).parts)
    best = [n for n in candidates if len(PurePosixPath(n.replace("\\", "/")).parts) == shallowest]
    if len(best) > 1:
        root_level = [n for n in best if len(PurePosixPath(n.replace("\\", "/")).parts) == 1]
        if len(root_level) == 1:
            return root_level[0]
        raise ValueError("归档中存在多个同层级 meta.json，无法安全判断哪一个是 Mod 母版。")
    return best[0]


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_json(value[k]) for k in sorted(value, key=lambda x: str(x).casefold())}
    if isinstance(value, list):
        return [_normalize_json(v) for v in value]
    return value


def _load_config(meta: dict[str, Any], read_bytes: Callable[[str], bytes | None], paths: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Load active groups from classic meta.json or PMP group_*.json files."""
    warnings: list[str] = []
    direct_groups = meta.get("Groups")
    if isinstance(direct_groups, list) and direct_groups:
        return direct_groups, warnings

    group_paths = [
        p for p in paths
        if PurePosixPath(p.replace("\\", "/")).parent == PurePosixPath(".")
        and PurePosixPath(p.replace("\\", "/")).name.casefold().startswith("group_")
        and PurePosixPath(p.replace("\\", "/")).suffix.casefold() == ".json"
    ]
    groups: list[dict[str, Any]] = []
    for group_path in sorted(group_paths, key=str.casefold):
        raw = read_bytes(group_path)
        if raw is None:
            warnings.append(f"无法读取组配置：{group_path}")
            continue
        try:
            group = json.loads(raw.decode("utf-8-sig"))
            if isinstance(group, dict) and isinstance(group.get("Options"), list):
                groups.append(group)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append(f"组配置解析失败 {group_path}: {exc}")
    if not groups:
        warnings.append("没有找到可解析的 Mod 选项组；该输入可能是普通资源目录，而非完整 Mod 母版。")
    return groups, warnings


def _load_backup_groups(read_bytes: Callable[[str], bytes | None], paths: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Load .json.bak group files for diagnostics only; never treat them as active by default."""
    warnings: list[str] = []
    group_paths = [
        p for p in paths
        if PurePosixPath(p.replace("\\", "/")).parent == PurePosixPath(".")
        and PurePosixPath(p.replace("\\", "/")).name.casefold().startswith("group_")
        and PurePosixPath(p.replace("\\", "/")).name.casefold().endswith(".json.bak")
    ]
    groups: list[dict[str, Any]] = []
    for group_path in sorted(group_paths, key=str.casefold):
        raw = read_bytes(group_path)
        if raw is None:
            warnings.append(f"无法读取备份组配置：{group_path}")
            continue
        try:
            group = json.loads(raw.decode("utf-8-sig"))
            if isinstance(group, dict) and isinstance(group.get("Options"), list):
                groups.append(group)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append(f"备份组配置解析失败 {group_path}: {exc}")
    return groups, warnings


def _analyze_mod_config(meta: dict[str, Any], groups: list[dict[str, Any]], index: dict[str, str], source: str) -> dict[str, Any]:
    groups_out: list[dict[str, Any]] = []
    target_matches: list[dict[str, Any]] = []
    mapping_count = 0
    missing_count = 0
    game_paths: set[str] = set()
    source_paths: set[str] = set()
    option_count = 0

    for gi, group in enumerate(groups):
        options_out: list[dict[str, Any]] = []
        group_name = str(group.get("Name", f"Group {gi + 1}"))
        for oi, option in enumerate(group.get("Options", []) or []):
            files = option.get("Files") or {}
            file_swaps = option.get("FileSwaps") or {}
            manipulations = option.get("Manipulations") or []
            mappings = []
            mapping_count += len(files)
            option_count += 1
            for game_path, source_path in files.items():
                normalized_source = normalize_relative_path(source_path)
                resolved = index.get(normalized_source)
                exists = resolved is not None
                if not exists:
                    missing_count += 1
                game_paths.add(normalize_relative_path(game_path))
                source_paths.add(normalized_source)
                mappings.append({
                    "game_path": str(game_path).replace("\\", "/"),
                    "source_path": str(source_path).replace("\\", "/"),
                    "source_exists": exists,
                    "resolved_source_path": resolved,
                })
            option_name = str(option.get("Name", f"Option {oi + 1}"))
            option_out = {
                "index": oi,
                "id": option.get("Id"),
                "name": option_name,
                "description": option.get("Description", ""),
                "file_mapping_count": len(files),
                "file_swap_count": len(file_swaps),
                "manipulation_count": len(manipulations),
                "mappings": mappings,
                "file_swaps": file_swaps,
                "manipulations": manipulations,
            }
            options_out.append(option_out)
            searchable = f"{option_name} {option_out['description']}".casefold()
            if "elezen male" in searchable:
                target_matches.append({
                    "group_index": gi,
                    "group_name": group_name,
                    "group_type": group.get("Type", ""),
                    **option_out,
                })
        groups_out.append({
            "index": gi,
            "id": group.get("Id"),
            "name": group_name,
            "type": group.get("Type", ""),
            "option_count": len(options_out),
            "options": options_out,
        })

    return {
        "source": source,
        "mod": {
            "name": meta.get("Name", ""),
            "author": meta.get("Author", ""),
            "version": meta.get("Version", ""),
            "file_version": meta.get("FileVersion"),
            "identifier": meta.get("Identifier"),
            "description": meta.get("Description", ""),
        },
        "summary": {
            "group_count": len(groups_out),
            "option_count": option_count,
            "file_mapping_count": mapping_count,
            "unique_game_path_count": len(game_paths),
            "unique_source_path_count": len(source_paths),
            "missing_source_count": missing_count,
        },
        "target_option_matches": target_matches,
        "groups": groups_out,
    }


def _view(path: Path) -> tuple[str, list[tuple[str, int]], Callable[[str], bytes | None], list[str], dict[str, Any] | None]:
    warnings: list[str] = []
    if path.is_dir():
        all_files = [
            p for p in path.rglob("*")
            if p.is_file() and not any(part in IGNORED_DIRS for part in p.relative_to(path).parts)
        ]
        initial_names = [p.relative_to(path).as_posix() for p in all_files]
        meta_name = _choose_meta_name(initial_names)
        effective_root = path
        if meta_name:
            parent = PurePosixPath(meta_name).parent
            effective_root = path if str(parent) == "." else path / parent
            all_files = [
                p for p in effective_root.rglob("*")
                if p.is_file() and not any(part in IGNORED_DIRS for part in p.relative_to(effective_root).parts)
            ]
        index_files = {p.relative_to(effective_root).as_posix(): p for p in all_files}
        entries = [(name, p.stat().st_size) for name, p in index_files.items()]
        def read_bytes(name: str) -> bytes | None:
            item = index_files.get(name)
            return item.read_bytes() if item else None
        meta = None
        if meta_name:
            raw = read_bytes("meta.json")
            try:
                meta = json.loads(raw.decode("utf-8-sig")) if raw is not None else None
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                warnings.append(f"meta.json 解析失败：{exc}")
        return "folder", entries, read_bytes, warnings, meta

    if not path.is_file():
        raise FileNotFoundError(f"输入路径不存在：{path}")

    is_archive = path.suffix.casefold() in SUPPORTED_ARCHIVE_SUFFIXES or zipfile.is_zipfile(path)
    if is_archive:
        zf = zipfile.ZipFile(path, "r")
        names_all = [n for n in zf.namelist() if not n.endswith("/")]
        meta_name_original = _choose_meta_name(names_all)
        prefix = ""
        if meta_name_original:
            parent = PurePosixPath(meta_name_original.replace("\\", "/")).parent
            if str(parent) != ".":
                prefix = str(parent).strip("/") + "/"
        original_by_rel: dict[str, str] = {}
        for original in names_all:
            clean = original.replace("\\", "/")
            if prefix:
                if not clean.startswith(prefix):
                    continue
                rel = clean[len(prefix):]
            else:
                rel = clean
            if rel:
                original_by_rel.setdefault(rel, original)
        entries = [(rel, zf.getinfo(original).file_size) for rel, original in original_by_rel.items()]
        def read_bytes(name: str) -> bytes | None:
            original = original_by_rel.get(name)
            if original is None:
                return None
            try:
                return zf.read(original)
            except (KeyError, OSError, zipfile.BadZipFile):
                return None
        meta = None
        if meta_name_original:
            try:
                raw = read_bytes("meta.json")
                meta = json.loads(raw.decode("utf-8-sig")) if raw is not None else None
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                warnings.append(f"meta.json 解析失败：{exc}")
        read_bytes._zipfile = zf  # type: ignore[attr-defined]
        return ("pmp_archive" if path.suffix.casefold() == ".pmp" else "zip_archive"), entries, read_bytes, warnings, meta

    return "single_file", [(path.name, path.stat().st_size)], lambda name: path.read_bytes() if name == path.name else None, warnings, None


def _canonical_mapping(mapping: dict[str, Any] | None) -> dict[str, str]:
    if not mapping:
        return {}
    return {normalize_relative_path(game): normalize_relative_path(source) for game, source in mapping.items()}


def _canonical_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    canonical_groups: dict[str, Any] = {}
    for group in analysis["groups"]:
        group_key = str(group.get("name", "")).casefold()
        options: dict[str, Any] = {}
        for option in group.get("options", []):
            option_key = str(option.get("name", "")).casefold()
            options[option_key] = {
                "files": _canonical_mapping({m["game_path"]: m["source_path"] for m in option.get("mappings", [])}),
                "file_swaps": _canonical_mapping(option.get("file_swaps") or {}),
                "manipulations": _normalize_json(option.get("manipulations") or []),
            }
        canonical_groups[group_key] = {"name": group.get("name"), "type": group.get("type"), "options": options}
    return canonical_groups


def _compare_canonical(left_canonical: dict[str, Any], right_canonical: dict[str, Any], left_source: str, right_source: str) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    left_groups, right_groups = set(left_canonical), set(right_canonical)
    for group in sorted(left_groups - right_groups):
        differences.append({"kind": "group_only_in_left", "group": left_canonical[group]["name"]})
    for group in sorted(right_groups - left_groups):
        differences.append({"kind": "group_only_in_right", "group": right_canonical[group]["name"]})
    for group in sorted(left_groups & right_groups):
        if left_canonical[group]["type"] != right_canonical[group]["type"]:
            differences.append({"kind": "group_type_mismatch", "group": left_canonical[group]["name"], "left": left_canonical[group]["type"], "right": right_canonical[group]["type"]})
        ao, bo = left_canonical[group]["options"], right_canonical[group]["options"]
        for option in sorted(set(ao) - set(bo)):
            differences.append({"kind": "option_only_in_left", "group": left_canonical[group]["name"], "option": option})
        for option in sorted(set(bo) - set(ao)):
            differences.append({"kind": "option_only_in_right", "group": right_canonical[group]["name"], "option": option})
        for option in sorted(set(ao) & set(bo)):
            for field in ("files", "file_swaps", "manipulations"):
                if ao[option][field] != bo[option][field]:
                    differences.append({"kind": f"{field}_mismatch", "group": left_canonical[group]["name"], "option": option, "left": ao[option][field], "right": bo[option][field]})
    same_structure = not any(d["kind"].startswith(("group_only", "option_only", "group_type")) for d in differences)
    same_shared_mappings = not any(d["kind"] == "files_mismatch" for d in differences)
    return {
        "same_group_names": left_groups == right_groups,
        "same_group_option_structure": same_structure,
        "same_resource_mappings_for_shared_options": same_shared_mappings,
        "same_resource_mappings": same_structure and same_shared_mappings,
        "same_file_swaps": not any(d["kind"] == "file_swaps_mismatch" for d in differences),
        "same_manipulations": not any(d["kind"] == "manipulations_mismatch" for d in differences),
        "same_semantic_config": len(differences) == 0,
        "difference_count": len(differences),
        "differences": differences,
        "left_config_source": left_source,
        "right_config_source": right_source,
    }


def _compare_analyses(left_analysis: dict[str, Any], right_analysis: dict[str, Any], left_source: str, right_source: str) -> dict[str, Any]:
    return _compare_canonical(_canonical_analysis(left_analysis), _canonical_analysis(right_analysis), left_source, right_source)


def scan_input(path_value: str | Path, assigned_role: str, include_hashes: bool = False, include_mdl_probes: bool = False) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    kind, raw_entries, read_bytes, warnings, meta = _view(path)
    resources: list[dict[str, Any]] = []
    index: dict[str, str] = {}
    for rel, size in raw_entries:
        index.setdefault(normalize_relative_path(rel), rel)
        item = classify_resource(rel, assigned_role, size)
        raw = None
        if include_hashes or (include_mdl_probes and item.get("extension") == ".mdl"):
            raw = read_bytes(rel)
        if include_hashes and raw is not None:
            item["sha256"] = hashlib.sha256(raw).hexdigest()
        if include_mdl_probes and item.get("extension") == ".mdl":
            if raw is None:
                item["mdl_probe"] = {"status": "unreadable", "error": "无法读取 MDL 字节。"}
            else:
                from .backends.ffxiv_mdl_backend import probe_mdl_bytes
                item["mdl_probe"] = probe_mdl_bytes(raw, source_name=Path(rel).name, source_path=rel)
        resources.append(item)

    entry_paths = [entry[0] for entry in raw_entries]
    groups: list[dict[str, Any]] = []
    backup_groups: list[dict[str, Any]] = []
    if meta is not None:
        try:
            groups, config_warnings = _load_config(meta, read_bytes, entry_paths)
            warnings.extend(config_warnings)
            backup_groups, backup_warnings = _load_backup_groups(read_bytes, entry_paths)
            warnings.extend(backup_warnings)
        except Exception as exc:
            warnings.append(f"Mod 选项组解析失败：{exc}")

    mod_analysis = _analyze_mod_config(meta, groups, index, str(path)) if meta is not None and groups else None
    backup_analysis = _analyze_mod_config(meta, backup_groups, index, str(path) + " [backup group configs]") if meta is not None and backup_groups else None
    internal_comparison = None
    if mod_analysis and backup_analysis:
        internal_comparison = _compare_analyses(mod_analysis, backup_analysis, "active_meta", "backup_group_json")
        if not internal_comparison["same_semantic_config"]:
            warnings.append("meta.json 活动配置与 .json.bak 备份组配置存在差异；程序只报告差异，不会自动用备份覆盖活动配置。")

    extension_counts = Counter(r["extension"] or "[no extension]" for r in resources)
    type_counts = Counter(r["resource_type"] for r in resources)
    summary = {
        "input_path": str(path), "input_kind": kind, "assigned_role": assigned_role,
        "file_count": len(resources), "total_bytes": sum(int(r["size_bytes"] or 0) for r in resources),
        "extension_counts": dict(sorted(extension_counts.items())),
        "resource_type_counts": dict(sorted(type_counts.items())),
        "mdl_probe_enabled": include_mdl_probes,
        "mdl_probe_count": sum(1 for r in resources if "mdl_probe" in r),
        "warnings": warnings,
    }
    result = {
        "input_path": str(path), "input_kind": kind, "assigned_role": assigned_role,
        "summary": summary, "resources": resources, "mod_analysis": mod_analysis,
        "backup_mod_analysis": backup_analysis, "internal_config_comparison": internal_comparison,
    }
    zipfile_obj = getattr(read_bytes, "_zipfile", None)
    if zipfile_obj is not None:
        zipfile_obj.close()
    return result


def _analysis_for_source(scan: dict[str, Any], config_source: str) -> dict[str, Any]:
    if config_source == "active":
        analysis = scan.get("mod_analysis")
    elif config_source == "backup":
        analysis = scan.get("backup_mod_analysis")
    else:
        raise ValueError("config_source 只能是 active 或 backup。")
    if not analysis:
        raise ValueError(f"输入没有可解析的 {config_source} Mod 选项配置：{scan.get('input_path')}")
    return analysis


def compare_mod_configs(left_path: str | Path, right_path: str | Path, left_config_source: str = "active", right_config_source: str = "active") -> dict[str, Any]:
    left = scan_input(left_path, "mod_master")
    right = scan_input(right_path, "mod_master")
    left_analysis = _analysis_for_source(left, left_config_source)
    right_analysis = _analysis_for_source(right, right_config_source)
    comparison = _compare_analyses(left_analysis, right_analysis, left_config_source, right_config_source)
    comparison.update({
        "left": {"path": str(Path(left_path).resolve()), "name": left_analysis["mod"].get("name"), "summary": left_analysis["summary"]},
        "right": {"path": str(Path(right_path).resolve()), "name": right_analysis["mod"].get("name"), "summary": right_analysis["summary"]},
        "comparison_note": "比较选项结构、文件映射、FileSwaps 和 Manipulations；不比较归档字节、选项 ID、额外 GLB 源文件或 .bak 文件。备份配置只有显式选择 config_source=backup 时才参与比较。",
    })
    return comparison


def format_text_report(manifest: dict[str, Any]) -> str:
    lines = ["FF14 本地资源扫描报告", "=" * 32]
    for input_result in manifest["inputs"]:
        s = input_result["summary"]
        lines += ["", f"输入角色：{input_result['assigned_role']}", f"路径：{input_result['input_path']}",
                  f"类型：{input_result['input_kind']}", f"文件数：{s['file_count']}；总字节：{s['total_bytes']}",
                  "资源类型：" + ", ".join(f"{k}={v}" for k, v in s["resource_type_counts"].items())]
        if s.get("mdl_probe_enabled"):
            lines.append(f"MDL 线索扫描：{s.get('mdl_probe_count', 0)} 个（仅二进制字符串探测，不是完整 MDL 解析）")
            for resource in input_result.get("resources", []):
                probe = resource.get("mdl_probe")
                if probe:
                    lines.append(
                        f"  MDL：{resource['path']}；大小 {probe.get('size_bytes')}；"
                        f"骨骼名称候选 {probe.get('bone_name_candidate_count')}；"
                        f"材质引用候选 {probe.get('material_reference_candidate_count')}"
                    )
        if input_result.get("mod_analysis"):
            ma = input_result["mod_analysis"]
            ms = ma["summary"]
            lines += [f"Mod：{ma['mod'].get('name', '')}",
                      f"选项组：{ms['group_count']}；选项：{ms['option_count']}；映射：{ms['file_mapping_count']}",
                      f"不同游戏路径：{ms['unique_game_path_count']}；不同源路径：{ms['unique_source_path_count']}；缺失映射：{ms['missing_source_count']}",
                      f"Elezen Male 匹配：{len(ma['target_option_matches'])}"]
            for match in ma["target_option_matches"]:
                lines.append(f"  目标选项：{match['group_name']} / {match['name']}；映射 {match['file_mapping_count']} 条")
                for mapping in match["mappings"]:
                    status = "OK" if mapping["source_exists"] else "MISSING"
                    lines.append(f"    [{status}] {mapping['game_path']} <= {mapping['source_path']}")
        if input_result.get("backup_mod_analysis"):
            bms = input_result["backup_mod_analysis"]["summary"]
            lines.append(f"备份组配置：组 {bms['group_count']}；选项 {bms['option_count']}；映射 {bms['file_mapping_count']}；缺失 {bms['missing_source_count']}")
        if input_result.get("internal_config_comparison"):
            ic = input_result["internal_config_comparison"]
            lines.append(f"活动配置与备份配置一致：{ic['same_semantic_config']}；差异 {ic['difference_count']}（仅提示，不自动覆盖）")
        for warning in s["warnings"]:
            lines.append(f"警告：{warning}")
    if manifest.get("comparison"):
        c = manifest["comparison"]
        lines += ["", "Mod 配置对比", "-" * 32, f"左侧：{c['left']['name']} ({c['left_config_source']})",
                  f"右侧：{c['right']['name']} ({c['right_config_source']})",
                  f"选项结构相同：{c['same_group_option_structure']}", f"资源映射完全相同：{c['same_resource_mappings']}",
                  f"共有选项的资源映射相同：{c['same_resource_mappings_for_shared_options']}",
                  f"Manipulations 相同：{c['same_manipulations']}", f"语义配置完全相同：{c['same_semantic_config']}",
                  f"差异条数：{c['difference_count']}"]
        for d in c["differences"][:30]:
            lines.append(f"  - {d['kind']}: group={d.get('group')} option={d.get('option')}")
    lines += ["", "说明：本工具只读扫描，不会修改原文件、编译 MDL 或生成 PMP。"]
    return "\n".join(lines) + "\n"
