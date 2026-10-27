"""금액 계산·문장 도우미 시험. 실행: python -m unittest (hidoc_maker 폴더에서)"""

import unittest

from hidoc.money import eul_reul, split_amount, won_to_korean


class SplitAmountTest(unittest.TestCase):
    # 0.5원 반올림 기준은 담당자 답변 대기 중(docs/문의사항.md 1번)이라 끝자리가 딱 떨어지는 값만 시험
    def test_separate_vat(self):
        self.assertEqual(split_amount(2, 450_000, "별도"), (900_000, 90_000))

    def test_included_vat(self):
        self.assertEqual(split_amount(1, 1_100_000, "포함"), (1_000_000, 100_000))

    def test_included_vat_sums_to_amount(self):
        supply, tax = split_amount(3, 125_000, "포함")
        self.assertEqual(supply + tax, 375_000)

    def test_no_vat(self):
        self.assertEqual(split_amount(5, 1_000, "없음"), (5_000, 0))


class WonToKoreanTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(won_to_korean(0), "영")
        self.assertEqual(won_to_korean(4_125_000), "사백일십이만오천")
        self.assertEqual(won_to_korean(1_650_000), "일백육십오만")
        self.assertEqual(won_to_korean(100_000_000), "일억")
        self.assertEqual(won_to_korean(1_000_010), "일백만일십")


class EulReulTest(unittest.TestCase):
    def test_hangul(self):
        self.assertEqual(eul_reul("카메라"), "를")
        self.assertEqual(eul_reul("렌즈 설계"), "를")
        self.assertEqual(eul_reul("서버용 SSD 구입"), "을")

    def test_digit_and_other(self):
        self.assertEqual(eul_reul("H100"), "을")
        self.assertEqual(eul_reul("모델 2"), "를")
        self.assertEqual(eul_reul("SSD"), "을(를)")


if __name__ == "__main__":
    unittest.main()
