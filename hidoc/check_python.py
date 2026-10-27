"""실행.bat 이 쓸 Python 확인용. Tk 9 이상(Python 3.14 이상)이면 이 Python 의 경로를 출력하고, 아니면 아무것도 출력하지 않음.
Tk 9 가 필요한 이유: 입력칸 예시 글자(placeholder) 등. 실행.bat 에서 hidoc\\check_python.py 로 직접 실행함
"""

import sys
import tkinter

if tkinter.TkVersion >= 9.0:
    print(sys.executable)
