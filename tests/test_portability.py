import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "tools" / "package_skill.py"


class PortabilityTests(unittest.TestCase):
    def test_skill_metadata_is_single_line_and_claude_compatible(self):
        text = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(?P<front>.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match, "SKILL.md needs YAML frontmatter")
        front = match.group("front")
        name = re.search(r"^name:\s*(.+)$", front, re.M)
        description = re.search(r"^description:\s*(.+)$", front, re.M)
        self.assertIsNotNone(name)
        self.assertIsNotNone(description)
        self.assertLessEqual(len(name.group(1)), 64)
        self.assertLessEqual(len(description.group(1)), 200)
        self.assertEqual(len(front.splitlines()), 2, "portable metadata should use only name and description")
        self.assertTrue((ROOT / "skill" / "agents" / "openai.yaml").is_file())

    def test_skill_zip_has_a_named_root_folder_and_all_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "skill.zip"
            result = subprocess.run([sys.executable, str(PACKAGER), "--format", "skill", "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("skill-time-machine/SKILL.md", names)
            self.assertIn("skill-time-machine/scripts/time_machine.py", names)
            self.assertIn("skill-time-machine/agents/openai.yaml", names)
            self.assertFalse(any(".time-machine/" in name or "__pycache__" in name for name in names))

    def test_openai_plugin_zip_has_manifest_and_embedded_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "plugin.zip"
            result = subprocess.run([sys.executable, str(PACKAGER), "--format", "openai-plugin", "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("plugin.json"))
                names = set(archive.namelist())
            self.assertEqual(manifest["name"], "skill-time-machine")
            self.assertIn("skills/skill-time-machine/SKILL.md", names)
            self.assertIn("skills/skill-time-machine/scripts/time_machine.py", names)


if __name__ == "__main__":
    unittest.main()
