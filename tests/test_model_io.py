import json
import struct
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from accessory_adapter.model_io import GLBDocument, read_accessor, read_glb, read_model, node_name, validate_glb, write_accessor, write_glb
from accessory_adapter.model_analysis import analyze_model
from accessory_adapter.skeleton_mapping import build_skeleton_mapping
from accessory_adapter.adapters.head import adapt_head_accessory


def make_glb(path: Path, *, skeleton_names=("root", "j_kao", "j_tail"),
             joint_names=None) -> None:
    """Create a tiny valid GLB fixture with POSITION, skin attributes and an IBM accessor."""
    if joint_names is None:
        joint_names = list(range(len(skeleton_names)))
    binary = bytearray()
    positions = [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (-1.0, 0.5, 2.0)]
    for p in positions:
        binary.extend(struct.pack("<3f", *p))
    joints_offset = len(binary)
    for _ in positions:
        binary.extend(struct.pack("<4B", 0, 0, 0, 0))
    weights_offset = len(binary)
    for _ in positions:
        binary.extend(struct.pack("<4f", 1.0, 0.0, 0.0, 0.0))
    ibm_offset = len(binary)
    identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    for _ in joint_names:
        binary.extend(struct.pack("<16f", *identity))
    mesh_node_index = len(skeleton_names)
    nodes = [{"name": skeleton_names[0], "children": list(range(1, len(skeleton_names)))}]
    nodes.extend({"name": name} for name in skeleton_names[1:])
    nodes.append({"name": "AccessoryMesh", "mesh": 0, "skin": 0})
    doc = {
        "asset": {"version": "2.0", "generator": "unit-test"},
        "scene": 0,
        "scenes": [{"nodes": [0, mesh_node_index]}],
        "nodes": nodes,
        "meshes": [{"name": "test-mesh", "primitives": [{"attributes": {
            "POSITION": 0, "JOINTS_0": 1, "WEIGHTS_0": 2
        }}]}],
        "skins": [{"name": "test-skin", "joints": list(joint_names), "inverseBindMatrices": 3}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": joints_offset, "byteLength": 12},
            {"buffer": 0, "byteOffset": weights_offset, "byteLength": 48},
            {"buffer": 0, "byteOffset": ibm_offset, "byteLength": len(binary) - ibm_offset},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [-1.0, 0.0, 0.0], "max": [1.0, 1.0, 2.0]},
            {"bufferView": 1, "componentType": 5121, "count": 3, "type": "VEC4"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC4"},
            {"bufferView": 3, "componentType": 5126, "count": len(joint_names), "type": "MAT4"},
        ],
    }
    json_chunk = json.dumps(doc, separators=(",", ":")).encode()
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    bin_chunk = bytes(binary) + b"\0" * ((4 - len(binary) % 4) % 4)
    body = struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk
    body += struct.pack("<I4s", len(bin_chunk), b"BIN\0") + bin_chunk
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)

