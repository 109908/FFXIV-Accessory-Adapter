import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.input_scanner import scan_input, compare_mod_configs
from accessory_adapter.resource_classifier import classify_resource


class ResourceScannerTests(unittest.TestCase):
    def _make_mod_folder(self, root: Path, option_name="Elezen Male"):
        (root / "common").mkdir(parents=True)
        (root / "common" / "asset.mtrl").write_bytes(b"mtrl")
        meta = {
            "Name": "Fixture Mod", "Author": "Test", "Version": "1",
            "Groups": [{"Name": "Heads", "Type": "Multi", "Options": [{
                "Id": "fixture-id", "Name": option_name,
                "Files": {"chara/equipment/e6047/material/v0001/mt.mtrl": "common/asset.mtrl"},
                "FileSwaps": {}, "Manipulations": []
            }]}]
        }
        (root / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def test_folder_scan_and_mapping_presence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mod"
            root.mkdir()
            self._make_mod_folder(root)
            result = scan_input(root, "mod_master")
            self.assertEqual(result["summary"]["file_count"], 2)
            self.assertEqual(result["mod_analysis"]["summary"]["group_count"], 1)
            self.assertEqual(result["mod_analysis"]["summary"]["missing_source_count"], 0)
            self.assertEqual(len(result["mod_analysis"]["target_option_matches"]), 1)

    def test_zip_wrapper_root_and_pmp_style_group_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            folder = base / "Fixture Mod"
            folder.mkdir()
            self._make_mod_folder(folder)
            zip_path = base / "fixture.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                for p in folder.rglob("*"):
                    if p.is_file(): z.write(p, p.relative_to(base).as_posix())
            result = scan_input(zip_path, "mod_master")
            self.assertEqual(result["mod_analysis"]["summary"]["option_count"], 1)
            pmp_path = base / "fixture.pmp"
            meta = {"Name": "Fixture Mod", "Version": "1"}
            group = {"Name": "Heads", "Type": "Multi", "Options": [{
                "Name": "Elezen Male", "Files": {"chara/equipment/e6047/material/v0001/mt.mtrl": "common/asset.mtrl"},
                "FileSwaps": {}, "Manipulations": []
            }]}
            with zipfile.ZipFile(pmp_path, "w") as z:
                z.writestr("meta.json", json.dumps(meta))
                z.writestr("group_001_heads.json", json.dumps(group))
                z.writestr("common/asset.mtrl", b"mtrl")
            result_pmp = scan_input(pmp_path, "mod_master")
            self.assertEqual(result_pmp["mod_analysis"]["summary"]["group_count"], 1)
            self.assertEqual(result_pmp["mod_analysis"]["summary"]["missing_source_count"], 0)

    def test_classifier_is_conservative_about_provenance(self):
        result = classify_resource("elezen male/chara/equipment/e6047/model/c0501e6047_met.mdl", "target_equipment_reference", 100)
        self.assertEqual(result["resource_type"], "ffxiv_model_mdl")
        self.assertEqual(result["model_code_candidate"], "c0501")
        self.assertEqual(result["equipment_id_candidate"], "e6047")
        self.assertFalse(result["provenance_verified"])
        backup = classify_resource("group_009_heads.json.bak")
        self.assertEqual(backup["resource_type"], "backup_mod_configuration")

    def test_backup_configs_are_diagnostic_and_can_be_compared_explicitly(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            left = base / "left.zip"
            right = base / "right.pmp"
            meta = {"Name": "Fixture", "Version": "1", "Groups": [{"Name": "Heads", "Type": "Multi", "Options": [{
                "Name": "Elezen Male", "Files": {"chara/equipment/e6047/model/c0501e6047_met.mdl": "common/head.mdl"},
                "FileSwaps": {}, "Manipulations": []
            }]}]}
            backup_group = {"Name": "Heads", "Type": "Multi", "Options": [{
                "Name": "Elezen Male", "Files": {"chara/equipment/e6047/model/c0501e6047_met.mdl": "common/head.mdl"},
                "FileSwaps": {}, "Manipulations": [{"Type": "Eqdp", "Manipulation": {"Entry": 1}}]
            }]}
            with zipfile.ZipFile(left, "w") as z:
                z.writestr("Fixture/meta.json", json.dumps(meta))
                z.writestr("Fixture/group_001_heads.json.bak", json.dumps(backup_group))
                z.writestr("Fixture/common/head.mdl", b"mdl")
            with zipfile.ZipFile(right, "w") as z:
                z.writestr("meta.json", json.dumps({"Name": "Fixture", "Version": "1"}))
                z.writestr("group_001_heads.json", json.dumps(backup_group))
                z.writestr("common/head.mdl", b"mdl")
            scanned = scan_input(left, "mod_master")
            self.assertIsNotNone(scanned["backup_mod_analysis"])
            self.assertFalse(scanned["internal_config_comparison"]["same_semantic_config"])
            compared = compare_mod_configs(left, right, "backup", "active")
            self.assertTrue(compared["same_semantic_config"])

    def test_compare_semantic_configs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            left, right = base / "left", base / "right"
            left.mkdir(); right.mkdir()
            self._make_mod_folder(left)
            self._make_mod_folder(right)
            result = compare_mod_configs(left, right)
            self.assertTrue(result["same_semantic_config"])
            self.assertEqual(result["difference_count"], 0)


if __name__ == "__main__":
    unittest.main()
