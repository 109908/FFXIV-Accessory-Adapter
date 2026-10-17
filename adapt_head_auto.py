"""CLI: calculate j_kao height delta from source/target reference GLBs and adapt the source Mod GLB."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from accessory_adapter.workflow import adapt_head_using_references  # noqa: E402

def main() -> int:
    p = argparse.ArgumentParser(description='自动计算头部高度差并生成头部附件适配 GLB（测试原型）。')
    p.add_argument('--source-mod', required=True, help='Inu 源 Mod GLB')
    p.add_argument('--source-reference', required=True, help='源种族头部参考 GLB')
    p.add_argument('--target-body', required=True, help='目标种族身体/骨架 GLB')
    p.add_argument('-o', '--output', required=True, help='输出适配 GLB')
    p.add_argument('--mesh-index', type=int, default=0)
    p.add_argument('--head-joint', default='j_kao')
    args = p.parse_args()
    try:
        result = adapt_head_using_references(args.source_mod, args.source_reference, args.target_body,
                                             args.output, mesh_index=args.mesh_index,
                                             head_joint_name=args.head_joint)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        Path(args.output).with_suffix('.adapt-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f'适配失败：{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
