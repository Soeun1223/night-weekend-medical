"""평일 밤이나 토요일에 아플 때, 우리 동네는 인구 대비 얼마나 갖춰져 있을까?

데이터는 data/ 의 CSV만 읽는다(API 키 불필요).
  facilities.csv  국립중앙의료원 전국 병·의원 찾기 서비스 (요일별 운영 시간)
  emergency.csv   국립중앙의료원 전국 응급의료기관 정보 조회 서비스
  population.csv  행정안전부 주민등록인구 (시군구)
"""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

HERE = Path(__file__).parent
st.set_page_config(page_title="평일 밤·토요일 의료 접근성", layout="wide")

DAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]  # 분석에 쓰는 요일 (dutyTime1~6)
ALL_DAYS = DAYS + ["일요일", "공휴일"]  # dutyTime1~8
BLUE, BLUE_LIGHT, ORANGE, ORANGE_LIGHT, GRAY = "#2a78d6", "#BCD4F3", "#eb6834", "#F8CBB8", "#BDBDBD"
SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "대전광역시": "대전",
         "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북",
         "충청남도": "충남", "전북특별자치도": "전북", "경상북도": "경북", "경상남도": "경남",
         "제주특별자치도": "제주", "전남광주통합특별시": "전남광주"}


# ---------------------------------------------------------------- 데이터
@st.cache_data
def load_data():
    pop = pd.read_csv(HERE / "data" / "population.csv", dtype={"base_month": str})
    fac = pd.read_csv(HERE / "data" / "facilities.csv")
    emg = pd.read_csv(HERE / "data" / "emergency.csv")
    meta = json.loads((HERE / "data" / "meta.json").read_text(encoding="utf-8"))
    return pop, fac, emg, meta


pop, fac_all, emg_all, meta = load_data()


def is_open(df, day, hour):
    """day(1=월 ... 6=토)의 hour시 정각에 운영 중이면 True.
    시작 <= 시각 < 종료. 시간이 비어 있으면(미등록) 비교가 False가 되어 '운영 중'에 세지 않는다."""
    t = hour * 100
    now = (df[f"s{day}"] <= t) & (t < df[f"c{day}"])
    if day > 1:  # 전날 종료 시각이 2400을 넘으면(예: 2600) 다음 날 새벽까지 영업하는 곳
        prev = df[f"c{day - 1}"]
        now = now | ((prev > 2400) & (t + 2400 < prev))
    return now


def short(name):
    return SHORT.get(name, name)


def tidy(fig, height):
    fig.update_layout(height=height, margin=dict(l=8, r=16, t=16, b=8), template="plotly_white")
    return fig


# ---------------------------------------------------------------- 사이드바 (위젯)
st.sidebar.header("조건 고르기")
sido = st.sidebar.selectbox("시도", ["전국"] + sorted(pop["sido"].unique(), key=short))
if sido == "전국":
    sigungu = st.sidebar.selectbox("시군구", ["전체"], disabled=True)
else:
    sigungu = st.sidebar.selectbox("시군구", ["전체"] + pop.loc[pop["sido"] == sido, "sigungu"].tolist(), key=f"sg_{sido}")
day_name = st.sidebar.selectbox("요일", DAYS, index=5)
day = DAYS.index(day_name) + 1
hour = st.sidebar.slider("시각", 0, 23, 20, format="%d시")
kind_options = fac_all["kind"].value_counts().index.tolist()
kinds = st.sidebar.multiselect("병·의원 종류", kind_options, default=["의원", "병원", "종합병원"])
ekind_options = emg_all["kind"].value_counts().index.tolist()
ekinds = st.sidebar.multiselect("응급의료기관 종류", ekind_options, default=ekind_options)
order = st.sidebar.radio("막대 정렬", ["낮은 지역부터", "높은 지역부터"], horizontal=True)
st.sidebar.caption(f"기관 수 기준일 {meta['collected_at']} · 인구 기준 {meta['population_base_month']}")

