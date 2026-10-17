from __future__ import annotations
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.gui import (  # noqa: E402
    GLB_FILETYPES, GLB_OUTPUT_FILETYPES, EQUIPMENT_MODEL_FILETYPES, MDL_FILETYPES, PMP_FILETYPES, ZIP_FILETYPES,
)

class GuiFileDialogFilterTests(unittest.TestCase):
    def test_model_picker_offers_gltf_and_glb(self):
        patterns = {pattern for _label, pattern in GLB_FILETYPES}
        self.assertIn("*.gltf", patterns)
        self.assertIn("*.glb", patterns)

    def test_equipment_picker_offers_gltf_glb_and_mdl(self):
        patterns = {pattern for _label, pattern in EQUIPMENT_MODEL_FILETYPES}
        self.assertIn("*.gltf", patterns)
        self.assertIn("*.glb", patterns)
        self.assertIn("*.mdl", patterns)

    def test_output_picker_defaults_to_single_glb_extension(self):
        self.assertEqual(GLB_OUTPUT_FILETYPES, (("二进制 GLB 输出 (*.glb)", "*.glb"),))

    def test_mdl_picker_only_shows_mdl(self):
        self.assertEqual(MDL_FILETYPES, (("MDL 模型 (*.mdl)", "*.mdl"),))

    def test_archive_pickers_are_filtered(self):
        self.assertIn("*.pmp", PMP_FILETYPES[0][1])
        self.assertIn("*.ttmp2", PMP_FILETYPES[0][1])
        self.assertEqual(ZIP_FILETYPES[0][1], "*.zip")
        all_patterns = [pattern for group in (GLB_FILETYPES, EQUIPMENT_MODEL_FILETYPES, MDL_FILETYPES, PMP_FILETYPES, ZIP_FILETYPES) for _label, pattern in group]
        self.assertNotIn("*.*", all_patterns)

    def test_pmp_gui_does_not_require_success_zip_or_modified_mdl(self):
        source = (ROOT / "src" / "accessory_adapter" / "gui.py").read_text(encoding="utf-8")
        self.assertNotIn("成功案例参考 ZIP（男精 V3）", source)
        self.assertNotIn("Penumbra 导出的目标 MDL", source)
        self.assertIn("目标种族原版装备 MDL（必需）", source)
        self.assertIn("build_pending_option_pmp", source)
        self.assertIn("要添加选项的原有选项组", source)

    def test_three_step_flow_requires_adapted_glb_before_pmp(self):
        source = (ROOT / "src" / "accessory_adapter" / "gui.py").read_text(encoding="utf-8")
        self.assertIn("步骤 2 · GLB + 原版 MDL 构建 PMP", source)
        self.assertIn("步骤 3 · Penumbra 绑定并保存", source)
        self.assertIn("'adapted_glb'", source)
        self.assertIn("adapted_glb=p['adapted_glb']", source)

if __name__ == "__main__":
    unittest.main()
