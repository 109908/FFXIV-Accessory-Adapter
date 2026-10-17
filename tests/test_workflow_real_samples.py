from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from accessory_adapter.workflow import adapt_head_using_references  # noqa: E402
from accessory_adapter.model_io import read_model, read_accessor, node_name, build_parent_map, validate_glb  # noqa: E402

DATA = Path('/mnt/data')
SOURCE_MOD = DATA / 'c1701e6047_met.glb'
SOURCE_REF = DATA / 'c0101e6141_met.glb'
FEMALE_BODY = DATA / 'c0601b0002_top.glb'
FEMALE_EQUIPMENT = DATA / 'c0601e6047_met.glb'

class WorkflowSampleTests(unittest.TestCase):
    def test_female_offset_calculated_from_glb_reference_data(self):
        if not all(p.is_file() for p in (SOURCE_MOD, SOURCE_REF, FEMALE_BODY, FEMALE_EQUIPMENT)):
            self.skipTest('Conversation GLB samples not mounted')
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'female_adapted.glb'
            report = adapt_head_using_references(
                SOURCE_MOD, SOURCE_REF, FEMALE_BODY, output,
                target_skeleton_glb=FEMALE_EQUIPMENT,
            )
            self.assertTrue(output.is_file())
            self.assertAlmostEqual(report['calculated_y_offset'], 0.148825, places=5)
            self.assertEqual(report['adapter_result']['head_joint_name'], 'j_kao')
            self.assertGreater(report['adapter_result']['vertex_count'], 0)
            self.assertTrue(report['adapter_result']['target_skeleton_rebind']['inverse_bind_matrices_replaced'])
            self.assertEqual(report['adapter_result']['target_skeleton_rebind']['target_joint_count'], 167)
            adapted = read_model(output)
            target = read_model(FEMALE_EQUIPMENT)
            active_skin = adapted.json['skins'][0]
            target_skin = target.json['skins'][0]
            adapted_names = [node_name(adapted.json, int(n)) for n in active_skin['joints']]
            target_names = [node_name(target.json, int(n)) for n in target_skin['joints']]
            self.assertEqual(adapted_names, target_names)
            self.assertEqual(len(adapted_names), 167)
            self.assertEqual(len(adapted.json['meshes']), 1, '输出必须只保留选中的耳朵网格，避免误导入躯干位置的第二网格')
            self.assertEqual(len(adapted.json['skins']), 1, '输出必须只保留已重定向到目标种族的活动 Skin')
            self.assertEqual(validate_glb(adapted), [])
            adapted_ibm = read_accessor(adapted, int(active_skin['inverseBindMatrices']))
            target_ibm = read_accessor(target, int(target_skin['inverseBindMatrices']))
            self.assertEqual(len(adapted_ibm), len(target_ibm))
            self.assertEqual(adapted_ibm[46], target_ibm[46])
            parent_map = build_parent_map(adapted.json)
            j_kao_node = active_skin['joints'][46]
            self.assertEqual(node_name(adapted.json, j_kao_node), 'j_kao')
            self.assertEqual(node_name(adapted.json, parent_map[j_kao_node]), 'j_kubi')

if __name__ == '__main__': unittest.main()
