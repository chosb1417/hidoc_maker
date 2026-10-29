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
    def test_copy_name(self):
        # 기업 공통 서류도 날짜를 붙임 (저장 위치만 날짜 폴더 밖)
        self.assertEqual(storage.copy_name("통장사본", "한빛테크(주)", "a.pdf", "261028"), "[통장사본]한빛테크(주)_261028.pdf")
        self.assertEqual(storage.copy_name("견적서", "한빛테크(주)", "a.pdf", "261028"), "[견적서]한빛테크(주)_261028.pdf")
        self.assertEqual(storage.copy_name("견적서", "H100 설계", "a.pdf", "261028", as_is=True), "H100_설계.pdf")

    def test_custom_attach_settings(self):
        self.write({"attach_types": ["견적서", "계약서"]})
        self.assertEqual(storage.attach_types(), ["견적서", "계약서"])

    def test_company_docs_outside_date_folder_and_kept_if_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "통장.pdf"
            src.write_bytes(b"same")
            company, folder = tmp / "한빛", tmp / "한빛" / "261030"
            folder.mkdir(parents=True)
            (company / "[통장사본]한빛.pdf").write_bytes(b"same")  # 예전(날짜 없는 이름)에 저장한 같은 파일
            est = tmp / "견적.pdf"
            est.write_bytes(b"x")
            copied = storage.copy_attachments([("통장사본", "한빛", str(src), False), ("견적서", "한빛", str(est), False)],
                                              company, folder, "261030", set())
            self.assertEqual(copied, ["[통장사본]한빛.pdf (같은 파일이 있어 유지)", str(Path("261030") / "[견적서]한빛_261030.pdf")])
            src.write_bytes(b"new")  # 내용이 바뀌면 날짜를 붙여 기업 폴더에 새로 저장
            copied = storage.copy_attachments([("통장사본", "한빛", str(src), False)], company, folder, "261030", set())
            self.assertEqual(copied, ["[통장사본]한빛_261030.pdf"])


class CompanyFoldersTest(unittest.TestCase):
    def test_lists_company_folders_newest_first(self):
        import os, time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hidoc_output"
            for name in ("엠에스산업", "한빛테크(주)"):
                (root / name).mkdir(parents=True)
            (root / "preview.html").write_text("x", encoding="utf-8")  # 파일은 목록에서 뺌
            now = time.time()
            os.utime(root / "엠에스산업", (now, now))
            os.utime(root / "한빛테크(주)", (now - 100, now - 100))
            self.assertEqual(storage.company_folders(tmp), ["엠에스산업", "한빛테크(주)"])

    def test_missing_folder_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(storage.company_folders(tmp), [])


class EnvironmentTest(unittest.TestCase):
    def test_run_checks_shape(self):
        rows = environment.run_checks()
        self.assertEqual([name for name, _, _ in rows], [name for name, _ in environment.CHECKS])
        for _, ok, detail in rows:
            self.assertIsInstance(ok, bool)
            self.assertTrue(detail)


if __name__ == "__main__":
    unittest.main()
