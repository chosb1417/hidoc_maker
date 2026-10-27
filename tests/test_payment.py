"""4번 지급방식 항목: 입력하지 않으면 빠지는지 (한글 문서와 하이웍스용 HTML이 같은 규칙)"""

import unittest

from hidoc.html_doc import build_html
from hidoc.money import payment_lines

DOC = {"target": "주차 카메라", "title": "주차 카메라 구매의 건", "vendor": "한빛테크(주)", "vat_note": False,
       "attach": ["[견적서]한빛테크(주) 1부."]}
ITEMS = [{"name": "카메라", "qty": 1, "price": 1000, "vat": "별도", "note": ""}]


class PaymentLinesTest(unittest.TestCase):
    def test_both_empty_removes_item(self):
        self.assertEqual(payment_lines("", []), [])

    def test_payment_and_details(self):
        self.assertEqual(payment_lines("선금 50%", ["발주 시 지급", "- 이미 붙은 줄"]),
                         ["4. 지급방식 : 선금 50%", "- 발주 시 지급", "- 이미 붙은 줄"])

    def test_details_only_keeps_heading(self):
        self.assertEqual(payment_lines("", ["계약 시 전액"]), ["4. 지급방식", "- 계약 시 전액"])

    def test_shop_only_is_item_4(self):
        self.assertEqual(payment_lines("", [], "https://cart.coupang.com/x"), ["4. 구매처 : https://cart.coupang.com/x"])

    def test_shop_after_payment_is_item_5(self):
        self.assertEqual(payment_lines("카드", [], "https://a.b"), ["4. 지급방식 : 카드", "5. 구매처 : https://a.b"])


class HtmlPaymentTest(unittest.TestCase):
    def test_html_without_payment(self):
        html = build_html({**DOC, "payment": "", "payment_detail": []}, ITEMS)
        self.assertNotIn("지급방식", html)
        self.assertIn("붙", html)

    def test_html_with_payment(self):
        html = build_html({**DOC, "payment": "후불", "payment_detail": []}, ITEMS)
        self.assertIn("4. 지급방식 : 후불", html)

    def test_html_with_shop(self):
        html = build_html({**DOC, "payment": "", "payment_detail": [], "shop": "https://cart.coupang.com/cartView.pang?a=1&b=2"}, ITEMS)
        self.assertIn("4. 구매처 : https://cart.coupang.com/cartView.pang?a=1&amp;b=2", html)
        self.assertNotIn("지급방식", html)


if __name__ == "__main__":
    unittest.main()