st.title("평일 밤이나 토요일에 아플 때, 우리 동네는 얼마나 갖춰져 있을까?")
st.markdown(
    "**질문** 시군구별로 **응급의료기관**과 **평일 밤·토요일에 문 연 병·의원**이 인구 대비 얼마나 다른가? "
    "왼쪽에서 조건을 바꾸면 숫자와 차트가 함께 바뀝니다. "
    "(일요일·공휴일은 운영 시간을 등록한 곳이 너무 적어 분석에서 뺐습니다. 아래 막대 참고)"
)

if not kinds or not ekinds:
    st.warning("표시할 데이터가 없습니다. 병·의원 종류와 응급의료기관 종류를 하나 이상 선택하세요.")
    st.stop()

# ---------------------------------------------------------------- view: 고른 조건의 행만 남긴 표
fac = fac_all[fac_all["kind"].isin(kinds)].copy()
fac["open"] = is_open(fac, day, hour)
fac["registered"] = fac[f"s{day}"].notna()
emg = emg_all[emg_all["kind"].isin(ekinds)]

by_region = fac.groupby(["sido", "sigungu"]).agg(
    n_fac=("hpid", "size"), n_reg=("registered", "sum"), n_open=("open", "sum")).reset_index()
er_region = emg.groupby(["sido", "sigungu"]).size().reset_index(name="n_er")
reg = pop.merge(by_region, how="left").merge(er_region, how="left").fillna(0)  # 시군구 230행

if sido == "전국":
    level = "시도"
    g = reg.groupby("sido", as_index=False)[["population", "n_fac", "n_reg", "n_open", "n_er"]].sum()
    g["label"] = g["sido"].map(short)
    sc = reg
    scope_name = "전국"
    scope_fac, scope_emg = fac, emg
else:
    level = "시군구"
    g = reg[reg["sido"] == sido].copy()
    g["label"] = g["sigungu"]
    sc = reg[reg["sido"] == sido]
    scope_name = short(sido)
    scope_fac, scope_emg = fac[fac["sido"] == sido], emg[emg["sido"] == sido]
    if sigungu != "전체":
        sc = sc[sc["sigungu"] == sigungu]
        scope_name += f" {sigungu}"
        scope_fac, scope_emg = scope_fac[scope_fac["sigungu"] == sigungu], scope_emg[scope_emg["sigungu"] == sigungu]
g["er_rate"] = g["n_er"] / g["population"] * 100000
g["open_rate"] = g["n_open"] / g["population"] * 100000

s_pop, s_fac, s_reg, s_open, s_er = (int(sc[c].sum()) for c in ["population", "n_fac", "n_reg", "n_open", "n_er"])
nat_pop = reg["population"].sum()
nat_er_rate = reg["n_er"].sum() / nat_pop * 100000
nat_open_rate = reg["n_open"].sum() / nat_pop * 100000

# ---------------------------------------------------------------- 지표 카드
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{scope_name} 인구", f"{s_pop:,}명")
c1.caption(f"주민등록 · {meta['population_base_month']}")
c2.metric("응급의료기관", f"{s_er:,}곳")
c2.caption(f"인구 10만 명당 **{s_er / s_pop * 100000:.2f}곳** (전국 {nat_er_rate:.2f}곳)")
c3.metric(f"{day_name} {hour}시 운영 중 병·의원", f"{s_open:,}곳")
c3.caption(f"인구 10만 명당 **{s_open / s_pop * 100000:.1f}곳** (전국 {nat_open_rate:.1f}곳)")
c4.metric(f"{day_name} 운영 시간 등록률", f"{s_reg / s_fac:.0%}" if s_fac else "-")
c4.caption(f"선택한 병·의원 {s_fac:,}곳 중 {s_reg:,}곳이 등록")


# ---------------------------------------------------------------- 차트 1·2: 지역별 10만 명당 막대
def rate_bar(col, count_col, color, color_light, base):
    d = g.sort_values(col, ascending=(order == "낮은 지역부터")).copy()
    sel = None if sigungu == "전체" else sigungu
    d["구분"] = ["선택" if sel is None or lab == sel else "그 밖" for lab in d["label"]]
    fig = px.bar(d, x=col, y="label", orientation="h", color="구분",
                 color_discrete_map={"선택": color, "그 밖": color_light},
                 text_auto=".1f" if len(d) <= 20 else False,
                 labels={col: "인구 10만 명당 (곳)", "label": "", "population": "인구", count_col: "기관 수"},
                 hover_data={"population": ":,", count_col: ":,", col: ":.2f", "구분": False})
    fig.add_vline(x=base, line_dash="dash", line_color="gray",
                  annotation_text=f"전국 {base:.1f}", annotation_position="top")
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(showlegend=False)
    return tidy(fig, max(300, 26 * len(d) + 90))


