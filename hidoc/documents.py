"""첫 화면의 '문서 만들기' 목록

새 문서를 추가하려면: 작성 화면 클래스(ttk.Frame, 생성자에 master 하나, refresh_from_settings()·reset() 메서드)를 만들고
아래 DOCUMENTS 에 한 줄 추가하면 첫 화면에 버튼이 생김.
"""

from dataclasses import dataclass

from .purchase_form import PurchaseRequestForm


@dataclass(frozen=True)
class DocumentType:
    key: str  # 내부 이름
    name: str  # 버튼 제목
    description: str  # 버튼 아래 한 줄 설명
    form_class: type  # 작성 화면


DOCUMENTS = [
    DocumentType("purchase_request", "구매 품의서",
                 "견적서를 읽어 한글(.hwp) 품의서를 만들고, 붙임 서류를 기업·날짜별 폴더에 정리합니다.",
                 PurchaseRequestForm),
]
