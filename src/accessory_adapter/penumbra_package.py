"""Conservative Penumbra PMP builder for the tested Elezen head-accessory workflow.

This module does not compile GLB to MDL. It accepts an MDL already imported/exported
through a model tool (e.g. Penumbra Model Import) and wires it into a copy of a classic
Penumbra PMP while preserving the original mod's files and groups.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class PackageBuildError(RuntimeError):
    pass


def _norm(value: str) -> str:
    return str(value).replace("\\", "/").lstrip("./").casefold()


def _json_load(data: bytes, source: str) -> Any:
    try:
        return json.loads(data.decode("utf-8-sig"))
    except Exception as exc:
        raise PackageBuildError(f"JSON 解析失败：{source}: {exc}") from exc


def _read_archive(path: Path) -> tuple[dict[str, bytes], dict[str, zipfile.ZipInfo]]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad:
                raise PackageBuildError(f"压缩包损坏：{bad}")
            data: dict[str, bytes] = {}
            infos: dict[str, zipfile.ZipInfo] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                key = _norm(info.filename)
                if key in data:
                    # Case-insensitive collisions are unsafe for Windows/Penumbra.
                    raise PackageBuildError(f"压缩包存在大小写冲突的重复路径：{info.filename}")
                data[info.filename.replace("\\", "/")] = zf.read(info.filename)
                infos[info.filename.replace("\\", "/")] = info
            return data, infos
    except zipfile.BadZipFile as exc:
        raise PackageBuildError(f"不是有效的 ZIP/PMP 文件：{path}") from exc


def _find_by_basename(files: dict[str, bytes], basename: str) -> str:
    matches = [p for p in files if PurePosixPath(p).name.casefold() == basename.casefold()]
    if len(matches) != 1:
        raise PackageBuildError(f"预期找到唯一的 {basename}，实际找到 {len(matches)} 个。")
    return matches[0]


def _find_template_meta(files: dict[str, bytes]) -> tuple[str, dict[str, Any]]:
    candidates = []
    for name, data in files.items():
        if PurePosixPath(name).name.casefold() == "meta.json":
            try:
                obj = json.loads(data.decode("utf-8-sig"))
            except Exception:
                continue
            if obj.get("FileVersion") == 4 and isinstance(obj.get("Groups"), list):
                candidates.append((name, obj))
    if len(candidates) != 1:
        raise PackageBuildError(f"参考 ZIP 中应有一个 FileVersion 4 meta.json，实际找到 {len(candidates)} 个。")
    return candidates[0]


def _find_template_option(meta: dict[str, Any], group_name: str, option_name: str) -> dict[str, Any]:
    groups = [g for g in meta["Groups"] if str(g.get("Name", "")).casefold() == group_name.casefold()]
    if len(groups) != 1:
        raise PackageBuildError(f"参考 ZIP 中找不到唯一选项组：{group_name}")
    options = [o for o in groups[0].get("Options", []) if str(o.get("Name", "")).casefold() == option_name.casefold()]
    if len(options) != 1:
        raise PackageBuildError(f"参考 ZIP 中找不到唯一选项：{option_name}")
    return options[0]


def _find_pmp_group(files: dict[str, bytes], group_name: str) -> tuple[str, dict[str, Any]]:
    matches = []
    for name, data in files.items():
        base = PurePosixPath(name).name.casefold()
        if not (base.startswith("group_") and base.endswith(".json")):
            continue
        obj = _json_load(data, name)
        if str(obj.get("Name", "")).casefold() == group_name.casefold():
            matches.append((name, obj))
    if len(matches) != 1:
        raise PackageBuildError(f"母版 PMP 中找不到唯一选项组：{group_name}（找到 {len(matches)} 个）")
    return matches[0]


def _resolve_source_member(archive_files: dict[str, bytes], source_path: str) -> str | None:
    key = _norm(source_path)
    for name in archive_files:
        if _norm(name) == key:
            return name
    return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compare_reference_archives(mother_pmp: Path, male_v3_zip: Path) -> dict[str, Any]:
    """Compare mother PMP's classic group files to the successful Male V3 installer ZIP."""
    base_files, _ = _read_archive(mother_pmp)
    ref_files, _ = _read_archive(male_v3_zip)
    meta_path = _find_by_basename(base_files, "meta.json")
    base_meta = _json_load(base_files[meta_path], meta_path)
    ref_meta_path, ref_meta = _find_template_meta(ref_files)
    if base_meta.get("FileVersion") != 3:
        raise PackageBuildError(f"母版 PMP 预期 FileVersion 3，实际为 {base_meta.get('FileVersion')}。")
    base_groups = {}
    for p, data in base_files.items():
        bn = PurePosixPath(p).name.casefold()
        if bn.startswith("group_") and bn.endswith(".json"):
            g = _json_load(data, p)
            base_groups[str(g.get("Name", "")).casefold()] = g
    target_group_name = "Lala + Viera (Replaces Werewolf Head)"
    if target_group_name.casefold() not in base_groups:
        raise PackageBuildError("母版 PMP 缺少预期的耳朵选项组。")
    ref_group = next((g for g in ref_meta.get("Groups", []) if str(g.get("Name", "")).casefold() == target_group_name.casefold()), None)
    if ref_group is None:
        raise PackageBuildError("男精 V3 ZIP 缺少预期的耳朵选项组。")
    base_group = base_groups[target_group_name.casefold()]
    base_options = {str(o.get("Name", "")).casefold(): o for o in base_group.get("Options", [])}
    ref_options = {str(o.get("Name", "")).casefold(): o for o in ref_group.get("Options", [])}
    compare = {}
    for name in ("Lalafell", "Viera"):
        bo, ro = base_options.get(name.casefold()), ref_options.get(name.casefold())
        if bo is None or ro is None:
            compare[name] = {"present_in_both": False}
            continue
        bfiles = {_norm(k): _norm(v) for k, v in bo.get("Files", {}).items()}
        rfiles = {_norm(k): _norm(v) for k, v in ro.get("Files", {}).items()}
        compare[name] = {
            "present_in_both": True,
            "base_file_mappings": len(bfiles),
            "reference_file_mappings": len(rfiles),
            "file_mappings_equal": bfiles == rfiles,
            "base_manipulations": len(bo.get("Manipulations", [])),
            "reference_manipulations": len(ro.get("Manipulations", [])),
            "manipulations_equal": bo.get("Manipulations", []) == ro.get("Manipulations", []),
        }
    base_option_count = sum(len(g.get("Options", [])) for g in base_groups.values())
    ref_option_count = sum(len(g.get("Options", [])) for g in ref_meta.get("Groups", []))
    return {
        "mother_pmp": str(mother_pmp),
        "reference_zip": str(male_v3_zip),
        "mother_file_version": base_meta.get("FileVersion"),
        "reference_file_version": ref_meta.get("FileVersion"),
        "mother_group_count": len(base_groups),
        "reference_group_count": len(ref_meta.get("Groups", [])),
        "mother_option_count": base_option_count,
        "reference_option_count": ref_option_count,
        "target_group": target_group_name,
        "target_group_base_options": list(base_options),
        "target_group_reference_options": list(ref_options),
        "existing_option_comparison": compare,
        "reference_elezen_male_files": _find_template_option(ref_meta, target_group_name, "Elezen Male").get("Files", {}),
        "reference_elezen_male_manipulations": _find_template_option(ref_meta, target_group_name, "Elezen Male").get("Manipulations", []),
        "notes": [
            "原始 PMP 使用 FileVersion 3 与独立 group_*.json；男精 V3 ZIP 使用 FileVersion 4 且在 meta.json 中嵌入 Groups。两者不是同一种封装结构。",
            "原 PMP 的 Lalafell/Viera 各有 40 条 Manipulations，而 V3 ZIP 对应选项各有 3 条；新 Elezen 选项遵循 V3 的 Elezen Male 规则，不继承旧 Viera 的 40 条跨种族 Manipulations。原有选项不修改。",
            "比较只核对配置语义与资源映射，不等于验证 MDL 几何内容或游戏效果。",
        ],
    }