left, right = st.columns(2)
with left:
    st.subheader("응급의료기관은 10만 명당 몇 곳일까")
    st.caption(f"{level}별 · 응급의료기관 수 ÷ 주민등록인구 · 점선 = 전국")
    st.plotly_chart(rate_bar("er_rate", "n_er", ORANGE, ORANGE_LIGHT, nat_er_rate), use_container_width=True)
with right:
    st.subheader(f"{day_name} {hour}시에 문 연 병·의원은 10만 명당 몇 곳일까")
    st.caption(f"{level}별 · 그 시각 운영 중으로 등록된 병·의원 수 ÷ 주민등록인구 · 점선 = 전국")
    st.plotly_chart(rate_bar("open_rate", "n_open", BLUE, BLUE_LIGHT, nat_open_rate), use_container_width=True)

# ---------------------------------------------------------------- 차트 3: 요일·시각 히트맵 / 차트 4: 등록률
left, right = st.columns([3, 2])
with left:
    st.subheader(f"{scope_name}: 언제 문을 여는 곳이 많을까")
    st.caption("시각별로 운영 중인 병·의원 수 ÷ 인구 × 10만 · 평일은 월~금 5일의 평균")
    rows = []
    for h in range(24):
        counts = [is_open(scope_fac, d, h).sum() for d in range(1, 7)]  # 월~토 운영 중 병·의원 수
        rows.append({"시각": h, "구분": "평일(월~금 평균)", "10만 명당": sum(counts[:5]) / 5 / s_pop * 100000})
        rows.append({"시각": h, "구분": "토요일", "10만 명당": counts[5] / s_pop * 100000})
    fig = px.line(pd.DataFrame(rows), x="시각", y="10만 명당", color="구분", markers=True,
                  color_discrete_map={"평일(월~금 평균)": BLUE, "토요일": ORANGE})
    fig.update_xaxes(dtick=3, ticksuffix="시", title="")
    fig.update_yaxes(rangemode="tozero", title="인구 10만 명당 (곳)")
    fig.update_layout(legend=dict(title=None, orientation="h", y=1.1))
    st.plotly_chart(tidy(fig, 330), use_container_width=True)
with right:
    st.subheader("요일별 운영 시간 등록률")
    st.caption("운영 시간을 등록한 병·의원의 비율 · 미등록은 '쉰다'가 아니라 '모른다'")
    rate = pd.DataFrame({"요일": ALL_DAYS, "등록률": [scope_fac[f"s{d}"].notna().mean() * 100 for d in range(1, 9)]})
    rate["구분"] = ["분석에 사용"] * 6 + ["등록률이 낮아 제외"] * 2
    fig = px.bar(rate.fillna(0), x="요일", y="등록률", color="구분", text_auto=".0f",
                 color_discrete_map={"분석에 사용": BLUE, "등록률이 낮아 제외": GRAY}, labels={"등록률": "등록률(%)", "요일": ""})
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_yaxes(range=[0, 115])
    fig.update_layout(legend=dict(orientation="h", y=1.12, title=None))
    st.plotly_chart(tidy(fig, 330), use_container_width=True)
    st.info(f"일요일 {rate.loc[6, '등록률']:.0f}%, 공휴일 {rate.loc[7, '등록률']:.0f}%만 시간을 등록해서, "
            "이 요일의 '문 연 곳 수'는 판단할 수 없어 분석에서 뺐습니다.")

# ---------------------------------------------------------------- 차트 5: 지도 + 목록
st.subheader(f"{scope_name}: {day_name} {hour}시에 갈 수 있는 곳")
open_df = scope_fac[scope_fac["open"]]
shown = open_df.sample(2000, random_state=0) if len(open_df) > 2000 else open_df  # 점이 너무 많으면 일부만
pts = pd.concat([
    shown.assign(구분="운영 중 병·의원", 크기=7),
    scope_emg.assign(구분="응급의료기관", 크기=12),
])
st.caption("파랑 = 그 시각 운영 중으로 등록된 병·의원, 주황 = 응급의료기관(운영 시간 정보 없음)"
           + (f" · 병·의원이 {len(open_df):,}곳이라 2,000곳만 표시했습니다." if len(open_df) > 2000 else ""))
