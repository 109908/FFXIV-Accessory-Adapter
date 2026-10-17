from __future__ import annotations
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.penumbra_package import (  # noqa: E402
    PackageBuildError,
    build_race_option_pmp,
    compare_reference_archives,
)

DATA = Path('/mnt/data')
MOTHER = DATA / '{Mord Proxy} Inu Set (v 2.0).pmp'
REFERENCE = DATA / '{Mord Proxy} Inu Set (v 2.0) - Elezen Male V3 (2)(1).zip'
FEMALE_MDL = DATA / 'c0601e6047_met.mdl'


class PackageBuilderTests(unittest.TestCase):
    def _make_fixture(self, td: Path):
        mother = td / 'mother.pmp'
        ref = td / 'reference.zip'
        mdl = td / 'c0601e6047_met.mdl'
        with zipfile.ZipFile(mother, 'w') as z:
            z.writestr('meta.json', json.dumps({'FileVersion': 3, 'Name': 'Test', 'Version': '1'}))
            z.writestr('group_009_lala + viera (replaces werewolf head).json', json.dumps({
                'Name': 'Lala + Viera (Replaces Werewolf Head)', 'Type': 'Multi', 'DefaultSettings': 3,
                'Options': [
                    {'Name': 'Lalafell', 'Files': {}, 'FileSwaps': {}, 'Manipulations': [{'Type': 'Eqdp'}]},
                    {'Name': 'Viera', 'Files': {}, 'FileSwaps': {}, 'Manipulations': [{'Type': 'Eqdp'}, {'Type': 'Eqp'}]},
                ]
            }))
            z.writestr('common/2/mt_c0701t0001_b.mtrl', b'mtrl')
            z.writestr('common/1/mt_c0701t0001_til_blank.mtrl', b'blank')
        ref_meta = {'FileVersion': 4, 'Groups': [{
            'Name': 'Lala + Viera (Replaces Werewolf Head)', 'Options': [
                {'Name': 'Elezen Male', 'Files': {
                    'chara/equipment/e6047/material/v0001/mt_c0101e6047_met_b.mtrl': 'common\\2\\mt_c0701t0001_b.mtrl',
                    'chara/equipment/e6047/material/v0001/mt_c0101e6047_met_c.mtrl': 'common\\2\\mt_c0701t0001_b.mtrl',
                    'chara/equipment/e6047/model/c0501e6047_met.mdl': 'elezen male\\chara\\equipment\\e6047\\model\\c0501e6047_met.mdl'}, 'Manipulations': []}
            ]
        }]}
        with zipfile.ZipFile(ref, 'w') as z:
            z.writestr('Successful V3/meta.json', json.dumps(ref_meta))
        mdl.write_bytes(b'MDL fixture')
        return mother, ref, mdl

    def test_real_reference_comparison(self):
        if not (MOTHER.is_file() and REFERENCE.is_file()):
            self.skipTest('Conversation sample archives are not mounted in this environment')
        result = compare_reference_archives(MOTHER, REFERENCE)
        self.assertEqual(result['mother_file_version'], 3)
        self.assertEqual(result['reference_file_version'], 4)
        self.assertEqual(result['mother_group_count'], 9)
        self.assertEqual(result['reference_group_count'], 9)
        self.assertEqual(result['mother_option_count'], 40)
        self.assertEqual(result['reference_option_count'], 41)
        self.assertTrue(result['existing_option_comparison']['Viera']['file_mappings_equal'])

    def test_build_is_idempotent_and_preserves_existing_options(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            mother, ref, mdl = self._make_fixture(td)
            output = td / 'output.pmp'
            r1 = build_race_option_pmp(mother, ref, mdl, output)
            self.assertEqual(r1['target_option_manipulation_count'], 0)
            self.assertEqual(r1['target_group_option_count'], 3)
            self.assertEqual(r1['missing_sources'], [])
            # Run a second time using output as mother; should replace, not duplicate the option.
            output2 = td / 'output2.pmp'
            r2 = build_race_option_pmp(output, ref, mdl, output2)
            self.assertEqual(r2['target_group_option_count'], 3)
            with zipfile.ZipFile(output2) as z:
                gname = next(n for n in z.namelist() if n.startswith('group_009'))
                group = json.loads(z.read(gname))
                females = [o for o in group['Options'] if o['Name'] == 'Elezen Female']
                self.assertEqual(len(females), 1)
                self.assertEqual(females[0]['Manipulations'], [])
                self.assertEqual(females[0]['Files']['chara/equipment/e6047/model/c0601e6047_met.mdl'],
                                 'elezen female\\chara\\equipment\\e6047\\model\\c0601e6047_met.mdl')
                self.assertEqual(z.read('elezen female/chara/equipment/e6047/model/c0601e6047_met.mdl'), b'MDL fixture')

    def test_real_build_preserves_original_options_and_all_other_files(self):
        if not all(p.is_file() for p in (MOTHER, REFERENCE, FEMALE_MDL)):
            self.skipTest('Conversation sample files are not mounted')
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'female.pmp'
            result = build_race_option_pmp(MOTHER, REFERENCE, FEMALE_MDL, output)
            self.assertEqual(result['zip_crc'], 'PASS')
            self.assertEqual(result['mdl_byte_identity'], 'PASS')
            self.assertEqual(result['target_option_manipulation_count'], 0)
            with zipfile.ZipFile(MOTHER) as old, zipfile.ZipFile(output) as new:
                old_names = {n for n in old.namelist() if not n.endswith('/')}
                new_names = {n for n in new.namelist() if not n.endswith('/')}
                changed = {'meta.json', 'group_009_lala + viera (replaces werewolf head).json'}
                self.assertTrue(old_names.issubset(new_names))
                for name in old_names - changed:
                    self.assertEqual(old.read(name), new.read(name), f'original file changed unexpectedly: {name}')
                group_name = 'group_009_lala + viera (replaces werewolf head).json'
                old_group = json.loads(old.read(group_name))
                new_group = json.loads(new.read(group_name))
                for existing_name in ('Lalafell', 'Viera'):
                    old_option = next(o for o in old_group['Options'] if o['Name'] == existing_name)
                    new_option = next(o for o in new_group['Options'] if o['Name'] == existing_name)
                    self.assertEqual(old_option, new_option, f'{existing_name} option changed unexpectedly')
                female = [o for o in new_group['Options'] if o['Name'] == 'Elezen Female']
                self.assertEqual(len(female), 1)
                self.assertEqual(female[0]['Manipulations'], [])

    def test_wrong_race_filename_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            mother, ref, mdl = self._make_fixture(td)
            with self.assertRaises(PackageBuildError):
                build_race_option_pmp(mother, ref, mdl, td / 'out.pmp', target_race='Elezen Male')

    def test_existing_inputs_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            mother, ref, mdl = self._make_fixture(td)
            with self.assertRaises(PackageBuildError):
                build_race_option_pmp(mother, ref, mdl, mother)


if __name__ == '__main__':
    unittest.main()
