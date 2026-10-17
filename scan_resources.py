#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI wrapper for local resource collection and optional Mod config comparison."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.input_scanner import scan_input, compare_mod_configs, format_text_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描本地 FF14/ Penumbra 资源目录、ZIP 和 PMP；只读生成清单。")
    parser.add_argument("--mod", action="append", default=[], help="Mod 母版文件夹、ZIP 或 PMP；可重复指定。")
    parser.add_argument("--source", action="append", default=[], help="源种族参考资源文件夹或文件；可重复指定。")
    parser.add_argument("--target-item", action="append", default=[], help="目标种族原版装备资源目录或文件；可重复指定。")
    parser.add_argument("--target-body", action="append", default=[], help="目标种族身体/骨架资源目录或文件；可重复指定。")
    parser.add_argument("--compare-mod", help="可选：与 --mod 的第一个输入比较 Mod 选项和资源映射。")
    parser.add_argument("--compare-left-source", choices=["active", "backup"], default="active", help="比较左侧配置来源；backup 仅在存在 .json.bak 时可用。")
    parser.add_argument("--compare-right-source", choices=["active", "backup"], default="active", help="比较右侧配置来源；backup 仅在存在 .json.bak 时可用。")
    parser.add_argument("-o", "--output", default="output/resource_manifest.json", help="JSON 清单输出路径。")
    parser.add_argument("--hash", action="store_true", help="计算每个资源的 SHA-256；大目录可能耗时。")
    parser.add_argument("--probe-mdl", action="store_true", help="对扫描到的 .mdl 做只读二进制字符串线索扫描；不是完整 MDL 解析。")
    args = parser.parse_args()

    specs = [("mod_master", p) for p in args.mod]
    specs += [("source_reference", p) for p in args.source]
    specs += [("target_equipment_reference", p) for p in args.target_item]
    specs += [("target_body_skeleton_reference", p) for p in args.target_body]
    if not specs:
        parser.error("至少提供一个输入，例如 --mod <Mod文件夹或归档>。")

    try:
        inputs = [scan_input(path, role, include_hashes=args.hash, include_mdl_probes=args.probe_mdl) for role, path in specs]
        comparison = None
        if args.compare_mod:
            if not args.mod:
                parser.error("使用 --compare-mod 时，必须同时指定 --mod。")
            comparison = compare_mod_configs(args.mod[0], args.compare_mod, args.compare_left_source, args.compare_right_source)
        manifest = {
            "schema_version": 1,
            "tool": "FF14-Accessory-Adapter resource scanner",
            "read_only": True,
            "inputs": inputs,
            "comparison": comparison,
        }
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        text_path = out.with_suffix(".txt")
        text_path.write_text(format_text_report(manifest), encoding="utf-8")
        print("本地资源扫描完成（只读，没有修改输入文件）。")
        for item in inputs:
            s = item["summary"]
            print(f"[{item['assigned_role']}] {item['input_path']}")
            print(f"  类型={item['input_kind']} 文件={s['file_count']} 总字节={s['total_bytes']}")
            if item.get("mod_analysis"):
                ms = item["mod_analysis"]["summary"]
                print(f"  选项组={ms['group_count']} 选项={ms['option_count']} 映射={ms['file_mapping_count']} 缺失={ms['missing_source_count']} Elezen Male={len(item['mod_analysis']['target_option_matches'])}")
            if args.probe_mdl:
                print(f"  MDL 线索扫描数={s.get('mdl_probe_count', 0)}（不等于完整结构解析）")
        if comparison:
            print(f"配置对比：same_semantic_config={comparison['same_semantic_config']}，差异={comparison['difference_count']}")
        print(f"JSON：{out}")
        print(f"TXT ：{text_path}")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"扫描失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
