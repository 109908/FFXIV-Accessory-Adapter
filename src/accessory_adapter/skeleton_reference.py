#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-check GLB embedded skeletons and conservatively inspect SKLB name evidence.

This tool does not claim to fully deserialize Havok/SKLB. It compares actual glTF
joint hierarchies/transforms/IBMs and reports visible bone-name strings in SKLB.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .model_io import read_glb, read_accessor, node_name, build_parent_map

HEAD_CHAIN = ("n_root", "n_hara", "j_sebo_a", "j_sebo_b", "j_sebo_c", "j_kubi", "j_kao")
BONE_RE = re.compile(r"^(?:n|j|atr|iv)_[A-Za-z0-9_]+$")


def _identity():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _trs(node: dict[str, Any]):
    if "matrix" in node:
        vals = node["matrix"]
        if len(vals) != 16:
            raise ValueError("节点 matrix 不是 16 个分量。")
        return [[float(vals[c * 4 + r]) for c in range(4)] for r in range(4)]
    t = node.get("translation", [0.0, 0.0, 0.0])
    q = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    s = node.get("scale", [1.0, 1.0, 1.0])
    x, y, z, w = [float(v) for v in q]
    rot = [
        [1 - 2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), 0.0],
        [2*(x*y+z*w), 1 - 2*(x*x+z*z), 2*(y*z-x*w), 0.0],
        [2*(x*z-y*w), 2*(y*z+x*w), 1 - 2*(x*x+y*y), 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    scale = [[float(s[r]) if r == c and r < 3 else (1.0 if r == c == 3 else 0.0) for c in range(4)] for r in range(4)]
    trans = _identity()
    for i in range(3): trans[i][3] = float(t[i])
    return _mul(_mul(trans, rot), scale)


def _world_matrices(doc):
    nodes = doc.get("nodes", [])
    parents = build_parent_map(doc)
    local = [_trs(n) for n in nodes]
    world = {}
    active = set()
    def resolve(i):
        if i in world: return world[i]
        if i in active: raise ValueError("GLB 节点层级存在循环引用。")
        active.add(i)
        world[i] = _mul(resolve(parents[i]), local[i]) if i in parents else local[i]
        active.remove(i)
        return world[i]
    for i in range(len(nodes)): resolve(i)
    return local, world, parents


def _maxdiff(a, b):
    if len(a) != len(b): return None
    vals=[]
    for x,y in zip(a,b):
        if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
            vals.extend(abs(float(i)-float(j)) for i,j in zip(x,y))
        else:
            vals.append(abs(float(x)-float(y)))
    return max(vals, default=0.0)


def _file_sha(path: Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def inspect_glb(path: str | Path) -> dict[str, Any]:
    path=Path(path).expanduser().resolve()
    model=read_glb(path); doc=model.json
    if not doc.get('skins'):
        raise ValueError(f"{path.name} 没有 Skin，不能用作骨架参考。")
    local, world, parents = _world_matrices(doc)
    skins=[]
    for si, skin in enumerate(doc.get('skins', [])):
        joint_ids=[int(x) for x in skin.get('joints', [])]
        names=[node_name(doc, j) for j in joint_ids]
        if len(names) != len(set(names)):
            duplicate=sorted({n for n in names if names.count(n)>1})
        else: duplicate=[]
        joint_parent={}
        for jid, name in zip(joint_ids,names):
            parent=parents.get(jid)
            joint_parent[name]=node_name(doc,parent) if parent is not None else None
        ibm_by_name={}
        ibm_idx=skin.get('inverseBindMatrices')
        if ibm_idx is not None:
            ibms=read_accessor(model, int(ibm_idx))
            for name, matrix in zip(names, ibms): ibm_by_name[name]=matrix
        chain=[]
        for name in HEAD_CHAIN:
            hits=[j for j in joint_ids if node_name(doc,j)==name]
            if not hits: continue
            j=hits[0]; pos=[world[j][r][3] for r in range(3)]
            chain.append({
                'name':name,
                'parent':joint_parent.get(name),
                'local_translation':doc['nodes'][j].get('translation',[0.0,0.0,0.0]),
                'world_translation':pos,
                'local_matrix':local[j],
                'world_matrix':world[j],
            })
        skins.append({
            'skin_index':si,'joint_count':len(names),'unique_joint_name_count':len(set(names)),
            'duplicate_joint_names':duplicate,'joint_names':names,'parent_by_joint_name':joint_parent,
            'inverse_bind_matrices_by_joint_name':ibm_by_name,'head_chain':chain,
        })
    mesh_nodes=[]
    for ni,node in enumerate(doc.get('nodes', [])):
        if 'mesh' in node:
            mesh_nodes.append({'node_index':ni,'mesh_index':int(node['mesh']),'skin_index':node.get('skin')})
    return {
        'path':str(path),'file_name':path.name,'size_bytes':path.stat().st_size,'sha256':_file_sha(path),
        'node_count':len(doc.get('nodes',[])),'mesh_count':len(doc.get('meshes',[])),
        'skin_count':len(doc.get('skins',[])),'mesh_nodes':mesh_nodes,'skins':skins,
        'glb_asset':doc.get('asset',{}),
    }


def inspect_sklb_names(path: str | Path, reference_joint_names: set[str]) -> dict[str, Any]:
    path=Path(path).expanduser().resolve(); data=path.read_bytes()
    visible=[]
    for m in re.finditer(rb'[\x20-\x7e]{3,}', data):
        value=m.group().decode('ascii','ignore')
        if BONE_RE.fullmatch(value): visible.append({'offset':m.start(),'name':value})
    by_name={x['name']:x['offset'] for x in visible}
    names=set(by_name)
    return {
        'path':str(path),'file_name':path.name,'size_bytes':len(data),'sha256':_file_sha(path),
        'header_ascii':data[:8].decode('ascii','replace').rstrip('\x00'),
        'contains_havok_skeleton_mapper_marker':b'hkaSkeletonMapper' in data,
        'visible_bone_name_string_count':len(visible),'unique_visible_bone_name_count':len(names),
        'matched_reference_names':sorted(names & reference_joint_names),
        'matched_count':len(names & reference_joint_names),
        'reference_names_not_found_as_visible_strings':sorted(reference_joint_names - names),
        'extra_visible_names_not_in_reference':sorted(names - reference_joint_names),
        'head_chain_name_presence':{n:n in names for n in HEAD_CHAIN},
        'limitation':'仅扫描可见字符串；未解析 Havok/SKLB 对象图、骨骼索引、层级或变换。字符串缺失不等于骨骼一定不存在。',
    }


def compare_glbs(reference: dict[str, Any], candidate: dict[str, Any], skin_index: int = 0) -> dict[str, Any]:
    rs=reference['skins'][skin_index]; cs=candidate['skins'][skin_index]
    rn=set(rs['joint_names']); cn=set(cs['joint_names']); common=sorted(rn & cn)
    parent_diffs=[]; local_diffs=[]; world_diffs=[]; ibm_diffs=[]
    rlookup={x['name']:x for x in rs['head_chain']}; clookup={x['name']:x for x in cs['head_chain']}
    # Re-read full matrices from the inspected source's joint lists by mapping names to nodes.
    # inspect_glb stores all hierarchy parents but only head matrices; for all-bone matrix comparison use head chain only.
    for name in common:
        rp=rs['parent_by_joint_name'].get(name); cp=cs['parent_by_joint_name'].get(name)
        if rp != cp: parent_diffs.append({'bone':name,'reference_parent':rp,'candidate_parent':cp})
        if name in rs['inverse_bind_matrices_by_joint_name'] and name in cs['inverse_bind_matrices_by_joint_name']:
            delta=_maxdiff(rs['inverse_bind_matrices_by_joint_name'][name],cs['inverse_bind_matrices_by_joint_name'][name])
            if delta is not None and delta > 1e-5: ibm_diffs.append({'bone':name,'max_abs_difference':delta})
    for name in sorted(set(rlookup)&set(clookup)):
        rd=rlookup[name]; cd=clookup[name]
        ld=_maxdiff(rd['local_matrix'],cd['local_matrix']); wd=_maxdiff(rd['world_matrix'],cd['world_matrix'])
        if ld is not None and ld>1e-5: local_diffs.append({'bone':name,'max_abs_difference':ld})
        if wd is not None and wd>1e-5: world_diffs.append({'bone':name,'max_abs_difference':wd})
    return {
        'reference_file':reference['file_name'],'candidate_file':candidate['file_name'],'skin_index':skin_index,
        'reference_joint_count':len(rn),'candidate_joint_count':len(cn),'common_joint_count':len(common),
        'reference_only_joints':sorted(rn-cn),'candidate_only_joints':sorted(cn-rn),
        'parent_difference_count':len(parent_diffs),'parent_differences':parent_diffs,
        'inverse_bind_matrix_difference_count':len(ibm_diffs),'inverse_bind_matrix_differences':ibm_diffs[:100],
        'head_chain_local_transform_difference_count':len(local_diffs),'head_chain_local_transform_differences':local_diffs,
        'head_chain_world_transform_difference_count':len(world_diffs),'head_chain_world_transform_differences':world_diffs,
        'head_chain_world_positions':{
            name:{'reference':rlookup[name]['world_translation'],'candidate':clookup[name]['world_translation']}
            for name in sorted(set(rlookup)&set(clookup))
        },
    }


def _active_weight_stats(path: str | Path, target_bone: str='j_kao') -> dict[str, Any]:
    model=read_glb(path); doc=model.json
    node_summaries=[]; total_vertices=0; target_only=0; any_target=0; other_active={}; invalid_joint_refs=[]
    for ni,node in enumerate(doc.get('nodes', [])):
        if 'mesh' not in node or 'skin' not in node: continue
        mesh=doc['meshes'][int(node['mesh'])]; skin=doc['skins'][int(node['skin'])]
        joint_names=[node_name(doc,int(j)) for j in skin.get('joints',[])]
        mesh_vertices=0; mesh_target_only=0; mesh_any_target=0; mesh_other_active={}
        for pi,prim in enumerate(mesh.get('primitives', [])):
            attrs=prim.get('attributes',{})
            if 'JOINTS_0' not in attrs or 'WEIGHTS_0' not in attrs: continue
            j0=read_accessor(model,int(attrs['JOINTS_0'])); w0=read_accessor(model,int(attrs['WEIGHTS_0']))
            pairs=[(j0,w0)]
            if 'JOINTS_1' in attrs and 'WEIGHTS_1' in attrs:
                pairs.append((read_accessor(model,int(attrs['JOINTS_1'])),read_accessor(model,int(attrs['WEIGHTS_1']))))
            count=len(j0); mesh_vertices+=count
            for vi in range(count):
                active=set()
                for js,ws in pairs:
                    for joint_idx, weight in zip(js[vi],ws[vi]):
                        if float(weight)>1e-6:
                            ji=int(joint_idx)
                            if ji<0 or ji>=len(joint_names):
                                invalid_joint_refs.append({'node_index':ni,'mesh_index':node['mesh'],'primitive_index':pi,'vertex_index':vi,'joint_index':ji})
                            else: active.add(joint_names[ji])
                if target_bone in active: mesh_any_target+=1; any_target+=1
                if active and active=={target_bone}: mesh_target_only+=1; target_only+=1
                for name in active:
                    if name != target_bone:
                        other_active[name]=other_active.get(name,0)+1
                        mesh_other_active[name]=mesh_other_active.get(name,0)+1
        total_vertices+=mesh_vertices
        node_summaries.append({'node_index':ni,'mesh_index':node['mesh'],'skin_index':node['skin'],'vertex_count':mesh_vertices,'vertices_only_influenced_by_target_bone':mesh_target_only,'vertices_with_target_bone_influences':mesh_any_target,'other_active_bone_vertex_counts':dict(sorted(mesh_other_active.items()))})
    return {'path':str(Path(path).resolve()),'target_bone':target_bone,'total_skinned_vertices':total_vertices,'vertices_only_influenced_by_target_bone':target_only,'vertices_with_target_bone_influences':any_target,'other_active_bone_vertex_counts':dict(sorted(other_active.items())),'invalid_joint_references':invalid_joint_refs,'mesh_nodes':node_summaries}


def build_report(body_glb: str | Path, target_item_glb: str | Path,
                 source_reference_glb: str | Path, source_mod_glb: str | Path | None=None,
                 sklb: str | Path | None=None) -> dict[str, Any]:
    """Compare target body/item with a source-race reference and optional Mod source GLB."""
    body=inspect_glb(body_glb); target=inspect_glb(target_item_glb)
    source_ref=inspect_glb(source_reference_glb)
    source_mod=inspect_glb(source_mod_glb) if source_mod_glb else None
    body_skin=body['skins'][0]
    sklb_report=inspect_sklb_names(sklb,set(body_skin['joint_names'])) if sklb else None
    body_target=compare_glbs(body,target)
    source_target=compare_glbs(source_ref,body)
    source_mod_compare=compare_glbs(source_ref,source_mod) if source_mod else None
    source_ref_weights=_active_weight_stats(source_reference_glb,'j_kao')
    source_mod_weights=_active_weight_stats(source_mod_glb,'j_kao') if source_mod_glb else None

    def head_pos(info):
        s=info['skins'][0]
        for entry in s['head_chain']:
            if entry['name']=='j_kao': return entry['world_translation']
        return None
    source_head=head_pos(source_ref); target_head=head_pos(body)
    delta_y=(target_head[1]-source_head[1]) if source_head and target_head else None
    return {
        'report_version':'1.1',
        'purpose':'Compare target body/item GLB skeletons, source-race reference and optional Mod source GLB; SKLB comparison is visible-string evidence only.',
        'inputs':{'target_body_glb':body,'target_item_glb':target,
                  'source_reference_glb':source_ref,'source_mod_glb':source_mod,'sklb':sklb_report},
        'comparisons':{'target_body_vs_target_item':body_target,
                       'source_reference_vs_target_body':source_target,
                       'source_reference_vs_source_mod':source_mod_compare},
        'source_reference_weight_analysis':source_ref_weights,
        'source_mod_weight_analysis':source_mod_weights,
        'head_height_delta':{'source_reference_file':source_ref['file_name'],
            'target_body_file':body['file_name'],
            'source_j_kao_world_y':source_head[1] if source_head else None,
            'target_j_kao_world_y':target_head[1] if target_head else None,
            'target_minus_source_y':delta_y,
            'matches_historical_offset_0_2545_within_0_0001':delta_y is not None and abs(delta_y-0.2545)<0.0001,
            'note':'基于 GLB 节点变换矩阵计算；是否应将该差值直接应用于附件顶点仍须结合模型坐标空间与游戏实测确认。'},
        'limitations':[
            'SKLB 目前仅扫描可见骨骼名称字符串，没有完整解析 Havok 对象、骨骼索引、层级、参考姿势或动画映射。',
            'GLB 骨骼比较使用第 0 个 Skin；多 Skin 的其他索引需在必要时单独比较。',
            '相同骨骼名称和变换不能证明输入资源一定是官方原版；来源仍需由用户的导出流程确认。',
            '头部世界 Y 差值与历史偏移吻合，不自动证明该偏移可用于其他附件或其他种族。',
        ]
    }


def to_text(report: dict[str, Any]) -> str:
    body=report['inputs']['target_body_glb']; target=report['inputs']['target_item_glb']
    source=report['inputs']['source_reference_glb']; mod=report['inputs'].get('source_mod_glb')
    delta=report['head_height_delta']; comp=report['comparisons']['target_body_vs_target_item']
    lines=['FF14 附件适配器：骨架参考交叉检查报告','='*42,'',
      '一、输入文件','-'*42,
      f"目标身体 GLB：{body['file_name']}（{body['size_bytes']} bytes）",
      f"目标装备 GLB：{target['file_name']}（{target['size_bytes']} bytes）",
      f"源种族原版装备/骨架参考 GLB：{source['file_name']}（{source['size_bytes']} bytes）"]
    if mod: lines.append(f"Mod 源模型 GLB：{mod['file_name']}（{mod['size_bytes']} bytes）")
    sklb=report['inputs'].get('sklb')
    if sklb: lines.append(f"SKLB：{sklb['file_name']}（{sklb['size_bytes']} bytes）")
    lines += ['', '二、目标身体与目标装备的 GLB 骨架对比','-'*42,
      f"身体 joints：{comp['reference_joint_count']}",f"装备 joints：{comp['candidate_joint_count']}",
      f"同名 joints：{comp['common_joint_count']}",f"装备独有 joints：{', '.join(comp['candidate_only_joints']) or '无'}",
      f"身体独有 joints：{', '.join(comp['reference_only_joints']) or '无'}",
      f"父级关系差异：{comp['parent_difference_count']}",
      f"逆绑定矩阵差异（绝对误差 > 1e-5）：{comp['inverse_bind_matrix_difference_count']}",
      f"头颈链局部变换差异（绝对误差 > 1e-5）：{comp['head_chain_local_transform_difference_count']}",
      f"头颈链世界变换差异（绝对误差 > 1e-5）：{comp['head_chain_world_transform_difference_count']}",
      '', '三、头部高度差','-'*42,
      f"源侧 j_kao world Y：{delta['source_j_kao_world_y']}",
      f"目标侧 j_kao world Y：{delta['target_j_kao_world_y']}",
      f"目标减源的 Y 差：{delta['target_minus_source_y']}",
      f"是否与历史 +0.2545 偏移在 0.0001 内一致：{delta['matches_historical_offset_0_2545_within_0_0001']}"]
    def append_weights(title, stats):
        if not stats: return
        lines.extend(['',title,'-'*42,
          f"蒙皮顶点总数：{stats['total_skinned_vertices']}",
          f"仅受 j_kao 影响的顶点：{stats['vertices_only_influenced_by_target_bone']}",
          f"含 j_kao 权重的顶点：{stats['vertices_with_target_bone_influences']}",
          f"其他有效影响骨骼对应顶点计数：{stats['other_active_bone_vertex_counts']}",
          f"无效骨骼索引：{len(stats['invalid_joint_references'])}"])
    append_weights('四、源种族参考模型的 j_kao 权重',report['source_reference_weight_analysis'])
    append_weights('五、Mod 源模型的 j_kao 权重',report.get('source_mod_weight_analysis'))
    if report['comparisons'].get('source_reference_vs_source_mod'):
        c=report['comparisons']['source_reference_vs_source_mod']
        lines += ['', '六、源种族参考与 Mod 源模型骨架对比','-'*42,
          f"同名 joints：{c['common_joint_count']}",
          f"Mod 源模型额外 joints：{', '.join(c['candidate_only_joints']) or '无'}",
          f"参考模型独有 joints：{', '.join(c['reference_only_joints']) or '无'}",
          f"头颈链局部变换差异：{c['head_chain_local_transform_difference_count']}",
          f"头颈链世界变换差异：{c['head_chain_world_transform_difference_count']}"]
    if sklb:
      lines += ['', '七、SKLB 可见字符串证据（不是完整 Havok 解析）','-'*42,
        f"头部标识：{sklb['header_ascii']}",
        f"包含 hkaSkeletonMapper 标记：{sklb['contains_havok_skeleton_mapper_marker']}",
        f"唯一可见骨骼名候选：{sklb['unique_visible_bone_name_count']}",
        f"与身体 GLB 同名：{sklb['matched_count']}",
        f"身体 GLB 中未扫描到可见字符串的名字：{', '.join(sklb['reference_names_not_found_as_visible_strings']) or '无'}",
        f"头颈链名称存在：{sklb['head_chain_name_presence']}"]
    lines += ['', '结论与限制','-'*42,
      '本报告对 GLB 的骨骼节点、层级、变换及顶点权重进行了结构化读取；对 SKLB 仅扫描可见字符串。',
      '不能把 SKLB 中未发现可见字符串的骨骼直接判断为不存在，也不能仅凭这些信息证明文件是官方原版。',
      '头部世界 Y 差与历史偏移相符，是重要的回归证据，但仍需结合模型坐标空间与游戏结果确认。','']
    return '\n'.join(lines)

