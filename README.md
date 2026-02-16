# Stock Portfolio Dashboard

증권 중심 포트폴리오의 현재 상태(평가금액, 손익, 비중)를 보여주고, 리밸런싱 업데이트 계획까지 제안하는 `Streamlit` 앱입니다.

## 1) 설치

```bash
pip install -r requirements.txt
```

## 2) 실행

```bash
streamlit run app.py
```

## 3) 데이터 형식

사이드바에서 아래 중 하나를 선택할 수 있습니다.

- Google Sheets URL 입력
- CSV 업로드
- 샘플 데이터

### Google Sheets 사용 시

링크 예시:

`https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit?gid=0#gid=0`

주의:
- 앱은 내부적으로 `export?format=csv&gid=...` 방식으로 읽습니다.
- 시트가 비공개면 로딩에 실패합니다. `링크가 있는 사용자 보기` 권한이 필요합니다.
- 시트 상단에 요약 행이 있어도 헤더 행을 자동 탐지합니다.
- 한국어 시트 포맷에서는 `현재가`를 현재 평가금액(총액)으로 해석해 계산합니다.

필수 컬럼:
- `ticker`: 티커 심볼 (예: AAPL)
- `shares`: 보유 수량
- `avg_cost`: 평균 매입 단가

예시:

```csv
ticker,shares,avg_cost
AAPL,12,165
MSFT,8,330
NVDA,5,800
TSLA,4,220
```

## 4) 업데이트 계획(리밸런싱)

평가 결과 아래에서:
- `올웨더 + 배당주 40%(기본)` 자동 계획
- `동일 비중(Equal Weight)` 자동 계획
- `직접 목표 비중 입력` 기반 계획

을 선택할 수 있고, 종목별 `BUY/SELL/HOLD` 제안을 확인할 수 있습니다.

## 5) 분석 필터(기본값)

- `보증금(부동산) 제외`: ON
- `증권만 분석`: ON

즉, 기본 화면은 부동산 보증금을 제외하고 증권 투자(국내/해외/원자재 포함)를 중심으로 평가합니다.