def build_race_option_pmp(
    mother_pmp: str | Path,
    male_v3_zip: str | Path,
    modified_mdl: str | Path,
    output_pmp: str | Path,
    *,
    target_race: str = "Elezen Female",
    option_group: str = "Lala + Viera (Replaces Werewolf Head)",
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Add/replace a tested Elezen head option in a classic PMP archive.

    The MDL must already be generated by an external model importer/compiler. This
    function only builds the Penumbra option, resource mapping and PMP container.
    """
    mother_pmp, male_v3_zip, modified_mdl, output_pmp = map(Path, (mother_pmp, male_v3_zip, modified_mdl, output_pmp))
    for p in (mother_pmp, male_v3_zip, modified_mdl):
        if not p.is_file():
            raise PackageBuildError(f"输入文件不存在：{p}")
    if output_pmp.resolve() in {mother_pmp.resolve(), male_v3_zip.resolve(), modified_mdl.resolve()}:
        raise PackageBuildError("输出路径不能覆盖任何输入文件。")
    race = target_race.strip().casefold()
    race_table = {
        "elezen female": {"code": "c0601", "folder": "elezen female", "gender": "Female"},
        "elezen male": {"code": "c0501", "folder": "elezen male", "gender": "Male"},
    }
    if race not in race_table:
        raise PackageBuildError("第一版仅支持已验证的 Elezen Female / Elezen Male 头部装备流程。")
    r = race_table[race]
    expected_name = f"{r['code']}e6047_met.mdl"
    if modified_mdl.name.casefold() != expected_name.casefold():
        raise PackageBuildError(f"所选 MDL 名称应为 {expected_name}，当前为 {modified_mdl.name}。请先确认没有选错种族模型。")

    base_files, base_infos = _read_archive(mother_pmp)
    ref_files, _ = _read_archive(male_v3_zip)
    meta_path = _find_by_basename(base_files, "meta.json")
    meta = _json_load(base_files[meta_path], meta_path)
    if meta.get("FileVersion") != 3:
        raise PackageBuildError("当前构建器要求输入为经典 FileVersion 3 的 Penumbra PMP 母版。")
    ref_meta_path, ref_meta = _find_template_meta(ref_files)
    template_option = _find_template_option(ref_meta, option_group, "Elezen Male")
    template_files = template_option.get("Files", {})
    if not isinstance(template_files, dict) or not template_files:
        raise PackageBuildError("男精 V3 参考选项中没有可用的资源映射。")

    group_path, group = _find_pmp_group(base_files, option_group)
    options = group.get("Options")
    if not isinstance(options, list):
        raise PackageBuildError("目标选项组的 Options 不是列表。")
    existing_idx = next((i for i, o in enumerate(options) if str(o.get("Name", "")).casefold() == target_race.casefold()), None)
    if existing_idx is not None and not replace_existing:
        raise PackageBuildError(f"选项组中已经存在 {target_race}。")

    # Clone the existing Viera option for the expected classic option schema, then replace
    # its files and remove race-wide manipulations because the V3 Elezen Male option has none.
    base_option = next((o for o in options if str(o.get("Name", "")).casefold() == "viera"), None)
    if base_option is None:
        raise PackageBuildError("母版选项组中没有 Viera 基础选项，无法安全复制既有 Manipulations。")
    new_option = copy.deepcopy(base_option)
    new_option["Name"] = target_race
    new_option["Description"] = "Generated by FF14 Accessory Adapter v1.0; uses a precompiled MDL."
    new_option["Image"] = ""
    new_option["Priority"] = 0
    # Preserve the mother PMP's classic manipulations for existing options only. The successful
    # FileVersion 4 Male V3 option has no Manipulations, so the new race option must not inherit
    # Viera's 40 race-wide manipulations (that would alter unrelated races).
    files_map: dict[str, str] = {}
    for game_path, source_path in template_files.items():
        game_path_s = str(game_path).replace("\\", "/")
        source_path_s = str(source_path).replace("\\", "\\")
        low = game_path_s.casefold()
        if low.endswith("mt_c0101e6047_met_b.mtrl") or low.endswith("mt_c0101e6047_met_c.mtrl"):
            files_map[game_path_s] = source_path_s
    if not any(k.casefold().endswith("mt_c0101e6047_met_b.mtrl") for k in files_map):
        raise PackageBuildError("男精 V3 模板缺少预期的 _b.mtrl 映射。")
    if not any(k.casefold().endswith("mt_c0101e6047_met_c.mtrl") for k in files_map):
        raise PackageBuildError("男精 V3 模板缺少预期的 _c.mtrl 映射。")

    game_model_path = f"chara/equipment/e6047/model/{expected_name}"
    relative_source = f"{r['folder']}/chara/equipment/e6047/model/{expected_name}"
    files_map[game_model_path] = relative_source.replace("/", "\\")
    new_option["Files"] = files_map
    # Classic PMP option objects need FileSwaps and Manipulations, preserved from Viera.
    new_option.setdefault("FileSwaps", {})
    new_option["Manipulations"] = []

    if existing_idx is not None:
        options[existing_idx] = new_option
    else:
        options.append(new_option)
        # Do not change DefaultSettings: the new race option must not silently enable.

    meta["Name"] = str(meta.get("Name", "Inu Set")) + ("" if "Accessory Adapter" in str(meta.get("Name", "")) else " - Accessory Adapter")
    meta["Version"] = "1.0.0-adapter"
    meta["Description"] = str(meta.get("Description", "")) + f"\n\nGenerated test option: {target_race}. Model MDL supplied by user."

    # Write new archive by preserving all mother files, replacing only meta/group JSON and adding MDL.
    out_entries = dict(base_files)
    out_entries[meta_path] = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out_entries[group_path] = (json.dumps(group, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out_entries[relative_source] = modified_mdl.read_bytes()

    # Validate every source path in the newly generated target option resolves to a file.
    member_index = {_norm(p): p for p in out_entries}
    missing_sources = []
    for game_path, source_path in new_option["Files"].items():
        if _norm(source_path) not in member_index:
            missing_sources.append({"game_path": game_path, "source_path": source_path})
    if missing_sources:
        raise PackageBuildError("新选项存在不存在的资源源文件：" + json.dumps(missing_sources, ensure_ascii=False))

    output_pmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output_pmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for name, data in out_entries.items():
                # Directory entries aren't needed in a PMP; retain file names as in source.
                zf.writestr(name.replace("\\", "/"), data)
    except Exception as exc:
        raise PackageBuildError(f"写入 PMP 失败：{exc}") from exc

    # Re-open the finished PMP, test CRC, and verify option mapping and MDL hash.
    result_files, _ = _read_archive(output_pmp)
    check_meta_path = _find_by_basename(result_files, "meta.json")
    check_meta = _json_load(result_files[check_meta_path], check_meta_path)
    check_group_path, check_group = _find_pmp_group(result_files, option_group)
    found = [o for o in check_group["Options"] if str(o.get("Name", "")).casefold() == target_race.casefold()]
    if len(found) != 1:
        raise PackageBuildError("输出 PMP 回读后，目标选项数量不等于 1。")
    check_option = found[0]
    if check_option["Files"].get(game_model_path) != relative_source.replace("/", "\\"):
        raise PackageBuildError("输出 PMP 的目标模型映射与预期不一致。")
    if _sha256(result_files[relative_source]) != _sha256(modified_mdl.read_bytes()):
        raise PackageBuildError("输出 PMP 内的 MDL 与输入 MDL 的 SHA-256 不一致。")
    with zipfile.ZipFile(output_pmp) as zf:
        if zf.testzip():
            raise PackageBuildError("输出 PMP CRC 检查失败。")

    return {
        "output_pmp": str(output_pmp),
        "target_race": target_race,
        "game_model_path": game_model_path,
        "package_model_path": relative_source.replace("/", "\\"),
        "mdl_size": len(modified_mdl.read_bytes()),
        "mdl_sha256": _sha256(modified_mdl.read_bytes()),
        "mother_entry_count": len(base_files),
        "output_entry_count": len(result_files),
        "target_group": option_group,
        "target_group_option_count": len(check_group.get("Options", [])),
        "target_option_file_mapping_count": len(check_option.get("Files", {})),
        "target_option_manipulation_count": len(check_option.get("Manipulations", [])),
        "missing_sources": missing_sources,
        "reference_template_version": ref_meta.get("FileVersion"),
        "output_file_version": check_meta.get("FileVersion"),
        "zip_crc": "PASS",
        "mdl_byte_identity": "PASS",
        "limitations": [
            "此构建器只处理 PMP 选项、映射与封装，不修改 MDL 网格/骨骼，也不将 GLB 编译为 MDL。",
            "游戏内显示仍需在 Penumbra 中验证；结构校验通过不代表模型效果已通过。",
        ],
    }


def inspect_pmp_option_groups(mother_pmp: str | Path) -> dict[str, Any]:
    """Return option-group information from a user-supplied PMP without a reference mod."""
    mother_pmp = Path(mother_pmp)
    if not mother_pmp.is_file():
        raise PackageBuildError(f"原始母版文件不存在：{mother_pmp}")
    files, _ = _read_archive(mother_pmp)
    meta_path = _find_by_basename(files, "meta.json")
    meta = _json_load(files[meta_path], meta_path)
    version = meta.get("FileVersion")
    groups: list[dict[str, Any]] = []

    if version == 3:
        for name, data in files.items():
            base = PurePosixPath(name).name.casefold()
            if not (base.startswith("group_") and base.endswith(".json")):
                continue
            group = _json_load(data, name)
            group_name = str(group.get("Name", "")).strip()
            if not group_name:
                continue
            options = group.get("Options", [])
            if not isinstance(options, list):
                raise PackageBuildError(f"选项组 {group_name} 的 Options 不是列表。")
            groups.append({
                "name": group_name,
                "entry_path": name,
                "option_count": len(options),
                "option_names": [str(o.get("Name", "")) for o in options if isinstance(o, dict)],
            })
    elif version == 4 and isinstance(meta.get("Groups"), list):
        for index, group in enumerate(meta["Groups"]):
            if not isinstance(group, dict):
                continue
            group_name = str(group.get("Name", "")).strip()
            if not group_name:
                continue
            options = group.get("Options", [])
            if not isinstance(options, list):
                raise PackageBuildError(f"选项组 {group_name} 的 Options 不是列表。")
            groups.append({
                "name": group_name,
                "entry_path": meta_path,
                "group_index": index,
                "option_count": len(options),
                "option_names": [str(o.get("Name", "")) for o in options if isinstance(o, dict)],
            })
    else:
        raise PackageBuildError(
            f"暂不支持此 PMP 配置结构：FileVersion={version!r}。当前支持 FileVersion 3（独立 group_*.json）和 FileVersion 4（meta.json 内含 Groups）。"
        )

    if not groups:
        raise PackageBuildError("没有在母版中找到可编辑的选项组。")
    folded_names = [g["name"].casefold() for g in groups]
    if len(folded_names) != len(set(folded_names)):
        raise PackageBuildError("母版中存在重名选项组，当前版本无法安全区分；请先在 Penumbra 中整理组选项名称。")
    return {
        "mother_pmp": str(mother_pmp),
        "file_version": version,
        "meta_path": meta_path,
        "group_count": len(groups),
        "groups": groups,
    }


def build_pending_option_pmp(
    mother_pmp: str | Path,
    output_pmp: str | Path,
    *,
    adapted_glb: str | Path,
    target_base_mdl: str | Path,
    target_race: str = "Elezen Female",
    option_group: str,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Create a mapped staging PMP containing the target-race vanilla MDL.

    The adapted GLB remains an intermediate input for Penumbra's native glTF model import.
    The staging PMP must already contain the target-race MDL at a race-specific internal path
    and a Files redirection from the in-game model path to that internal MDL. Penumbra then
    imports the GLB into this mapped model and writes the compiled MDL into the mod.
    """
    mother_pmp, output_pmp, adapted_glb, target_base_mdl = map(
        Path, (mother_pmp, output_pmp, adapted_glb, target_base_mdl)
    )
    if not mother_pmp.is_file():
        raise PackageBuildError(f"原始母版文件不存在：{mother_pmp}")
    if not adapted_glb.is_file():
        raise PackageBuildError(f"请先在步骤 1 生成适配 GLB，或选择现有 GLB：{adapted_glb}")
    if not target_base_mdl.is_file():
        raise PackageBuildError(f"缺少目标种族原版装备 MDL：{target_base_mdl}")
    if target_base_mdl.suffix.casefold() != ".mdl":
        raise PackageBuildError(f"目标装备基准文件必须是 .mdl，而不是：{target_base_mdl.name}")
    if adapted_glb.suffix.casefold() != ".glb":
        raise PackageBuildError(f"此处需要步骤 1 输出的二进制 .glb 文件，当前为：{adapted_glb.name}")
    glb_bytes = adapted_glb.read_bytes()
    if len(glb_bytes) < 20 or glb_bytes[:4] != b"glTF":
        raise PackageBuildError(f"所选文件不是有效的 GLB（二进制 glTF）文件：{adapted_glb}")
    glb_version = int.from_bytes(glb_bytes[4:8], "little")
    declared_length = int.from_bytes(glb_bytes[8:12], "little")
    if glb_version != 2 or declared_length != len(glb_bytes):
        raise PackageBuildError(
            f"GLB 头部校验失败（版本={glb_version}，声明长度={declared_length}，实际长度={len(glb_bytes)}）：{adapted_glb}"
        )
    if output_pmp.resolve() in {mother_pmp.resolve(), adapted_glb.resolve(), target_base_mdl.resolve()}:
        raise PackageBuildError("输出 PMP 路径不能覆盖原始母版、适配 GLB 或目标原版 MDL。")
    if not str(target_race).strip():
        raise PackageBuildError("目标选项名称不能为空。")
    if not str(option_group).strip():
        raise PackageBuildError("请先选择需要加入目标选项的原有选项组。")

    race_table = {
        "elezen female": {"code": "c0601", "folder": "elezen female"},
        "elezen male": {"code": "c0501", "folder": "elezen male"},
    }
    race_info = race_table.get(str(target_race).strip().casefold())
    if race_info is None:
        raise PackageBuildError("第一版仅支持 Elezen Female / Elezen Male。")
    # The input filename is not authoritative: TTMP2 mods often rename extracted
    # models (e.g. yuananjing_ear.mdl). Infer the actual item path from the original
    # mod's Files mappings, then create the target-race game filename from that path.
    target_mdl_bytes = target_base_mdl.read_bytes()
    if len(target_mdl_bytes) < 16:
        raise PackageBuildError(f"目标原版 MDL 文件过小，疑似不是有效模型：{target_base_mdl}")

    base_files, _ = _read_archive(mother_pmp)
    meta_path = _find_by_basename(base_files, "meta.json")
    meta = _json_load(base_files[meta_path], meta_path)
    version = meta.get("FileVersion")
    changed_path: str
    group: dict[str, Any]
    options: list[Any]

    if version == 3:
        changed_path, group = _find_pmp_group(base_files, option_group)
        options = group.get("Options")
        if not isinstance(options, list):
            raise PackageBuildError(f"选项组 {option_group} 的 Options 不是列表。")
    elif version == 4 and isinstance(meta.get("Groups"), list):
        matched = [(i, g) for i, g in enumerate(meta["Groups"])
                   if isinstance(g, dict) and str(g.get("Name", "")).casefold() == option_group.casefold()]
        if len(matched) != 1:
            raise PackageBuildError(f"母版中找不到唯一选项组：{option_group}（找到 {len(matched)} 个）")
        group_index, group = matched[0]
        changed_path = meta_path
        options = group.get("Options")
        if not isinstance(options, list):
            raise PackageBuildError(f"选项组 {option_group} 的 Options 不是列表。")
    else:
        raise PackageBuildError(
            f"暂不支持此 PMP 配置结构：FileVersion={version!r}。当前支持 FileVersion 3 和 4。"
        )

    # Infer the model resource from the selected option group's existing mappings.
    # Normalize race-specific model names so multiple race variants count as one item.
    model_paths: set[str] = set()
    for source_option in options:
        if not isinstance(source_option, dict):
            continue
        files_map = source_option.get("Files", {})
        if not isinstance(files_map, dict):
            continue
        for source_path in files_map.keys():
            normalized = str(source_path).replace("\\", "/").strip("/")
            lower = normalized.casefold()
            if lower.endswith(".mdl") and "/model/" in lower and (
                "/accessory/" in lower or "/equipment/" in lower or "/weapon/" in lower
            ):
                model_paths.add(normalized)
    if not model_paths:
        raise PackageBuildError(
            f"选项组“{option_group}”中没有可识别的装备/饰品 MDL 路径。"
            "请确保原 Mod 的 Files 映射已导入；不能仅凭重命名后的 MDL 文件名推断游戏路径。"
        )
    # Collapse e.g. c0101a0047_ear.mdl and c1101a0047_ear.mdl to the same model family.
    families: dict[str, str] = {}
    for source_path in sorted(model_paths):
        parts = source_path.split("/")
        basename = parts[-1]
        if len(basename) >= 6 and basename[0].casefold() == "c" and basename[1:5].isdigit():
            canonical_name = basename[5:]
        else:
            canonical_name = basename
        canonical = "/".join(parts[:-1] + [canonical_name]).casefold()
        families.setdefault(canonical, source_path)
    if len(families) != 1:
        raise PackageBuildError(
            f"选项组“{option_group}”包含 {len(families)} 个不同的模型资源，无法自动判断要适配哪一个。"
            "请先将原 Mod 整理为单一目标饰品/装备，或提供对应资源路径选择功能。"
        )
    source_model_path = next(iter(families.values()))
    source_parts = source_model_path.split("/")
    source_basename = source_parts[-1]
    # Keep the item's directory (a0047/e6047/etc.) and model suffix, replacing only
    # the race/gender prefix. For custom filenames, infer the standard target filename
    # from the resource folder ID plus the suffix (e.g. yuananjing_ear.mdl -> c0501a0047_ear.mdl).
    if len(source_basename) >= 6 and source_basename[0].casefold() == "c" and source_basename[1:5].isdigit():
        target_basename = race_info["code"] + source_basename[5:]
    else:
        item_id = source_parts[-3] if len(source_parts) >= 3 else ""
        suffix_match = re.search(r"(_[^/]+\.mdl)$", source_basename, flags=re.IGNORECASE)
        if item_id and re.fullmatch(r"[ae]\d{4}", item_id, flags=re.IGNORECASE) and suffix_match:
            target_basename = race_info["code"] + item_id + suffix_match.group(1)
        else:
            raise PackageBuildError(
                f"无法从原 Mod 路径推导目标种族 MDL 文件名：{source_model_path}。"
                "请检查该选项组的 Files 映射。"
            )
    game_model_path = "/".join(source_parts[:-1] + [target_basename])
    package_model_path = "/".join([race_info["folder"]] + game_model_path.split("/"))

    target_folded = target_race.casefold()
    existing_indices = [i for i, option in enumerate(options)
                        if isinstance(option, dict) and str(option.get("Name", "")).casefold() == target_folded]
    if len(existing_indices) > 1:
        raise PackageBuildError(f"选项组内存在多个同名选项：{target_race}，无法安全替换。")
    if existing_indices and not replace_existing:
        raise PackageBuildError(
            f"选项组“{option_group}”中已存在“{target_race}”。如需重建空白待绑定选项，请勾选替换；注意会清空该选项现有映射。"
        )

    if existing_indices:
        template = options[existing_indices[0]]
    elif options:
        template = next((o for o in options if isinstance(o, dict)), None)
    else:
        template = None

    if template is None:
        # Standard Penumbra option shape for an empty group.
        new_option: dict[str, Any] = {
            "Files": {}, "FileSwaps": {}, "Manipulations": [],
            "Priority": 0, "Name": target_race, "Description": "",
            "Image": "",
        }
    else:
        new_option = copy.deepcopy(template)
        new_option["Name"] = target_race
        new_option["Description"] = (
            "待绑定选项：导入此 PMP 后，在 Penumbra 中选择目标游戏资源路径并导入适配后的 GLB，然后保存。"
        )
        new_option["Image"] = ""
        new_option["Priority"] = 0
        # Critical: never clone mappings or manipulations from an unrelated option.
        new_option["Files"] = {}
        new_option["FileSwaps"] = {}
        new_option["Manipulations"] = []

    # Crucial: the staging option must already redirect the game model path to a real
    # target-race MDL. The user will import the adapted GLB into this model in Penumbra.
    new_option["Files"] = {game_model_path: package_model_path.replace("/", "\\")}
    new_option["FileSwaps"] = {}
    new_option["Manipulations"] = []

    if existing_indices:
        options[existing_indices[0]] = new_option
    else:
        options.append(new_option)

    out_entries = dict(base_files)
    if version == 3:
        out_entries[changed_path] = (json.dumps(group, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    else:
        out_entries[meta_path] = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out_entries[package_model_path] = target_mdl_bytes

    output_pmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output_pmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for name, data in out_entries.items():
                zf.writestr(name.replace("\\", "/"), data)
    except Exception as exc:
        raise PackageBuildError(f"写入待绑定 PMP 失败：{exc}") from exc

    result_files, _ = _read_archive(output_pmp)
    if version == 3:
        check_group_path, check_group = _find_pmp_group(result_files, option_group)
    else:
        check_meta_path = _find_by_basename(result_files, "meta.json")
        check_meta = _json_load(result_files[check_meta_path], check_meta_path)
        found_groups = [g for g in check_meta.get("Groups", [])
                        if isinstance(g, dict) and str(g.get("Name", "")).casefold() == option_group.casefold()]
        if len(found_groups) != 1:
            raise PackageBuildError("输出 PMP 回读后找不到唯一目标选项组。")
        check_group = found_groups[0]
    found_options = [o for o in check_group.get("Options", [])
                     if isinstance(o, dict) and str(o.get("Name", "")).casefold() == target_folded]
    if len(found_options) != 1:
        raise PackageBuildError("输出 PMP 回读后，目标选项数量不等于 1。")
    checked_option = found_options[0]
    expected_source = package_model_path.replace("/", "\\")
    if checked_option.get("Files", {}).get(game_model_path) != expected_source:
        raise PackageBuildError("输出 PMP 的目标游戏模型路径未正确映射到目标种族 MDL。")
    if checked_option.get("FileSwaps", {}) or checked_option.get("Manipulations", []):
        raise PackageBuildError("输出 PMP 意外继承了其他选项的 FileSwaps/Manipulations。")
    if _sha256(result_files[package_model_path]) != _sha256(target_mdl_bytes):
        raise PackageBuildError("输出 PMP 中的目标 MDL 与输入的原版 MDL 不一致。")
    with zipfile.ZipFile(output_pmp, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise PackageBuildError(f"输出 PMP CRC 检查失败：{bad}")

    return {
        "output_pmp": str(output_pmp),
        "mother_pmp": str(mother_pmp),
        "file_version": version,
        "target_race_option": target_race,
        "option_group": option_group,
        "group_option_count": len(check_group.get("Options", [])),
        "target_option_files_count": len(checked_option.get("Files", {})),
        "target_option_fileswaps_count": len(checked_option.get("FileSwaps", {})),
        "target_option_manipulations_count": len(checked_option.get("Manipulations", [])),
        "game_model_path": game_model_path,
        "package_model_path": expected_source,
        "target_base_mdl": str(target_base_mdl.resolve()),
        "target_base_mdl_size": len(target_mdl_bytes),
        "target_base_mdl_sha256": _sha256(target_mdl_bytes),
        "target_base_mdl_copied": True,
        "adapted_glb": str(adapted_glb.resolve()),
        "adapted_glb_size": len(glb_bytes),
        "adapted_glb_version": glb_version,
        "adapted_glb_sha256": _sha256(glb_bytes),
        "adapted_glb_validation": "PASS",
        "adapted_glb_embedded_in_pmp": False,
        "target_base_mdl_added_to_pmp": True,
        "resource_mapping_added": True,
        "zip_crc": "PASS",
        "manual_penumbra_steps": [
            "步骤 1 先生成适配 GLB；本次构建已校验该文件存在且具有 GLB 文件头。",
            "在 Penumbra 中导入此待绑定 PMP。",
            "进入刚创建的目标种族选项，并打开 Advanced Editing → Models。",
            f"选择已映射的模型资源 {game_model_path}（包内路径为 {expected_source}）。",
            "在该模型的 Import/Export 区域导入步骤 1 生成的适配 GLB；不要把 GLB 当作游戏资源映射文件。",
            "由 Penumbra 将导入模型保存为该选项中的游戏 MDL，再保存/导出最终 PMP。",
            "重新打开最终 PMP，确认目标 MDL 哈希已不同于原版基准，并在游戏中验证耳朵位置、材质与显示。",
        ],
        "limitations": [
            "成功案例 ZIP 不是必需输入；该构建器只从用户自己的母版读取配置结构。",
            "适配 GLB 是必需输入并会记录路径、大小和 SHA-256；它不会直接作为游戏资源映射。",
            "输出包含目标种族原版 MDL 占位文件和正确的 Files 映射；它尚未包含导入适配 GLB 后编译出的最终 MDL。",
            "当前仅支持 FileVersion 3 的独立 group_*.json 结构，以及 FileVersion 4 的 meta.json/Groups 结构。",
            "静态检查通过不代表 Penumbra 中的手动绑定或游戏内模型效果已验证。",
        ],
    }
