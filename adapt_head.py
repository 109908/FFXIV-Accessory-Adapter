#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convenience CLI for the current head-accessory GLB adapter."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.adapters.head import adapt_head_accessory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="对指定 GLB 执行当前耳朵适配规则。")
    parser.add_argument("input", help="输入 GLB")
    parser.add_argument("-o", "--output", required=True, help="输出 GLB；不会覆盖输入")
    parser.add_argument("--mesh-index", type=int, default=0)
    parser.add_argument("--head-joint", default="j_kao")
    parser.add_argument("--y-offset", type=float, default=0.2545)
    parser.add_argument("--target-skeleton", help="目标种族骨架参考 GLB/GLTF；正式适配时建议提供")
    args = parser.parse_args()
    try:
        result = adapt_head_accessory(args.input, args.output, args.y_offset, args.mesh_index, args.head_joint, target_skeleton_path=args.target_skeleton)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"适配失败：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
