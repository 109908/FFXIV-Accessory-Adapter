#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读解析 Penumbra Mod 文件夹、ZIP 或 PMP 归档。

本程序只生成 JSON/TXT 检查报告；不会修改原 Mod、编译 MDL 或生成 PMP。
仅使用 Python 标准库。
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


def norm_rel(value: str) -> str:
    value = str(value).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return str(PurePosixPath(value)).strip("/").casefold()


def load_archive(path: Path) -> tuple[dict[str, Any], dict[str, str], str]:
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        meta_names = [
            n for n in names
            if n.replace("\\", "/").casefold() == "meta.json"
            or n.replace("\\", "/").casefold().endswith("/meta.json")
        ]
        if len(meta_names) != 1:
            raise ValueError(f"归档中应恰好有一个 meta.json，实际找到 {len(meta_names)} 个。")
        meta_name = meta_names[0]
        meta = json.loads(archive.read(meta_name).decode("utf-8-sig"))
        clean_meta = meta_name.replace("\\", "/")
        root_prefix = clean_meta.rsplit("/", 1)[0] if "/" in clean_meta else ""
        prefix = root_prefix + "/" if root_prefix else ""
        index: dict[str, str] = {}
        for name in names:
            clean = name.replace("\\", "/")
            if prefix:
                if not clean.startswith(prefix):
                    continue
                relative = clean[len(prefix):]
            else:
                relative = clean
            if relative and not relative.endswith("/"):
                index.setdefault(norm_rel(relative), relative)
        return meta, index, meta_name


def load_folder(path: Path) -> tuple[dict[str, Any], dict[str, str], str]:
    root = path if path.is_dir() else path.parent
    meta_path = root / "meta.json"
    if not meta_path.is_file():
        matches = list(root.rglob("meta.json"))
        if len(matches) != 1:
            raise FileNotFoundError(
                f"在 {root} 中找不到唯一的 meta.json。请选择 Mod 根目录或 ZIP/PMP 文件。"
            )
        meta_path = matches[0]
        root = meta_path.parent
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    index: dict[str, str] = {}
    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path != meta_path:
            rel = file_path.relative_to(root).as_posix()
            index.setdefault(norm_rel(rel), rel)
    return meta, index, str(meta_path)


def analyze(meta: dict[str, Any], index: dict[str, str], source: str) -> dict[str, Any]:
    groups_out = []
    target_matches = []
    mapping_count = 0
    missing_count = 0
    game_paths: set[str] = set()
    source_paths: set[str] = set()

    for gi, group in enumerate(meta.get("Groups", [])):
        options_out = []
        for oi, option in enumerate(group.get("Options", [])):
            files = option.get("Files") or {}
            manipulations = option.get("Manipulations") or []
            mappings = []
            mapping_count += len(files)

            for game_path, source_path in files.items():
                resolved = index.get(norm_rel(source_path))
                exists = resolved is not None
                missing_count += 0 if exists else 1
                game_paths.add(str(game_path))
                source_paths.add(str(source_path))
                mappings.append({
                    "game_path": str(game_path).replace("\\", "/"),
                    "source_path": str(source_path).replace("\\", "/"),
                    "source_exists": exists,
                    "resolved_source_path": resolved,
                })

            item = {
                "index": oi,
                "id": option.get("Id"),
                "name": option.get("Name", ""),
                "description": option.get("Description", ""),
                "file_mapping_count": len(files),
                "manipulation_count": len(manipulations),
                "mappings": mappings,
                "manipulations": manipulations,
            }
            options_out.append(item)

            searchable = " ".join([
                str(group.get("Name", "")),
                str(option.get("Name", "")),
                str(option.get("Description", "")),
            ]).casefold()
            if "elezen male" in searchable:
                target_matches.append({
                    "group_index": gi,
                    "group_name": group.get("Name", ""),
                    "group_type": group.get("Type", ""),
                    **item,
                })

        groups_out.append({
            "index": gi,
            "id": group.get("Id"),
            "name": group.get("Name", ""),
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
            "option_count": sum(g["option_count"] for g in groups_out),
            "file_mapping_count": mapping_count,
            "unique_game_path_count": len(game_paths),
            "unique_source_path_count": len(source_paths),
            "missing_source_count": missing_count,
        },
        "target_option_matches": target_matches,
        "groups": groups_out,
    }