if pts.empty:
    st.info("이 조건에서 지도에 표시할 곳이 없습니다.")
else:
    zoom = 5.8 if sido == "전국" else (8.5 if sigungu == "전체" else 11.5)
    center = dict(lat=36.3, lon=127.8) if sido == "전국" else dict(lat=pts["lat"].median(), lon=pts["lon"].median())
    fig = px.scatter_map(pts, lat="lat", lon="lon", color="구분", size="크기", size_max=12, hover_name="name",
                         color_discrete_map={"운영 중 병·의원": BLUE, "응급의료기관": ORANGE},
                         hover_data={"kind": True, "addr": True, "lat": False, "lon": False, "크기": False, "구분": False},
                         center=center, zoom=zoom, map_style="open-street-map")
    st.plotly_chart(tidy(fig, 520), use_container_width=True)


def hhmm(v):
    h, m = divmod(int(v), 100)
    return f"익일 {h - 24:02d}:{m:02d}" if h >= 24 and v != 2400 else f"{h:02d}:{m:02d}"


st.subheader(f"운영 중 병·의원 {len(open_df):,}곳")
if open_df.empty:
    st.info("이 조건에서 운영 중으로 등록된 병·의원이 없습니다. 요일·시각·종류를 바꿔 보세요.")
else:
    table = pd.DataFrame({
        "시도": open_df["sido"].map(short), "시군구": open_df["sigungu"], "이름": open_df["name"], "종류": open_df["kind"],
        f"{day_name} 운영 시간": [f"{hhmm(a)}–{hhmm(b)}" if pd.notna(a) else "-" for a, b in zip(open_df[f"s{day}"], open_df[f"c{day}"])],
        "응급실 운영 표시": open_df["er"].map({1: "있음", 0: ""}), "주소": open_df["addr"],
    }).sort_values(["시도", "시군구", "이름"])
    st.dataframe(table, hide_index=True, width="stretch", height=300)
    st.download_button("현재 선택 CSV 저장", data=table.to_csv(index=False).encode("utf-8-sig"),
                       file_name="selected_facilities.csv", mime="text/csv")
st.subheader(f"응급의료기관 {len(scope_emg):,}곳")
st.dataframe(scope_emg[["sido", "sigungu", "name", "kind", "addr"]].rename(
    columns={"sido": "시도", "sigungu": "시군구", "name": "이름", "kind": "종류", "addr": "주소"}),
    hide_index=True, width="stretch", height=240)

# ---------------------------------------------------------------- 해석 (선택에 따라 바뀌는 문장)
st.header("이 화면에서 읽을 수 있는 것")
er_rate, open_rate = s_er / s_pop * 100000, s_open / s_pop * 100000
lines = [f"**{scope_name}**의 응급의료기관은 {s_er:,}곳, 인구 10만 명당 **{er_rate:.2f}곳**입니다."
         + ("" if sido == "전국" else f" 전국({nat_er_rate:.2f}곳)의 {er_rate / nat_er_rate:.0%} 수준입니다."),
         f"{day_name} {hour}시에 운영 중으로 등록된 병·의원은 {s_open:,}곳, 10만 명당 **{open_rate:.1f}곳**입니다."
         + ("" if sido == "전국" else f" 전국({nat_open_rate:.1f}곳)의 {open_rate / nat_open_rate:.0%} 수준입니다.")]
noon = int(is_open(scope_fac, day, 14).sum())
if noon and hour != 14:
    lines.append(f"같은 {day_name} 14시에는 {noon:,}곳이 운영 중이라, {hour}시에는 낮의 **{s_open / noon:.0%}** 수준입니다.")
if len(g) >= 3:
    lo, hi = g.loc[g["open_rate"].idxmin()], g.loc[g["open_rate"].idxmax()]
    lines.append(f"{level} {len(g)}곳 가운데 운영 중 병·의원은 {lo['label']} {lo['open_rate']:.1f}곳에서 {hi['label']} {hi['open_rate']:.1f}곳까지 차이가 납니다.")
