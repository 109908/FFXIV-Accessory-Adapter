#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect a supplied FFXIV MDL conservatively; optional MDL-to-FBX conversion."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.backends.ffxiv_mdl_backend import (  # noqa: E402
    MdlBackendError, export_mdl_to_fbx, find_converter, probe_mdl_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 FF14 MDL 的二进制线索；不将字符串扫描冒充完整模型解析。")
    parser.add_argument("input", help="输入 .mdl 文件")
    parser.add_argument("-o", "--output", default="output/mdl_probe.json", help="JSON 报告输出路径")
    parser.add_argument("--export-fbx", help="可选：调用 FFXIVModelConverter 导出 FBX")
    parser.add_argument("--game-path", help="游戏内部相对路径，如 chara/equipment/e6047/model/c0501e6047_met.mdl")
    parser.add_argument("--converter", help="FFXIVModelConverter 可执行文件路径；也可设置 FFXIV_MODEL_CONVERTER 环境变量")
    parser.add_argument("--timeout", type=int, default=1200, help="转换超时秒数")
    args = parser.parse_args()
    try:
        report = {"probe": probe_mdl_file(args.input), "converter": {"found": bool(find_converter(args.converter)), "path": str(find_converter(args.converter)) if find_converter(args.converter) else None}}
        if args.export_fbx:
            if not args.game_path:
                parser.error("使用 --export-fbx 时必须同时提供 --game-path。")
            report["conversion"] = export_mdl_to_fbx(args.input, args.export_fbx, args.game_path, args.converter, args.timeout)
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        p = report["probe"]
        print("MDL 线索检查完成。")
        print(f"文件：{p['source_path']}")
        print(f"大小：{p['size_bytes']} bytes；SHA-256：{p['sha256']}")
        print(f"骨骼名称候选：{p['bone_name_candidate_count']}；材质引用候选：{p['material_reference_candidate_count']}")
        print(f"解析状态：{p['parser_status']}（不是完整 MDL 解析）")
        print(f"转换器：{report['converter']['path'] or '未找到'}")
        if args.export_fbx:
            print(f"FBX 输出：{report['conversion']['output_path']} ({report['conversion']['output_size_bytes']} bytes)")
        print(f"报告：{out}")
        return 0
    except (OSError, ValueError, MdlBackendError) as exc:
        print(f"检查/转换失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
