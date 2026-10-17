"""High-level tested workflow for the current head-only Elezen adaptation."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .adapters.head import adapt_head_accessory
from .skeleton_reference import inspect_glb


def _head_world_y(path: str | Path, joint_name: str = 'j_kao') -> float:
    report = inspect_glb(path)
    for skin in report.get('skins', []):
        for joint in skin.get('head_chain', []):
            if joint.get('name') == joint_name:
                return float(joint['world_translation'][1])
    raise ValueError(f"{Path(path).name} 的 Skin 中找不到 {joint_name} 的世界 Y 坐标。")


def adapt_head_using_references(
    source_mod_glb: str | Path,
    source_reference_glb: str | Path,
    target_body_glb: str | Path,
    output_glb: str | Path,
    *, mesh_index: int = 0,
    head_joint_name: str = 'j_kao',
    target_skeleton_glb: str | Path | None = None,
) -> dict[str, Any]:
    """Calculate source-to-target head-height delta, then run the tested head prototype.

    The resulting GLB is an intermediate file. It still must be imported/compiled to MDL
    using a compatible FFXIV model tool before packaging into PMP.
    """
    source_mod_glb, source_reference_glb, target_body_glb, output_glb = map(
        Path, (source_mod_glb, source_reference_glb, target_body_glb, output_glb)
    )
    for p in (source_mod_glb, source_reference_glb, target_body_glb):
        if not p.is_file():
            raise FileNotFoundError(f"输入文件不存在：{p}")
    if output_glb.resolve() in {source_mod_glb.resolve(), source_reference_glb.resolve(), target_body_glb.resolve(), Path(target_skeleton_glb).resolve() if target_skeleton_glb else target_body_glb.resolve()}:
        raise ValueError('输出 GLB 不能覆盖任何输入文件。')
    skeleton_reference = Path(target_skeleton_glb) if target_skeleton_glb else target_body_glb
    if not skeleton_reference.is_file():
        raise FileNotFoundError(f"目标骨架参考文件不存在：{skeleton_reference}")
    if skeleton_reference.suffix.casefold() not in ('.glb', '.gltf'):
        raise ValueError('目标骨架参考必须是可读取的 .glb/.gltf；MDL 不能直接作为骨架重定向输入。')
    source_y = _head_world_y(source_reference_glb, head_joint_name)
    target_y = _head_world_y(skeleton_reference, head_joint_name)
    delta = target_y - source_y
    adapted = adapt_head_accessory(
        source_mod_glb, output_glb, y_offset=delta,
        mesh_index=mesh_index, head_joint_name=head_joint_name,
        target_skeleton_path=skeleton_reference,
    )
    return {
        'source_mod_glb': str(source_mod_glb.resolve()),
        'source_reference_glb': str(source_reference_glb.resolve()),
        'target_body_glb': str(target_body_glb.resolve()),
        'target_skeleton_glb': str(skeleton_reference.resolve()),
        'output_glb': str(output_glb.resolve()),
        'head_joint_name': head_joint_name,
        'source_head_world_y': source_y,
        'target_head_world_y': target_y,
        'calculated_y_offset': delta,
        'adapter_result': adapted,
        'next_step': '将此适配 GLB 传递到步骤 2；程序验证 GLB 后基于用户自己的母版创建待绑定 PMP，再在步骤 3 的 Penumbra 中导入 GLB、绑定目标游戏资源路径并保存最终 PMP。',
        'limitations': [
            '当前只支持已测试的头部耳朵样例，默认取 mesh_index=0；不是通用饰品重定向算法。',
            '目标 Skin、骨骼层级和逆绑定矩阵已从目标骨架 GLB 重建；仍需 Penumbra/游戏内确认模型局部空间和最终表现。',
            '本函数不编译 MDL，也不直接生成 PMP。',
        ],
    }