no_er = reg[reg["n_er"] == 0]
lines.append(f"전국 시군구 {len(reg)}곳 중 응급의료기관이 없는 곳은 **{len(no_er)}곳**(인구 {no_er['population'].sum() / 10000:,.0f}만 명, 전국의 {no_er['population'].sum() / nat_pop:.1%})입니다.")
for t in lines:
    st.markdown(f"- {t}")

st.subheader("결론과 한계")
st.markdown("""
**결론** 평일 낮에 비해 밤과 토요일에는 운영 중으로 등록된 병·의원이 크게 줄고, 지역마다 응급의료기관 수와 줄어드는 정도가 다릅니다.
위 숫자는 *전국 평균과의 상대 비교*이며, 몇 곳이면 '충분'한지는 이 데이터만으로 정할 수 없습니다.

**한계 (숫자를 읽을 때 꼭 함께 보세요)**
- **일요일·공휴일은 분석하지 못했습니다.** 운영 시간을 등록한 병·의원이 일요일 7%, 공휴일 11%뿐이라 '문 연 곳 수'가 의미가 없습니다. 이 질문의 '주말'은 토요일까지만 답합니다.
- **미등록 ≠ 휴무.** 운영 시간은 기관이 등록한 진료 시간입니다. 토요일도 등록하지 않은 곳이 있어 실제보다 적게 집계될 수 있고, 응급실의 24시간 운영과는 별개입니다.
- **기관 수 ≠ 접근성.** 거리, 교통, 진료과, 병상, 대기 시간은 반영하지 않았고 의원과 대형병원을 똑같이 1곳으로 셉니다.
- **응급의료기관은 지정·신고 수입니다.** 24시간 운영 여부와 진료 가능 수준은 데이터에 없습니다.
- **행정구역 경계와 거주 인구 기준.** 이웃 시군구의 병·의원도 이용하고, 통근·관광 인구는 분모에 없습니다.
- **인구가 적은 군 지역은 값이 크게 흔들립니다.** 기관 1곳 차이로 10만 명당 값이 크게 달라집니다.
- **한 시점의 스냅샷입니다.** 변화나 추세가 아니라 기준일의 상태입니다.
""")

# ---------------------------------------------------------------- 데이터와 집계 기준
st.header("데이터와 집계 기준")
st.markdown(f"""
| 데이터 | 출처 | 기준 |
|---|---|---|
| 병·의원 {meta['facilities']:,}곳 | 국립중앙의료원 전국 병·의원 찾기 서비스 (공공데이터포털) | {meta['collected_at']} 수집 · 요일별 운영 시작·종료 시각 |
| 응급의료기관 {meta['emergency']:,}곳 | 국립중앙의료원 전국 응급의료기관 정보 조회 서비스 (공공데이터포털) | {meta['collected_at']} 수집 |
| 주민등록인구 | 행정안전부 「주민등록인구현황」 | {meta['population_base_month']} 말일 · 시군구 {len(pop)}곳 · 외국인 제외 |

**집계 기준**
- 요일 열은 공공데이터포털 명세(`dutyTime1~7` = 월~일, `8` = 공휴일)를 따릅니다.
- 지역은 기관 주소의 시도·시군구입니다. 일반구가 있는 시(수원·청주 등)는 시 단위로 합쳤고 세종은 한 지역입니다.
- *운영 중* = 선택 요일의 시작 ≤ 선택 시각 < 종료. 종료가 24시를 넘으면 다음 날 새벽까지 이어진 것으로 보고, 전날 밤 영업이 이어지는 경우도 셉니다(월요일 0~2시는 일요일 자료가 없어 제외).
- *10만 명당* = 기관 수 ÷ 시군구 인구 합 × 100,000. 시도 값은 시군구를 합산해 다시 나눈 값입니다.
- 제외: 약국·구급차 등 의료기관이 아닌 분류, 주소의 시군구가 인구 표와 맞지 않는 병·의원 {meta['hospitals_unmatched_region']}곳, 종료가 시작보다 빠르거나 같은 {meta['invalid_time_cells']}개 요일 칸(미등록 처리).
""")
