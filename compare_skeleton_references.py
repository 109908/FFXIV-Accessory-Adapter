#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare target-body/item GLB with source reference, optional Mod source GLB and SKLB."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from accessory_adapter.skeleton_reference import build_report, to_text

def main():
 p=argparse.ArgumentParser(description='对比 GLB 内嵌骨架、头颈变换、耳朵权重和 SKLB 可见骨骼名。')
 p.add_argument('--body-glb',required=True,help='目标种族身体 GLB')
 p.add_argument('--target-item-glb',required=True,help='目标种族原版装备 GLB')
 p.add_argument('--source-reference-glb',required=True,help='源种族原版装备/骨架参考 GLB（含源种族骨架）')
 p.add_argument('--source-mod-glb',help='Mod 中待适配的源模型 GLB（可选）')
 p.add_argument('--sklb',help='目标种族 SKLB（仅扫描可见字符串）')
 p.add_argument('-o','--output',default='output/skeleton_reference_report.json')
 a=p.parse_args()
 try:
  r=build_report(a.body_glb,a.target_item_glb,a.source_reference_glb,a.source_mod_glb,a.sklb)
  out=Path(a.output).expanduser(); out.parent.mkdir(parents=True,exist_ok=True)
  out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
  txt=out.with_suffix('.txt'); txt.write_text(to_text(r),encoding='utf-8')
  print('骨架交叉检查完成。')
  print(f"目标身体/装备：同名骨骼 {r['comparisons']['target_body_vs_target_item']['common_joint_count']}，父级差异 {r['comparisons']['target_body_vs_target_item']['parent_difference_count']}，头颈局部变换差异 {r['comparisons']['target_body_vs_target_item']['head_chain_local_transform_difference_count']}")
  print(f"头部世界 Y 差（目标-源）：{r['head_height_delta']['target_minus_source_y']}")
  print(f"源参考模型仅受 j_kao 影响的顶点：{r['source_reference_weight_analysis']['vertices_only_influenced_by_target_bone']}/{r['source_reference_weight_analysis']['total_skinned_vertices']}")
  print(f"源参考模型含 j_kao 权重的顶点：{r['source_reference_weight_analysis']['vertices_with_target_bone_influences']}/{r['source_reference_weight_analysis']['total_skinned_vertices']}")
  if r['source_mod_weight_analysis']:
   print(f"Mod 源模型仅受 j_kao 影响的顶点：{r['source_mod_weight_analysis']['vertices_only_influenced_by_target_bone']}/{r['source_mod_weight_analysis']['total_skinned_vertices']}")
   print(f"Mod 源模型含 j_kao 权重的顶点：{r['source_mod_weight_analysis']['vertices_with_target_bone_influences']}/{r['source_mod_weight_analysis']['total_skinned_vertices']}")
  if r['inputs']['sklb']:
   s=r['inputs']['sklb']; print(f"SKLB 可见骨骼名：{s['unique_visible_bone_name_count']}；与身体 GLB 同名：{s['matched_count']}")
  print(f'JSON：{out.resolve()}'); print(f'TXT：{txt.resolve()}')
 except Exception as e:
  print(f'检查失败：{type(e).__name__}: {e}',file=sys.stderr); return 1
 return 0
if __name__=='__main__': raise SystemExit(main())
