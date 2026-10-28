"""견적서 읽기(로컬 방식) 규칙 시험 - OCR·PDF 없이 줄 문자열로 시험"""

import unittest

from hidoc.quote_reader import _company, _find_valid_until, _find_vendor, _from_claude, _number, _parse_rows


class NumberTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(_number("1,200"), 1200)
        self.assertEqual(_number("1.200.000"), 1200000)
        self.assertEqual(_number("₩1,650,000"), 1650000)
        self.assertEqual(_number("10EA"), 10)
        self.assertIsNone(_number("GE-200"))
        self.assertIsNone(_number("2026.10.27"))

    def test_ocr_misreads(self):
        self.assertEqual(_number("1t650,000"), 1650000)
        self.assertEqual(_number("36이000"), 360000)


class VendorTest(unittest.TestCase):
    def test_skips_our_company_and_recipient(self):
        rows = ["주식회사 지아이랩 귀하", "등록번호 123-45-67890", "상 호 : ㈜한빛테크 대표 : 홍길동"]
        self.assertEqual(_find_vendor(rows), "(주)한빛테크")

    def test_fallback_company_pattern(self):
        self.assertEqual(_find_vendor(["1. 견 적 처 : 한빛테크(주)"]), "한빛테크(주)")

    def test_company_cleanup(self):
        self.assertEqual(_company(". ((주)한빛테크"), "(주)한빛테크")
        self.assertEqual(_company("주식회사 지아이랩"), "")


class ParseRowsTest(unittest.TestCase):
    def test_separate_vat_with_tax_column(self):
        rows = ["상 호 : ㈜한빛테크",
                "NO 품명 규격 수량 단가 공급가액 세액 비고",
                "1 산업용 카메라 GE-200 2 450,000 900,000 90,000",
                "3 설치비 1 360,000 360,000 36,000 현장",
                "합 계 1,260,000 126,000"]
        r = _parse_rows(rows)
        self.assertEqual(r["vendor"], "(주)한빛테크")
        self.assertEqual([(i["name"], i["qty"], i["price"], i["vat"], i["note"]) for i in r["items"]],
                         [("산업용 카메라 GE-200", 2, 450000, "별도", ""), ("설치비", 1, 360000, "별도", "현장")])
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["valid_until"], "")

    def test_included_vat(self):
        r = _parse_rows(["NO 품목 수량 단가 공급가액 세액 합계",
                         "2 렌즈 8mm 3 125,000 340,909 34,091 375,000 예비"])
        item = r["items"][0]
        self.assertEqual((item["qty"], item["price"], item["vat"], item["note"]), (3, 125000, "포함", "예비"))

    def test_price_before_qty(self):
        r = _parse_rows(["품명 단가 수량 금액", "볼트 1,200 10 12,000", "부가세 별도"])
        self.assertEqual((r["items"][0]["qty"], r["items"][0]["price"], r["items"][0]["vat"]), (10, 1200, "별도"))

    def test_warns_when_total_differs(self):
        r = _parse_rows(["품명 수량 단가 금액", "볼트 10 1,200 12,000", "합계 99,000"])
        self.assertTrue(any("합계" in w for w in r["warnings"]))


class ValidUntilTest(unittest.TestCase):
    def test_written_date(self):
        for row in ("유효기간 : 2026.11.30", "견적 유효일 2026-11-30 까지", "유 효 기 간  2026년 11월 30일"):
            self.assertEqual(_find_valid_until(["견적서", row]), ("2026-11-30", None))

    def test_days_from_quote_date(self):
        rows = ["견적일자 : 2026.10.20", "유효기간 : 견적일로부터 30일"]
        self.assertEqual(_find_valid_until(rows), ("2026-11-19", None))

    def test_days_without_quote_date(self):
        valid, warning = _find_valid_until(["유효기간 : 견적일로부터 30일"])
        self.assertEqual(valid, "")
        self.assertIn("견적일", warning)

    def test_not_written(self):
        self.assertEqual(_find_valid_until(["견적일자 2026.10.20", "합계 1,000"]), ("", None))

    def test_claude_result_checked(self):
        data = {"vendor": "(주)한빛테크", "target": "", "items": [], "warnings": []}
        self.assertEqual(_from_claude({**data, "valid_until": "2026-11-30"})["valid_until"], "2026-11-30")
        self.assertEqual(_from_claude({**data, "valid_until": "30일"})["valid_until"], "")


if __name__ == "__main__":
    unittest.main()
