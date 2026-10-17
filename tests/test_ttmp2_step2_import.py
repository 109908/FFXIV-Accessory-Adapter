import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from accessory_adapter.ttmp2_import import convert_ttmp2_to_pmp
from accessory_adapter.penumbra_package import inspect_pmp_option_groups


class TTMP2Step2ImportTests(unittest.TestCase):
    def test_convert_manifest_and_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'sample.ttmp2'
            output = root / 'converted.pmp'
            manifest = {
                'Name': 'Sample Mod', 'Author': 'Tester', 'Version': '1.0',
                'ModPackPages': [{'ModGroups': [{
                    'GroupName': 'Ears', 'SelectionType': 'Single',
                    'OptionList': [{'Name': 'Default', 'ModsJsons': [{
                        'Name': 'Model', 'FullPath': 'chara/accessory/a0047/model/test.mdl',
                        'ModOffset': 0, 'ModSize': 4
                    }]}]
                }]}]
            }
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('TTMPL.mpl', json.dumps(manifest))
                z.writestr('TTMPD.mpd', b'MDL!')
            report = convert_ttmp2_to_pmp(source, output)
            self.assertEqual(report['resource_count'], 1)
            groups = inspect_pmp_option_groups(output)
            self.assertEqual(groups['group_count'], 1)
            self.assertEqual(groups['groups'][0]['option_names'], ['Default'])
            with zipfile.ZipFile(output) as z:
                meta = json.loads(z.read('meta.json'))
                option = meta['Groups'][0]['Options'][0]
                internal = next(iter(option['Files'].values())).replace('\\', '/')
                self.assertEqual(z.read(internal), b'MDL!')


if __name__ == '__main__':
    unittest.main()
