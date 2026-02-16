import io
import re
from typing import Dict, Optional

import pandas as pd
import streamlit as st
import yfinance as yf


st.set_page_config(page_title="Stock Portfolio Dashboard", layout="wide")
st.title("Stock Portfolio Dashboard")
st.caption("포트폴리오 평가와 리밸런싱 업데이트 계획을 보여줍니다.")


STANDARD_REQUIRED_COLUMNS = ["ticker", "shares", "avg_cost"]
KOR_REQUIRED_COLUMNS = ["자산명", "보유수(주/개수)", "평단", "현재가"]
ALL_WEATHER_TARGET = {
    "dividend": 40.0,
    "bond": 25.0,
    "growth": 20.0,
    "commodity": 10.0,
    "cash": 5.0,
}


def to_number(value) -> float:
    if pd.isna(value):
        return float("nan")
    text = str(value).strip()
    if not text:
        return float("nan")
    cleaned = re.sub(r"[^\d\.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return float("nan")
    try:
        return float(cleaned)
    except ValueError:
        return float("nan")


def clean_column_name(col: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(col)).strip()


def normalize_token(text: str) -> str:
    cleaned = clean_column_name(text)
    return re.sub(r"[\s\(\)/_:\-]", "", cleaned)


def extract_headered_frame(df: pd.DataFrame) -> pd.DataFrame:
    for idx in range(min(20, len(df))):
        row = [normalize_token(v) for v in df.iloc[idx].tolist()]
        has_asset = any("자산명" in v for v in row)
        has_avg = any("평단" in v for v in row)
        has_price = any("현재가" in v for v in row)
        if has_asset and has_avg and has_price:
            headers = [clean_column_name(v) if clean_column_name(v) else f"col_{i}" for i, v in enumerate(df.iloc[idx].tolist())]
            body = df.iloc[idx + 1 :].reset_index(drop=True).copy()
            body.columns = headers
            return body
    return df


def find_col(columns: list[str], candidates: list[str]) -> Optional[str]:
    normalized = {c: normalize_token(c) for c in columns}
    for cand in candidates:
        for original, norm in normalized.items():
            if cand in norm:
                return original
    return None


def google_sheet_to_csv_url(sheet_url: str) -> str:
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not match:
        raise ValueError("유효한 Google Sheets URL 형식이 아닙니다.")
    sheet_id = match.group(1)
    gid_match = re.search(r"[?#&]gid=([0-9]+)", sheet_url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


@st.cache_data(ttl=120)
def load_google_sheet(sheet_url: str) -> pd.DataFrame:
    csv_url = google_sheet_to_csv_url(sheet_url.strip())
    raw = pd.read_csv(csv_url, header=None)
    parsed = extract_headered_frame(raw)
    parsed.columns = [clean_column_name(c) for c in parsed.columns]
    return parsed


@st.cache_data(ttl=300)
def fetch_prices(tickers: tuple[str, ...]) -> Dict[str, float]:
    if not tickers:
        return {}
    data = yf.download(
        tickers=list(tickers),
        period="1d",
        interval="1m",
        group_by="ticker",
        progress=False,
        auto_adjust=True,
    )
    prices: Dict[str, float] = {}
    if len(tickers) == 1:
        ticker = tickers[0]
        close_series = data.get("Close")
        if close_series is not None and not close_series.dropna().empty:
            prices[ticker] = float(close_series.dropna().iloc[-1])
        return prices

    for ticker in tickers:
        close_series = data.get((ticker, "Close"))
        if close_series is not None and not close_series.dropna().empty:
            prices[ticker] = float(close_series.dropna().iloc[-1])
    return prices


def parse_standard_format(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [clean_column_name(c).lower() for c in normalized.columns]
    missing = [c for c in STANDARD_REQUIRED_COLUMNS if c not in normalized.columns]
    if missing:
        raise ValueError(
            f"필수 컬럼이 없습니다: {', '.join(missing)}. "
            "필요한 컬럼: ticker, shares, avg_cost"
        )
    normalized = normalized[STANDARD_REQUIRED_COLUMNS].copy()
    normalized["asset"] = normalized["ticker"].astype(str).str.upper().str.strip()
    normalized["shares"] = pd.to_numeric(normalized["shares"], errors="coerce")
    normalized["avg_cost"] = pd.to_numeric(normalized["avg_cost"], errors="coerce")
    normalized = normalized.dropna(subset=["asset", "shares", "avg_cost"])
    normalized = normalized[normalized["shares"] > 0]
    normalized["current_price"] = pd.NA
    normalized["market_value_raw"] = pd.NA
    normalized["cost_basis_raw"] = pd.NA
    return normalized[["asset", "shares", "avg_cost", "current_price", "market_value_raw", "cost_basis_raw"]]


def parse_korean_sheet_format(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [clean_column_name(c) for c in normalized.columns]
    cols = normalized.columns.tolist()
    col_asset = find_col(cols, ["자산명"])
    col_shares = find_col(cols, ["보유수", "보유"])
    col_avg = find_col(cols, ["평단"])
    col_price = find_col(cols, ["현재가"])
    col_cost = find_col(cols, ["투자금액"])
    col_top = find_col(cols, ["대범주"])
    col_type = find_col(cols, ["자산대범주"])
    col_mid = find_col(cols, ["자산중범주"])
    col_country = find_col(cols, ["투자국가"])

    if not all([col_asset, col_shares, col_avg, col_price]):
        raise ValueError("한국어 시트 컬럼을 찾지 못했습니다.")

    use_cols = [col_asset, col_shares, col_avg, col_price]
    if col_cost:
        use_cols.append(col_cost)
    if col_top:
        use_cols.append(col_top)
    if col_type:
        use_cols.append(col_type)
    if col_mid:
        use_cols.append(col_mid)
    if col_country:
        use_cols.append(col_country)
    parsed = normalized[use_cols].copy()
    parsed["asset"] = parsed[col_asset].astype(str).str.strip()
    parsed["shares"] = parsed[col_shares].apply(to_number)
    parsed["avg_cost"] = parsed[col_avg].apply(to_number)
    parsed["market_value_raw"] = parsed[col_price].apply(to_number)
    parsed["current_price"] = parsed["market_value_raw"] / parsed["shares"]
    parsed["cost_basis_raw"] = parsed[col_cost].apply(to_number) if col_cost else (parsed["shares"] * parsed["avg_cost"])
    parsed["asset_group_top"] = parsed[col_top].astype(str).str.strip() if col_top else ""
    parsed["asset_group"] = parsed[col_type].astype(str).str.strip() if col_type else ""
    parsed["asset_group_mid"] = parsed[col_mid].astype(str).str.strip() if col_mid else ""
    parsed["country"] = parsed[col_country].astype(str).str.strip() if col_country else ""

    parsed = parsed.dropna(subset=["asset", "shares", "avg_cost", "market_value_raw"])
    parsed = parsed[(parsed["asset"] != "") & (parsed["shares"] > 0) & (parsed["market_value_raw"] > 0)]
    parsed = parsed[~parsed["asset"].isin(["자산명", "총 투자금액", "자산투자", "현재 자산", "총 수익", "수익률"])]

    result = parsed[
        [
            "asset",
            "shares",
            "avg_cost",
            "current_price",
            "market_value_raw",
            "cost_basis_raw",
            "asset_group_top",
            "asset_group",
            "asset_group_mid",
            "country",
        ]
    ].copy()
    return result


def classify_all_weather_bucket(row: pd.Series) -> str:
    text = " ".join(
        [
            str(row.get("asset_group", "")),
            str(row.get("asset_group_mid", "")),
            str(row.get("asset", "")),
        ]
    )
    if "배당" in text:
        return "dividend"
    if "채권" in text:
        return "bond"
    if "원자재" in text or "금" in text or "은" in text or "silver" in text.lower() or "gold" in text.lower():
        return "commodity"
    if "현금" in text:
        return "cash"
    return "growth"


def build_all_weather_targets(df: pd.DataFrame) -> Dict[str, float]:
    work = df.copy()
    work["aw_bucket"] = work.apply(classify_all_weather_bucket, axis=1)
    bucket_counts = work["aw_bucket"].value_counts().to_dict()
    available_targets = {k: v for k, v in ALL_WEATHER_TARGET.items() if bucket_counts.get(k, 0) > 0}
    target_sum = sum(available_targets.values())
    if target_sum == 0:
        return {}

    normalized_bucket_targets = {k: v / target_sum for k, v in available_targets.items()}
    target_weights: Dict[str, float] = {}
    for bucket, bucket_weight in normalized_bucket_targets.items():
        members = work[work["aw_bucket"] == bucket]["asset"].tolist()
        per_asset_weight = bucket_weight / len(members)
        for asset in members:
            target_weights[asset] = per_asset_weight
    return target_weights


def build_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [clean_column_name(c) for c in cleaned.columns]
    col_tokens = [normalize_token(c) for c in cleaned.columns]
    if any("자산명" in c for c in col_tokens) and any("현재가" in c for c in col_tokens):
        return parse_korean_sheet_format(cleaned)
    return parse_standard_format(cleaned)


with st.sidebar:
    st.header("입력")
    source = st.radio(
        "데이터 소스",
        ["Google Sheets 링크", "CSV 업로드", "샘플 데이터"],
        index=0,
    )
    sheet_url = st.text_input(
        "Google Sheets URL",
        value="https://docs.google.com/spreadsheets/d/19sZTYrZbgzcuyB6gzY8hgdstcTEfE-bflivikKPR0j4/edit?usp=sharing",
        placeholder="https://docs.google.com/spreadsheets/d/.../edit?gid=0#gid=0",
    )
    uploaded = st.file_uploader("포트폴리오 CSV", type=["csv"])
    st.markdown(
        "지원 포맷:  \n"
        "1) `ticker, shares, avg_cost`  \n"
        "2) 한국어 시트(`자산명, 보유수(주/개수), 평단, 현재가` 포함)"
    )

if source == "Google Sheets 링크":
    if sheet_url.strip():
        try:
            raw_df = load_google_sheet(sheet_url)
        except Exception:
            st.error(
                "Google Sheets를 불러오지 못했습니다. "
                "시트가 '링크가 있는 모든 사용자 보기'로 공유되어 있는지 확인하세요."
            )
            st.stop()
    else:
        raw_df = pd.DataFrame(columns=STANDARD_REQUIRED_COLUMNS)
elif source == "CSV 업로드" and uploaded is not None:
    raw_df = pd.read_csv(uploaded)
elif source == "샘플 데이터":
    sample_csv = io.StringIO(
        "ticker,shares,avg_cost\nAAPL,12,165\nMSFT,8,330\nNVDA,5,800\nTSLA,4,220\n"
    )
    raw_df = pd.read_csv(sample_csv)
else:
    raw_df = pd.DataFrame(columns=STANDARD_REQUIRED_COLUMNS)

if raw_df.empty:
    st.info("사이드바에서 Google Sheets 링크를 입력하거나 CSV/샘플 데이터를 선택하세요.")
    st.stop()

try:
    portfolio = build_portfolio(raw_df)
except ValueError as e:
    st.error(str(e))
    st.stop()

if portfolio.empty:
    st.warning("유효한 보유 데이터가 없습니다. 보유수량이 0보다 큰 행이 필요합니다.")
    st.stop()

# 보증금/비증권 자산은 기본적으로 분석에서 제외
exclude_deposit = st.sidebar.checkbox("보증금(부동산) 제외", value=True)
security_only = st.sidebar.checkbox("증권만 분석", value=True)

if exclude_deposit:
    portfolio = portfolio[~portfolio["asset"].str.contains("보증금", na=False)].copy()
if security_only and "asset_group_top" in portfolio.columns:
    portfolio = portfolio[portfolio["asset_group_top"] == "증권"].copy()

if portfolio.empty:
    st.warning("필터 적용 후 분석 대상 자산이 없습니다.")
    st.stop()

if portfolio["current_price"].isna().all() and ("market_value_raw" not in portfolio.columns or portfolio["market_value_raw"].isna().all()):
    assets = tuple(sorted(portfolio["asset"].unique()))
    prices = fetch_prices(assets)
    portfolio["current_price"] = portfolio["asset"].map(prices)
    missing_price = portfolio[portfolio["current_price"].isna()]["asset"].unique().tolist()
    if missing_price:
        st.warning(
            f"현재가를 가져오지 못한 티커가 있습니다: {', '.join(missing_price)}. "
            "해당 행은 계산에서 제외됩니다."
        )

calc_df = portfolio.dropna(subset=["current_price"]).copy()
if calc_df.empty:
    st.error("가격 데이터가 없어 계산할 수 없습니다. 티커/시트 데이터를 확인하세요.")
    st.stop()

if "cost_basis_raw" in calc_df.columns:
    calc_df["cost_basis"] = calc_df["cost_basis_raw"].fillna(calc_df["shares"] * calc_df["avg_cost"])
else:
    calc_df["cost_basis"] = calc_df["shares"] * calc_df["avg_cost"]

if "market_value_raw" in calc_df.columns and not calc_df["market_value_raw"].isna().all():
    calc_df["market_value"] = calc_df["market_value_raw"]
    calc_df["current_price"] = calc_df["market_value"] / calc_df["shares"]
else:
    calc_df["market_value"] = calc_df["shares"] * calc_df["current_price"]
calc_df["pnl"] = calc_df["market_value"] - calc_df["cost_basis"]
calc_df["pnl_pct"] = (calc_df["pnl"] / calc_df["cost_basis"]) * 100
total_value = calc_df["market_value"].sum()
total_cost = calc_df["cost_basis"].sum()
total_pnl = total_value - total_cost
total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost else 0
calc_df["weight_pct"] = (calc_df["market_value"] / total_value) * 100 if total_value else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("총 평가금액", f"₩{total_value:,.0f}")
c2.metric("총 매입원가", f"₩{total_cost:,.0f}")
c3.metric("총 손익", f"₩{total_pnl:,.0f}", f"{total_pnl_pct:.2f}%")
c4.metric("보유 자산 수", f"{calc_df['asset'].nunique()}개")

st.subheader("보유 자산 상세")
display_df = calc_df[
    ["asset", "shares", "avg_cost", "current_price", "cost_basis", "market_value", "pnl", "pnl_pct", "weight_pct"]
].copy()
display_df.columns = [
    "Asset",
    "Shares",
    "Avg Cost",
    "Current Price",
    "Cost Basis",
    "Market Value",
    "PnL",
    "PnL %",
    "Weight %",
]
st.dataframe(display_df.sort_values("Market Value", ascending=False), use_container_width=True)

col_l, col_r = st.columns(2)
with col_l:
    st.subheader("자산별 평가금액")
    chart_df = calc_df.set_index("asset")[["market_value"]].rename(columns={"market_value": "Market Value"})
    st.bar_chart(chart_df)
with col_r:
    st.subheader("포트폴리오 비중(%)")
    weight_df = calc_df[["asset", "weight_pct"]].set_index("asset").rename(columns={"weight_pct": "Weight %"})
    st.dataframe(weight_df, use_container_width=True)

st.subheader("업데이트 계획(리밸런싱 제안)")
st.caption("기본값은 올웨더 + 배당주 40%입니다. 수수료와 세금은 제외됩니다.")

plan_mode = st.selectbox(
    "계획 기준",
    ["올웨더 + 배당주 40%(기본)", "동일 비중(Equal Weight)", "직접 목표 비중 입력"],
    index=0,
)
target_weights: Dict[str, float] = {}

if plan_mode == "올웨더 + 배당주 40%(기본)":
    target_weights = build_all_weather_targets(calc_df)
    if not target_weights:
        st.warning("올웨더 분류를 만들 수 없어 동일 비중으로 대체합니다.")
        equal_weight = 1 / len(calc_df)
        target_weights = {a: equal_weight for a in calc_df["asset"]}
elif plan_mode == "동일 비중(Equal Weight)":
    equal_weight = 1 / len(calc_df)
    target_weights = {a: equal_weight for a in calc_df["asset"]}
else:
    st.write("자산별 목표 비중(%)을 입력하세요. 합계 100% 권장")
    weight_sum = 0.0
    for a in calc_df["asset"]:
        current_weight = float(calc_df.loc[calc_df["asset"] == a, "weight_pct"].iloc[0])
        input_weight = st.number_input(
            f"{a} 목표 비중(%)",
            min_value=0.0,
            max_value=100.0,
            value=round(current_weight, 2),
            step=0.1,
        )
        target_weights[a] = input_weight / 100
        weight_sum += input_weight
    st.write(f"입력 합계: {weight_sum:.2f}%")

plan_df = calc_df[["asset", "shares", "current_price", "market_value", "weight_pct"]].copy()
plan_df["target_weight"] = plan_df["asset"].map(target_weights) * 100
plan_df["target_value"] = plan_df["asset"].map(target_weights) * total_value
plan_df["trade_value"] = plan_df["target_value"] - plan_df["market_value"]
plan_df["trade_shares"] = plan_df["trade_value"] / plan_df["current_price"]
plan_df["action"] = plan_df["trade_shares"].apply(
    lambda x: "BUY" if x > 0.05 else ("SELL" if x < -0.05 else "HOLD")
)
plan_df["trade_value"] = plan_df["trade_value"].round(0)
plan_df["trade_shares"] = plan_df["trade_shares"].round(2)

st.dataframe(
    plan_df[
        [
            "asset",
            "shares",
            "current_price",
            "weight_pct",
            "target_weight",
            "target_value",
            "trade_value",
            "trade_shares",
            "action",
        ]
    ].rename(
        columns={
            "asset": "Asset",
            "shares": "Current Shares",
            "current_price": "Current Price",
            "weight_pct": "Current Weight %",
            "target_weight": "Target Weight %",
            "target_value": "Target Value",
            "trade_value": "Trade Value (₩)",
            "trade_shares": "Trade Shares",
            "action": "Action",
        }
    ),
    use_container_width=True,
)
