"""금액 계산과 문장 도우미 - 입력창, 한글 문서, 하이웍스용 복사, 견적서 읽기에서 함께 씀"""

VAT_RATE = 0.1
# 품목별 세액 처리: 별도 = 단가에 10% 추가 / 포함 = 단가에 부가세 포함 / 없음 = 면세
VAT_MODES = ["별도", "포함", "없음"]


def split_amount(qty: int, price: int, mode: str) -> tuple[int, int]:
    """한 품목의 (공급가액, 세액)"""
    amount = qty * price
    if mode == "별도":
        return amount, round(amount * VAT_RATE)
    if mode == "포함":
        supply = round(amount / (1 + VAT_RATE))
        return supply, amount - supply
    return amount, 0


def won_to_korean(amount: int) -> str:
    """4125000 -> '사백일십이만오천'"""
    if amount == 0:
        return "영"
    digits = "영일이삼사오육칠팔구"
    small = ["", "십", "백", "천"]
    big = ["", "만", "억", "조", "경"]
    result = []
    group = 0
    while amount > 0:
        chunk = amount % 10000
        amount //= 10000
        if chunk:
            text = ""
            for i in range(3, -1, -1):
                d = (chunk // 10 ** i) % 10
                if d:
                    text += digits[d] + small[i]
            result.insert(0, text + big[group])
        group += 1
    return "".join(result)


def payment_lines(payment: str, details: list[str]) -> list[str]:
    """품의서 4번 지급방식 항목의 줄들. 지급방식과 상세가 모두 비면 [] (항목을 넣지 않음).
    상세만 있으면 '4. 지급방식' 제목 아래 상세만 넣음. 상세 줄 앞에는 '- '를 붙임"""
    if not payment and not details:
        return []
    head = f"4. 지급방식 : {payment}" if payment else "4. 지급방식"
    return [head] + [ln if ln.startswith("-") else f"- {ln}" for ln in details]


def eul_reul(word: str) -> str:
    """마지막 글자 받침에 맞는 목적격 조사"""
    last = word.rstrip()[-1:] or " "
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    if last.isdigit():
        return "을" if last in "013678" else "를"
    return "을(를)"
