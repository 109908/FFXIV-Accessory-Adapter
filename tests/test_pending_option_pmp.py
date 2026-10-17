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
    build_pending_option_pmp,
    inspect_pmp_option_groups,
)


def _write_zip(path: Path, entries: dict[str, bytes | str]):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, value in entries.items():
            zf.writestr(name, value.encode("utf-8") if isinstance(value, str) else value)


class GenericPendingPmpTests(unittest.TestCase):
    def _v3_fixture(self, td: Path):
        mother = td / "arbitrary-mod.pmp"
        glb = td / "adapted.glb"
        mdl = td / "c0601e6047_met.mdl"
        mdl.write_bytes(b"TEST_TARGET_VANILLA_MDL_BYTES_" + bytes(range(32)))
        # Minimal GLB header for the builder's file-type gate (full model parsing is Step 1's job).
        glb.write_bytes(b"glTF" + (2).to_bytes(4, "little") + (24).to_bytes(4, "little") + (4).to_bytes(4, "little") + (0x4E4F534A).to_bytes(4, "little") + b"{}  ")
        entries = {
            "meta.json": json.dumps({"FileVersion": 3, "Name": "Arbitrary Mod", "Version": "2.3"}),
            "group_001_ears.json": json.dumps({
                "Name": "Ears", "Description": "Ears for some races", "Priority": 0,
                "Image": "", "Page": "", "Type": "Multi", "DefaultSettings": 0,
                "Options": [
                    {"Name": "Miqote", "Description": "existing", "Image": "", "Priority": 0,
                     "Files": {"chara/equipment/e0001/model/c0101e0001_met.mdl": "miqote/model.mdl"},
                     "FileSwaps": {}, "Manipulations": [{"Type": "Eqp"}]},
                    {"Name": "Viera", "Description": "existing", "Image": "", "Priority": 0,
                     "Files": {}, "FileSwaps": {}, "Manipulations": []},
                ]
            }),
            "miqote/model.mdl": b"existing-model",
            "common/texture.mtrl": b"texture",
        }
        _write_zip(mother, entries)
        return mother, entries, glb, mdl

    def test_v3_build_requires_target_vanilla_mdl_but_not_reference_zip_or_modified_mdl(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother, original, glb, mdl = self._v3_fixture(td)
            out = td / "staging.pmp"
            info = inspect_pmp_option_groups(mother)
            self.assertEqual(info["file_version"], 3)
            self.assertEqual(info["groups"][0]["name"], "Ears")
            result = build_pending_option_pmp(mother, out, adapted_glb=glb, target_base_mdl=mdl, option_group="Ears", target_race="Elezen Female")
            self.assertEqual(result["zip_crc"], "PASS")
            self.assertEqual(result["target_option_files_count"], 1)
            self.assertTrue(result["target_base_mdl_added_to_pmp"])
            self.assertEqual(result["adapted_glb_validation"], "PASS")
            self.assertEqual(result["adapted_glb_sha256"], __import__("hashlib").sha256(glb.read_bytes()).hexdigest())
            with zipfile.ZipFile(mother) as old, zipfile.ZipFile(out) as new:
                changed = "group_001_ears.json"
                self.assertEqual(set(new.namelist()), set(old.namelist()) | {"elezen female/chara/equipment/e0001/model/c0601e0001_met.mdl"})
                for name in old.namelist():
                    if name != changed:
                        self.assertEqual(old.read(name), new.read(name))
                group = json.loads(new.read(changed))
                original_miqote = next(o for o in group["Options"] if o["Name"] == "Miqote")
                self.assertEqual(original_miqote["Manipulations"], [{"Type": "Eqp"}])
                target = next(o for o in group["Options"] if o["Name"] == "Elezen Female")
                self.assertEqual(target["Files"], {"chara/equipment/e0001/model/c0601e0001_met.mdl": "elezen female\\chara\\equipment\\e0001\\model\\c0601e0001_met.mdl"})
                self.assertEqual(new.read("elezen female/chara/equipment/e0001/model/c0601e0001_met.mdl"), mdl.read_bytes())
                self.assertEqual(target["FileSwaps"], {})
                self.assertEqual(target["Manipulations"], [])

    def test_accepts_renamed_mdl_and_infers_target_path_from_mod_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother, _, glb, _ = self._v3_fixture(td)
            renamed = td / "yuananjing_ear.mdl"
            renamed.write_bytes(b"RENAMED_TARGET_MODEL_BYTES_" + bytes(range(32)))
            out = td / "renamed-staging.pmp"
            result = build_pending_option_pmp(
                mother, out, adapted_glb=glb, target_base_mdl=renamed,
                option_group="Ears", target_race="Elezen Male"
            )
            self.assertEqual(result["target_option_files_count"], 1)
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                expected = "elezen male/chara/equipment/e0001/model/c0501e0001_met.mdl"
                self.assertIn(expected, names)
                group = json.loads(zf.read("group_001_ears.json"))
                option = next(o for o in group["Options"] if o["Name"] == "Elezen Male")
                self.assertEqual(option["Files"], {
                    "chara/equipment/e0001/model/c0501e0001_met.mdl":
                    "elezen male\\chara\\equipment\\e0001\\model\\c0501e0001_met.mdl"
                })

    def test_v3_existing_target_requires_explicit_replace(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother, _, glb, mdl = self._v3_fixture(td)
            out = td / "staging.pmp"
            build_pending_option_pmp(mother, out, adapted_glb=glb, target_base_mdl=mdl, option_group="Ears", target_race="Elezen Female")
            with self.assertRaises(PackageBuildError):
                build_pending_option_pmp(out, td / "staging2.pmp", adapted_glb=glb, target_base_mdl=mdl, option_group="Ears", target_race="Elezen Female")
            result = build_pending_option_pmp(out, td / "staging2.pmp", adapted_glb=glb, target_base_mdl=mdl, option_group="Ears", target_race="Elezen Female", replace_existing=True)
            self.assertEqual(result["target_option_files_count"], 1)

    def test_v4_build_updates_embedded_groups(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother = td / "v4.pmp"
            glb = td / "adapted.glb"
            glb.write_bytes(b"glTF" + (2).to_bytes(4, "little") + (24).to_bytes(4, "little") + (4).to_bytes(4, "little") + (0x4E4F534A).to_bytes(4, "little") + b"{}  ")
            meta = {"FileVersion": 4, "Name": "V4 Test", "Groups": [{
                "Name": "Head Accessory", "Options": [{"Name": "Human", "Files": {"chara/accessory/a0047/model/c1101a0047_ear.mdl": "lalafell/model/c1101a0047_ear.mdl"}, "FileSwaps": {}, "Manipulations": [{"Type": "Eqp"}], "Description": "x"}]
            }]}
            _write_zip(mother, {"meta.json": json.dumps(meta), "data/model.bin": b"keep"})
            info = inspect_pmp_option_groups(mother)
            self.assertEqual(info["file_version"], 4)
            out = td / "out.pmp"
            mdl = td / "c0501e6047_met.mdl"
            mdl.write_bytes(b"TEST_TARGET_MALE_MDL_BYTES_" + bytes(range(32)))
            build_pending_option_pmp(mother, out, adapted_glb=glb, target_base_mdl=mdl, option_group="Head Accessory", target_race="Elezen Male")
            with zipfile.ZipFile(out) as zf:
                new_meta = json.loads(zf.read("meta.json"))
                options = new_meta["Groups"][0]["Options"]
                self.assertEqual(len(options), 2)
                target = next(o for o in options if o["Name"] == "Elezen Male")
                self.assertEqual(target["Files"], {"chara/accessory/a0047/model/c0501a0047_ear.mdl": "elezen male\\chara\\accessory\\a0047\\model\\c0501a0047_ear.mdl"})
                self.assertEqual(target["Manipulations"], [])
                self.assertEqual(zf.read("data/model.bin"), b"keep")

    def test_cannot_overwrite_mother(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother, _, glb, mdl = self._v3_fixture(td)
            with self.assertRaises(PackageBuildError):
                build_pending_option_pmp(mother, mother, adapted_glb=glb, target_base_mdl=mdl, option_group="Ears")

    def test_glb_is_required_before_pmp_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother, _, glb, mdl = self._v3_fixture(td)
            missing = td / "missing.glb"
            with self.assertRaisesRegex(PackageBuildError, "先在步骤 1 生成适配 GLB"):
                build_pending_option_pmp(mother, td / "out.pmp", adapted_glb=missing, target_base_mdl=mdl, option_group="Ears")
            bad = td / "bad.glb"
            bad.write_bytes(b"glTF" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little"))
            with self.assertRaisesRegex(PackageBuildError, "不是有效的 GLB|GLB 头部校验失败"):
                build_pending_option_pmp(mother, td / "out2.pmp", adapted_glb=bad, target_base_mdl=mdl, option_group="Ears")


    def test_renamed_mdl_is_accepted_when_mod_mapping_identifies_resource(self):
        with tempfile.TemporaryDirectory() as temp:
            td = Path(temp)
            mother, _, glb, _ = self._v3_fixture(td)
            renamed = td / "yuananjing_ear.mdl"
            renamed.write_bytes(b"RENAMED_MODEL_BYTES_" + bytes(range(32)))
            result = build_pending_option_pmp(
                mother, td / "out.pmp", adapted_glb=glb, target_base_mdl=renamed,
                option_group="Ears", target_race="Elezen Male"
            )
            self.assertEqual(result["target_option_files_count"], 1)


if __name__ == "__main__":
    unittest.main()