class ModelIOTests(unittest.TestCase):
    def test_read_write_roundtrip_and_accessor(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.glb"
            output = Path(temp) / "output.glb"
            make_glb(source)
            model = read_glb(source)
            self.assertEqual(read_accessor(model, 0)[1], [1.0, 1.0, 1.0])
            write_accessor(model, 0, [[0.0, 2.0, 0.0], [1.0, 2.0, 1.0], [-1.0, 2.0, 2.0]])
            write_glb(model, output)
            reopened = read_glb(output)
            self.assertEqual(read_accessor(reopened, 0)[0], [0.0, 2.0, 0.0])
            self.assertEqual(validate_glb(reopened), [])

    def test_analysis_reports_mesh_skin_and_validity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.glb"
            make_glb(path)
            report = analyze_model(read_glb(path))
            self.assertEqual(report["summary"]["mesh_count"], 1)
            self.assertEqual(report["summary"]["skin_count"], 1)
            self.assertEqual(report["summary"]["validation_error_count"], 0)
            self.assertEqual(report["skins"][0]["joint_count"], 3)

    def test_skeleton_mapping_exact_names_and_unmatched(self):
        with tempfile.TemporaryDirectory() as temp:
            source_path = Path(temp) / "source.glb"
            target_path = Path(temp) / "target.glb"
            make_glb(source_path, skeleton_names=("root", "j_kao", "j_tail"))
            make_glb(target_path, skeleton_names=("root", "j_kao"), joint_names=(0, 1))
            source = read_glb(source_path)
            target = read_glb(target_path)
            result = build_skeleton_mapping(source.json, 0, target.json, 0)
            self.assertEqual(result["matched_count"], 2)
            self.assertEqual(result["unmatched_count"], 1)
            self.assertEqual(result["unmatched"][0]["source_name"], "j_tail")

    def test_skeleton_alias_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            source_path = Path(temp) / "source.glb"
            target_path = Path(temp) / "target.glb"
            make_glb(source_path, skeleton_names=("root", "j_kao", "j_tail"))
            make_glb(target_path, skeleton_names=("root", "head_joint", "tail_joint"))
            result = build_skeleton_mapping(
                read_glb(source_path).json, 0, read_glb(target_path).json, 0,
                aliases={"j_kao": "head_joint", "j_tail": "tail_joint"},
            )
            self.assertEqual(result["matched_count"], 3)
            self.assertEqual(sum(m["match_type"] == "explicit_alias" for m in result["matches"]), 2)

    def test_head_adapter_keeps_source_and_rebinds_vertices(self):
        with tempfile.TemporaryDirectory() as temp:
            source_path = Path(temp) / "source.glb"
            output_path = Path(temp) / "adapted.glb"
            make_glb(source_path)
            source_bytes = source_path.read_bytes()
            result = adapt_head_accessory(source_path, output_path, y_offset=0.25)
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(result["head_joint_index"], 1)
            adapted = read_glb(output_path)
            positions = read_accessor(adapted, 0)
            joints = read_accessor(adapted, 1)
            weights = read_accessor(adapted, 2)
            self.assertAlmostEqual(positions[0][1], 0.25)
            self.assertEqual(joints[0], [1, 0, 0, 0])
            self.assertEqual(weights[0], [1.0, 0.0, 0.0, 0.0])
            self.assertEqual(validate_glb(adapted), [])

    def test_head_adapter_rebuilds_skin_from_target_skeleton_and_prunes_other_meshes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source_path = folder / "source.glb"
            target_path = folder / "target.glb"
            output_path = folder / "adapted_target_skeleton.glb"
            make_glb(source_path, skeleton_names=("root", "j_kao", "j_tail"))
            make_glb(target_path, skeleton_names=("root", "j_kao"), joint_names=(0, 1))

            result = adapt_head_accessory(
                source_path, output_path, y_offset=0.25,
                target_skeleton_path=target_path,
            )
            adapted = read_glb(output_path)
            target = read_glb(target_path)
            self.assertTrue(result["target_skeleton_rebind"]["inverse_bind_matrices_replaced"])
            self.assertEqual(len(adapted.json["meshes"]), 1)
            self.assertEqual(len(adapted.json["skins"]), 1)
            self.assertEqual(len(adapted.json["skins"][0]["joints"]), 2)
            self.assertEqual(
                [node_name(adapted.json, n) for n in adapted.json["skins"][0]["joints"]],
                [node_name(target.json, n) for n in target.json["skins"][0]["joints"]],
            )
            self.assertEqual(
                read_accessor(adapted, adapted.json["skins"][0]["inverseBindMatrices"]),
                read_accessor(target, target.json["skins"][0]["inverseBindMatrices"]),
            )
            self.assertEqual(validate_glb(adapted), [])

    def test_read_standalone_gltf_with_external_bin_and_image(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            glb_path = folder / "fixture.glb"
            gltf_path = folder / "fixture.gltf"
            output_path = folder / "converted.glb"
            make_glb(glb_path)
            original = read_glb(glb_path)
            # Build a standalone glTF from the GLB's JSON and external BIN buffer.
            doc = original.json
            doc["buffers"][0]["uri"] = "fixture.bin"
            (folder / "fixture.bin").write_bytes(bytes(original.binary))
            (folder / "tiny.png").write_bytes(b"fake-png-test-bytes")
            doc["images"] = [{"uri": "tiny.png"}]
            gltf_path.write_text(json.dumps(doc), encoding="utf-8")

            loaded = read_model(gltf_path)
            self.assertEqual(bytes(loaded.binary), bytes(original.binary))
            self.assertTrue(loaded.json["images"][0]["uri"].startswith("data:image/png;base64,"))
            self.assertNotIn("uri", loaded.json["buffers"][0])
            write_glb(loaded, output_path)
            reopened = read_glb(output_path)
            self.assertEqual(read_accessor(reopened, 0)[1], [1.0, 1.0, 1.0])
            self.assertTrue(reopened.json["images"][0]["uri"].startswith("data:image/png;base64,"))

    def test_read_model_rejects_missing_gltf_companion_bin(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            gltf_path = folder / "missing.gltf"
            gltf_path.write_text(json.dumps({
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "missing.bin", "byteLength": 4}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "配套文件不存在"):
                read_model(gltf_path)

    def test_head_adapter_accepts_standalone_gltf_source(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source_glb = folder / "source.glb"
            source_gltf = folder / "source.gltf"
            output_glb = folder / "adapted.glb"
            make_glb(source_glb)
            source_doc = read_glb(source_glb)
            source_doc.json["buffers"][0]["uri"] = "source.bin"
            (folder / "source.bin").write_bytes(bytes(source_doc.binary))
            source_gltf.write_text(json.dumps(source_doc.json), encoding="utf-8")
            result = adapt_head_accessory(source_gltf, output_glb, y_offset=0.125)
            self.assertEqual(result["vertex_count"], 3)
            adapted = read_glb(output_glb)
            self.assertAlmostEqual(read_accessor(adapted, 0)[0][1], 0.125)


if __name__ == "__main__":
    unittest.main()
