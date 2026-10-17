import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from accessory_adapter.skeleton_reference import inspect_glb, compare_glbs, _active_weight_stats, build_report

DATA=Path('/mnt/data')
@unittest.skipUnless((DATA/'c0501b0002_top.glb').exists(), 'real uploaded samples are unavailable')
class TestSkeletonReferenceSamples(unittest.TestCase):
    def test_target_body_and_item_share_head_chain(self):
        body=inspect_glb(DATA/'c0501b0002_top.glb')
        item=inspect_glb(DATA/'c0501e6047_met(1).glb')
        cmp=compare_glbs(body,item)
        self.assertEqual(cmp['common_joint_count'],167)
        self.assertEqual(cmp['candidate_only_joints'],['j_ex_met_va'])
        self.assertEqual(cmp['parent_difference_count'],0)
        self.assertEqual(cmp['inverse_bind_matrix_difference_count'],0)
        self.assertEqual(cmp['head_chain_local_transform_difference_count'],0)
        self.assertEqual(cmp['head_chain_world_transform_difference_count'],0)


    def test_v3_target_item_skeleton_matches_target_body(self):
        body=inspect_glb(DATA/'c0501b0002_top.glb')
        item=inspect_glb(DATA/'c0501e6047_v3_met.glb')
        cmp=compare_glbs(body,item)
        self.assertEqual(cmp['common_joint_count'],167)
        self.assertEqual(cmp['candidate_only_joints'],[])
        self.assertEqual(cmp['parent_difference_count'],0)
        self.assertEqual(cmp['inverse_bind_matrix_difference_count'],0)
        self.assertEqual(cmp['head_chain_local_transform_difference_count'],0)
        self.assertEqual(cmp['head_chain_world_transform_difference_count'],0)

    def test_source_and_target_head_height_matches_historical_offset(self):
        source=inspect_glb(DATA/'c0101e6141_met.glb')
        target=inspect_glb(DATA/'c0501b0002_top.glb')
        def y(info):
            return next(x['world_translation'][1] for x in info['skins'][0]['head_chain'] if x['name']=='j_kao')
        delta=y(target)-y(source)
        self.assertAlmostEqual(delta,0.2545355,places=5)

    def test_original_ear_glb_is_head_bound(self):
        stats=_active_weight_stats(DATA/'c0101e6141_met.glb')
        self.assertEqual(stats['invalid_joint_references'],[])
        self.assertEqual(stats['vertices_only_influenced_by_target_bone'],1312)
        self.assertEqual(stats['vertices_only_influenced_by_target_bone'],stats['total_skinned_vertices'])

    def test_mod_source_has_additional_ear_bones(self):
        source=inspect_glb(DATA/'c0101e6141_met.glb')
        mod=inspect_glb(DATA/'c1701e6047_met.glb')
        cmp=compare_glbs(source,mod)
        self.assertEqual(cmp['candidate_only_joints'],['j_zera_a_l','j_zera_a_r'])
        self.assertEqual(cmp['head_chain_local_transform_difference_count'],0)
        stats=_active_weight_stats(DATA/'c1701e6047_met.glb')
        self.assertIn('j_zera_a_l',stats['other_active_bone_vertex_counts'])
        self.assertIn('j_zera_a_r',stats['other_active_bone_vertex_counts'])

    def test_sklb_visible_names_cover_head_chain(self):
        from accessory_adapter.skeleton_reference import inspect_sklb_names
        body=inspect_glb(DATA/'c0501b0002_top.glb')
        result=inspect_sklb_names(DATA/'skl_c0501b0001.sklb',set(body['skins'][0]['joint_names']))
        self.assertTrue(all(result['head_chain_name_presence'].values()))
        self.assertTrue(result['contains_havok_skeleton_mapper_marker'])
        self.assertEqual(result['matched_count'],153)

if __name__=='__main__': unittest.main()
