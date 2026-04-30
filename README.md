# 🇰🇷 한국 주요 종목 추적 테이블

KRX(한국거래소) 데이터를 기반으로 주요 종목의 수익률을 추적하는 테이블입니다.  
GitHub Actions를 통해 **매 거래일 오후 4시 (KST)** 자동 업데이트됩니다.

---

## 📊 컬럼 설명

| 컬럼 | 설명 |
|------|------|
| **거래대금 증가** | 최근 20일 평균 거래대금 ÷ 기준일 이후 초기 20일 평균 거래대금 (배수) |
| **수익률** | 기준일 종가 → 현재 종가 상승률 (%) |
| **수익률 − 시총증가** | 수익률(%) − 시가총액 증가율(%) → 양수일수록 자사주 매입 효과 등이 큰 종목 |

## 🎨 색상 기준

- 🟡 **노란색 행**: 수익률 ≥ 300%
- 🟢 **초록색 행**: 수익률 ≥ 120%
- 🔴 **분홍색 행**: 수익률 < 40%

---

## ⚙️ 설정 방법

### 1. 레포 Fork 또는 생성 후 파일 업로드

```
/
├── .github/workflows/update.yml
├── generate.py
├── requirements.txt
└── index.html  ← 자동 생성됨
```

### 2. GitHub Pages 활성화

`Settings` → `Pages` → `Source: Deploy from a branch` → `main` 브랜치 `/root` 선택

### 3. 기준일 변경하기

`generate.py` 상단의 `START_DATE`를 원하는 날짜로 변경하거나,  
Actions 탭에서 워크플로우를 수동 실행할 때 날짜를 입력하세요.

### 4. 종목 추가/제거

`generate.py`의 `TICKERS` 리스트를 수정하세요:

```python
TICKERS = [
    ("005930", "삼성전자"),
    ("000660", "SK하이닉스"),
    # 추가할 종목 (KRX 6자리 티커, 표시명)
    ("259960", "크래프톤"),
]
```

---

## 🔧 로컬 실행

```bash
pip install -r requirements.txt
python generate.py
# → index.html 생성됨
```

기준일 변경:
```bash
START_DATE=20210101 python generate.py
```

---

## 📌 참고

- 데이터 출처: [pykrx](https://github.com/sharebook-kr/pykrx) (KRX 공식 데이터)
- 장 마감 후 약 30분 뒤 업데이트 (시간외 거래 반영 전)
