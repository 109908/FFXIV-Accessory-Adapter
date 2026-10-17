import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.backends.ffxiv_mdl_backend import (  # noqa: E402
    MdlBackendError,
    build_fbx_to_mdl_command,
    build_mdl_to_fbx_command,
    probe_mdl_bytes,
    probe_mdl_file,
)
from accessory_adapter.input_scanner import scan_input  # noqa: E402


class FfxivMdlBackendTests(unittest.TestCase):
    def test_probe_finds_string_candidates_without_claiming_full_parse(self):
        data = (
            b"\x06\x00\x00\x01" + b"\x00" * 8
            + b"j_kao\x00j_zera_a_l\x00n_root\x00"
            + b"/mt_c0101e6047_met_a.mtrl\x00"
            + b"chara/equipment/e6047/model/c0501e6047_met.mdl\x00"
        )
        result = probe_mdl_bytes(data, "fixture.mdl")
        self.assertEqual(result["parser_status"], "forensic_string_probe_only")
        self.assertIn("j_kao", result["bone_name_candidates"])
        self.assertIn("j_zera_a_l", result["bone_name_candidates"])
        self.assertIn("mt_c0101e6047_met_a.mtrl", result["material_reference_candidates"])
        self.assertEqual(result["internal_mdl_path_candidate_count"], 1)
        self.assertTrue(result["matches_supplied_sample_prefix"])
        self.assertTrue(any("Not a structural" in item for item in result["limitations"]))

    def test_empty_bytes_rejected(self):
        with self.assertRaises(MdlBackendError):
            probe_mdl_bytes(b"")

    def test_game_path_must_be_internal_relative_mdl_path(self):
        with self.assertRaises(MdlBackendError):
            build_mdl_to_fbx_command("converter.exe", "in.mdl", "out.fbx", r"E:\game\model.mdl")
        command = build_mdl_to_fbx_command(
            "converter.exe", "in.mdl", "out.fbx",
            "chara/equipment/e6047/model/c0501e6047_met.mdl",
        )
        self.assertEqual(command[1], "mdl2fbx")
        self.assertEqual(command[-1], "chara/equipment/e6047/model/c0501e6047_met.mdl")

    def test_fbx_to_mdl_command_uses_base_model_and_optional_race(self):
        command = build_fbx_to_mdl_command(
            "converter.exe", "in.fbx", "out.mdl",
            "chara/equipment/e6047/model/c0501e6047_met.mdl",
            "base.mdl", "Elezen_Male",
        )
        self.assertIn("--base-model", command)
        self.assertIn("--override-incoming-race", command)
        self.assertEqual(command[-1], "Elezen_Male")

    def test_probe_file_and_scanner_integration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mdl = root / "c0501e6047_met.mdl"
            mdl.write_bytes(b"\x06\x00\x00\x01\x00j_kao\x00/mt_c0101e6047_met_a.mtrl\x00")
            direct = probe_mdl_file(mdl)
            self.assertEqual(direct["source_name"], mdl.name)
            scanned = scan_input(mdl, "target_equipment_reference", include_mdl_probes=True)
            self.assertEqual(scanned["summary"]["mdl_probe_count"], 1)
            probe = scanned["resources"][0]["mdl_probe"]
            self.assertIn("j_kao", probe["bone_name_candidates"])


if __name__ == "__main__":
    unittest.main()