def text_report(report: dict[str, Any]) -> str:
    mod, summary = report["mod"], report["summary"]
    lines = [
        "Penumbra Mod 结构检查报告",
        "=" * 32,
        f"输入：{report['source']}",
        f"Mod 名称：{mod.get('name', '')}",
        f"作者：{mod.get('author', '')}",
        f"版本：{mod.get('version', '')}",
        "",
        "总体统计",
        "-" * 32,
        f"选项组：{summary['group_count']}",
        f"选项总数：{summary['option_count']}",
        f"资源映射总数：{summary['file_mapping_count']}",
        f"不同游戏路径：{summary['unique_game_path_count']}",
        f"不同源文件路径：{summary['unique_source_path_count']}",
        f"未找到的源文件映射：{summary['missing_source_count']}",
        "",
        "选项组与资源映射",
        "-" * 32,
    ]
    for group in report["groups"]:
        lines.append(f"[{group['index']}] {group['name']} ({group['type']})")
        for option in group["options"]:
            lines.append(
                f"  - {option['name']} | 文件映射 {option['file_mapping_count']} | "
                f"Manipulations {option['manipulation_count']} | ID {option.get('id')}"
            )
            for m in option["mappings"]:
                status = "OK" if m["source_exists"] else "MISSING"
                lines.append(f"      [{status}] {m['game_path']} <= {m['source_path']}")
        lines.append("")

    lines += ["Elezen Male 匹配结果", "-" * 32]
    if not report["target_option_matches"]:
        lines.append("没有找到名称或说明中包含 'Elezen Male' 的选项。")
    for match in report["target_option_matches"]:
        lines.append(
            f"组：{match['group_name']} / 选项：{match['name']} "
            f"(组索引 {match['group_index']}，选项索引 {match['index']})"
        )
        if match.get("description"):
            lines.append(f"说明：{match['description']}")
        for m in match["mappings"]:
            status = "OK" if m["source_exists"] else "MISSING"
            lines.append(f"  [{status}] {m['game_path']} <= {m['source_path']}")
    lines += ["", "注意：这是只读报告；没有修改 Mod、编译 MDL 或生成 PMP。"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读解析 Penumbra Mod 文件夹、ZIP 或 PMP，生成资源映射检查报告。"
    )
    parser.add_argument("input", help="Mod 根目录、ZIP 或 PMP 文件路径")
    parser.add_argument(
        "-o", "--output-dir",
        help="报告输出目录；默认写入当前目录 output/mod_analysis",
    )
    args = parser.parse_args()
    input_path = Path(args.input.strip('"')).expanduser()
    if not input_path.exists():
        parser.error(f"找不到输入路径：{input_path}")

    try:
        if input_path.is_file() and (
            input_path.suffix.casefold() in {".zip", ".pmp"} or zipfile.is_zipfile(input_path)
        ):
            meta, index, source = load_archive(input_path)
        else:
            meta, index, source = load_folder(input_path)

        report = analyze(meta, index, source)
        out_dir = Path(args.output_dir).expanduser() if args.output_dir else Path.cwd() / "output" / "mod_analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "mod_analysis_report.json"
        txt_path = out_dir / "mod_analysis_report.txt"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path.write_text(text_report(report), encoding="utf-8")

        print("Mod 结构分析完成（只读，没有修改源文件）。")
        print(f"Mod：{meta.get('Name', '')}")
        print(f"选项组：{report['summary']['group_count']}；选项：{report['summary']['option_count']}")
        print(f"资源映射：{report['summary']['file_mapping_count']}；缺失源文件：{report['summary']['missing_source_count']}")
        print(f"Elezen Male 匹配数：{len(report['target_option_matches'])}")
        print(f"JSON 报告：{json_path.resolve()}")
        print(f"文本报告：{txt_path.resolve()}")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"分析失败：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
