"""CLI entry point for creating a generic Penumbra staging PMP."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from accessory_adapter.penumbra_package import PackageBuildError, build_pending_option_pmp, inspect_pmp_option_groups


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate adapted GLB and target-race vanilla MDL, then create a mapped staging PMP for Penumbra glTF import."
    )
    parser.add_argument("--mother", required=True, help="Original Penumbra .pmp")
    parser.add_argument("--adapted-glb", required=True, help="Adapted .glb produced by Step 1; must exist before PMP staging")
    parser.add_argument("--target-base-mdl", help="Required target-race vanilla MDL, e.g. c0601e6047_met.mdl")
    parser.add_argument("--output", help="Output staging .pmp path (required unless --list-groups)")
    parser.add_argument("--race", default="Elezen Female", choices=("Elezen Female", "Elezen Male"))
    parser.add_argument("--group", help="Existing option group name to receive the target-race option")
    parser.add_argument("--replace-existing", action="store_true", help="Replace an existing target option and clear its mappings (destructive for that option)")
    parser.add_argument("--list-groups", action="store_true", help="List groups in the mother PMP and exit")
    args = parser.parse_args()
    try:
        if args.list_groups:
            result = inspect_pmp_option_groups(args.mother)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if not args.output:
            parser.error("构建 PMP 时必须指定 --output。")
        if not args.group:
            parser.error("构建 PMP 时必须通过 --group 指定要添加选项的原有组选项名。")
        if not args.target_base_mdl:
            parser.error("构建 PMP 时必须通过 --target-base-mdl 指定目标种族原版 MDL。")
        result = build_pending_option_pmp(
            args.mother, args.output, adapted_glb=args.adapted_glb,
            target_base_mdl=args.target_base_mdl, target_race=args.race, option_group=args.group,
            replace_existing=args.replace_existing,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        Path(args.output).with_suffix(".build-report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0
    except (PackageBuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
