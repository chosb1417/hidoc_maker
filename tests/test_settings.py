"""설정 기본값과 설정을 쓰는 곳 시험. 실제 settings.json 대신 임시 파일을 씀"""

import json
import tempfile
import unittest
from pathlib import Path

from hidoc import environment, settings, storage


class TempSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.real_path = settings.SETTINGS_PATH
        settings.SETTINGS_PATH = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        settings.SETTINGS_PATH = self.real_path
        self.tmp.cleanup()

    def write(self, data):
        settings.SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class GetSettingTest(TempSettingsTest):
    def test_defaults_without_file(self):
        self.assertEqual(settings.get_setting("save_dir"), str(settings.DEFAULT_SAVE_DIR))
        self.assertEqual(settings.get_setting("read_mode"), "local")
        self.assertEqual(settings.get_setting("payment_example"), "선금 50% , 잔금 50%")
        self.assertIn("지아이랩", settings.get_setting("company_names"))

    def test_saved_value_wins_and_empty_falls_back(self):
        self.write({"read_mode": "claude_code", "save_dir": ""})
        self.assertEqual(settings.get_setting("read_mode"), "claude_code")
        self.assertEqual(settings.get_setting("save_dir"), str(settings.DEFAULT_SAVE_DIR))

    def test_output_dir_always_hidoc_output(self):
        self.assertEqual(settings.output_dir("D:/구매"), Path("D:/구매/hidoc_output"))
        self.assertEqual(settings.output_dir("D:/구매/hidoc_output"), Path("D:/구매/hidoc_output"))  # 겹치지 않음
        self.assertEqual(settings.output_dir(), settings.ROOT_DIR / "hidoc_output")  # 기본값

    def test_update_keeps_other_values(self):
        self.write({"read_mode": "claude"})
        settings.update_settings(quote_dir="D:/견적서")
        self.assertEqual(settings.load_settings(), {"read_mode": "claude", "quote_dir": "D:/견적서"})


class StorageUsesSettingsTest(TempSettingsTest):
    def test_default_company_docs(self):
        self.assertEqual(storage.copy_name("통장사본", "한빛테크(주)", "a.pdf", "261028"), "[통장사본]한빛테크(주).pdf")
        self.assertEqual(storage.copy_name("견적서", "한빛테크(주)", "a.pdf", "261028"), "[견적서]한빛테크(주)_261028.pdf")

    def test_custom_attach_settings(self):
        self.write({"company_docs": ["견적서"], "attach_types": ["견적서", "계약서"]})
        self.assertEqual(storage.copy_name("견적서", "한빛", "a.pdf", "261028"), "[견적서]한빛.pdf")
        self.assertEqual(storage.attach_types(), ["견적서", "계약서"])


class EnvironmentTest(unittest.TestCase):
    def test_run_checks_shape(self):
        rows = environment.run_checks()
        self.assertEqual([name for name, _, _ in rows], [name for name, _ in environment.CHECKS])
        for _, ok, detail in rows:
            self.assertIsInstance(ok, bool)
            self.assertTrue(detail)


if __name__ == "__main__":
    unittest.main()
