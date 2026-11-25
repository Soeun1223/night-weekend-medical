"""밤이나 주말에 아플 때, 우리 동네 병·의원과 응급실은 인구 대비 얼마나 갖춰져 있을까?

Streamlit 대시보드. 데이터는 data/ 의 CSV만 읽는다(API 키 불필요).
  facilities.csv  국립중앙의료원 전국 병·의원 찾기 서비스 (요일별 운영 시간)
  emergency.csv   국립중앙의료원 전국 응급의료기관 정보 조회 서비스
  population.csv  KOSIS·행정안전부 주민등록인구 (시군구)
"""
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

HERE = Path(__file__).parent

st.set_page_config(page_title="밤·주말 의료 접근성", page_icon="🏥", layout="wide")

# ---------------------------------------------------------------- 상수
DAYS = ["월", "화", "수", "목", "금", "토", "일", "공휴일"]  # API 필드 dutyTime1~8 순서
DAYS_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"]
BLUE, BLUE_LIGHT = "#2a78d6", "#BCD4F3"  # 병·의원 (팔레트 1번)
ORANGE, ORANGE_LIGHT = "#eb6834", "#F8CBB8"  # 응급의료기관 (팔레트 2번)
INK, INK_SUB, GRID = "#1F2937", "#6B7280", "#E5E7EB"
FONT = "Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif"
SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "전남광주통합특별시": "전남광주",
}
DEFAULT_KINDS = ["의원", "병원", "종합병원"]


# ---------------------------------------------------------------- 데이터
@st.cache_resource(show_spinner="데이터를 불러오는 중…")
def load_data():
    pop = pd.read_csv(HERE / "data" / "population.csv", dtype={"base_month": str})
    pop["rid"] = np.arange(len(pop))
    key = pop[["sido", "sigungu", "rid"]]
    fac = pd.read_csv(HERE / "data" / "facilities.csv").merge(key, on=["sido", "sigungu"], how="left")
    emg = pd.read_csv(HERE / "data" / "emergency.csv").merge(key, on=["sido", "sigungu"], how="left")
    meta = json.loads((HERE / "data" / "meta.json").read_text(encoding="utf-8"))
    S = fac[[f"s{d}" for d in range(1, 9)]].to_numpy(dtype="float64", na_value=np.nan)
    C = fac[[f"c{d}" for d in range(1, 9)]].to_numpy(dtype="float64", na_value=np.nan)
    return {"pop": pop, "fac": fac, "emg": emg, "meta": meta, "S": S, "C": C,
            "sido": fac["sido"].to_numpy(), "sigungu": fac["sigungu"].to_numpy(),
            "rid": fac["rid"].to_numpy().astype(int), "erid": emg["rid"].to_numpy().astype(int)}


D = load_data()
POP, FAC, EMG, META = D["pop"], D["fac"], D["emg"], D["meta"]


def open_at(S, C, day, hhmm):
    """day(0=월..6=일, 7=공휴일)의 hhmm(예: 2300)에 운영 중인 행. 종료가 2400을 넘으면 다음 날 새벽까지 이어진다."""
    s, c = S[:, day], C[:, day]
    now = (s <= hhmm) & (hhmm < c)
    if day != 7:  # 전날 밤을 넘겨 새벽까지 영업하는 곳(공휴일은 전날을 알 수 없어 제외)
        pc = C[:, (day - 1) % 7]
        now = now | ((pc > 2400) & ((hhmm + 2400) < pc))
    return now


def registered(S, C, day):
    """해당 요일 운영 시간이 등록된 행(미등록 = 휴무가 아니라 '모름')."""
    return ~np.isnan(S[:, day]) & ~np.isnan(C[:, day])


def scope_mask(sido, sigungu):
    m = np.ones(len(FAC), dtype=bool)
    if sido != "전국":
        m &= D["sido"] == sido
    if sigungu != "전체":
        m &= D["sigungu"] == sigungu
    return m


@st.cache_data(show_spinner=False)
def heat_grid(sido, sigungu, kinds):
    """요일 8 x 시각 24의 '운영 중 병·의원 수'와 요일별 시간 등록 수."""
    m = scope_mask(sido, sigungu) & FAC["kind"].isin(kinds).to_numpy()
    S, C = D["S"][m], D["C"][m]
    grid = np.array([[open_at(S, C, d, h * 100).sum() for h in range(24)] for d in range(8)], dtype=float)
    reg = np.array([registered(S, C, d).sum() for d in range(8)], dtype=float)
    return grid, reg, int(m.sum())


def hhmm_text(v):
    v = int(v)
    if v == 2400:
        return "24:00"
    h, m = divmod(v, 100)
    return f"익일 {h - 24:02d}:{m:02d}" if h >= 24 else f"{h:02d}:{m:02d}"


_PLOTLY_HAS_WIDTH = "width" in inspect.signature(st.plotly_chart).parameters


def show_chart(fig):
    """Streamlit 버전에 따라 차트를 칸 너비에 맞춰 그린다."""
    if _PLOTLY_HAS_WIDTH:
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig, use_container_width=True)


def style(fig, height, title=None):
    fig.update_layout(
        height=height, margin=dict(l=8, r=16, t=28 if title else 8, b=8), title=dict(text=title) if title else dict(text=""),
        font=dict(family=FONT, size=13, color=INK), plot_bgcolor="white", paper_bgcolor="white",
        hoverlabel=dict(font_family=FONT, font_size=13), legend=dict(orientation="h", y=1.08, x=0),
    )
    return fig


# ---------------------------------------------------------------- 사이드바 (위젯)
st.sidebar.header("조건 고르기")
sido = st.sidebar.selectbox("시도", ["전국"] + sorted(POP["sido"].unique(), key=lambda s: SHORT.get(s, s)))
if sido == "전국":
    sigungu = st.sidebar.selectbox("시군구", ["전체"], disabled=True, help="시도를 고르면 시군구를 고를 수 있습니다.")
else:
    sg_options = ["전체"] + POP.loc[POP["sido"] == sido, "sigungu"].tolist()
    sigungu = st.sidebar.selectbox("시군구", sg_options, key=f"sg_{sido}")
day = DAYS_FULL.index(st.sidebar.selectbox("요일", DAYS_FULL, index=5))
hour = st.sidebar.slider("시각", 0, 23, 20, format="%d시", help="그 시각 정각에 운영 중인 병·의원을 셉니다.")
kind_options = FAC["kind"].value_counts().index.tolist()
kinds = st.sidebar.multiselect("병·의원 종류", kind_options, default=DEFAULT_KINDS,
                               help="기본값은 아플 때 가는 일반 진료기관(의원·병원·종합병원)입니다.")
ekind_options = EMG["kind"].value_counts().index.tolist()
ekinds = st.sidebar.multiselect("응급의료기관 종류", ekind_options, default=ekind_options)
order = st.sidebar.radio("막대 정렬", ["낮은 지역부터", "높은 지역부터"], horizontal=True)
st.sidebar.caption(f"기관 수 기준일 {META['collected_at']} · 인구 기준 {META['population_base_month']}")

st.title("밤이나 주말에 아플 때, 우리 동네는 얼마나 갖춰져 있을까?")
st.markdown(
    "**질문** 전국 시군구별로 **응급의료기관**과 **밤·주말에 문 연 병·의원**이 인구 대비 얼마나 다른가? "
    "왼쪽에서 지역·요일·시각·기관 종류를 바꾸면 숫자와 차트가 함께 바뀝니다."
)

if not kinds or not ekinds:
    st.warning("표시할 데이터가 없습니다. 병·의원 종류와 응급의료기관 종류를 하나 이상 선택하세요.")
    st.stop()

# ---------------------------------------------------------------- view: 선택 조건의 행만 남긴 표
day_name, hhmm = DAYS_FULL[day], hour * 100
scope = scope_mask(sido, sigungu)
kind_ok = FAC["kind"].isin(kinds).to_numpy()
open_now = open_at(D["S"], D["C"], day, hhmm)
reg_day = registered(D["S"], D["C"], day)
ekind_ok = EMG["kind"].isin(ekinds).to_numpy()

n_regions = len(POP)
reg = POP.copy()
reg["n_fac"] = np.bincount(D["rid"][kind_ok], minlength=n_regions)
reg["n_reg"] = np.bincount(D["rid"][kind_ok & reg_day], minlength=n_regions)
reg["n_open"] = np.bincount(D["rid"][kind_ok & open_now], minlength=n_regions)
reg["n_er"] = np.bincount(D["erid"][ekind_ok], minlength=n_regions)

if sido == "전국":
    level = "시도"
    g = reg.groupby("sido", as_index=False)[["population", "n_fac", "n_reg", "n_open", "n_er"]].sum()
    g["label"] = g["sido"].map(lambda s: SHORT.get(s, s))
    sel_label = None
    scope_name = "전국"
else:
    level = "시군구"
    g = reg[reg["sido"] == sido].copy()
    g["label"] = g["sigungu"]
    sel_label = None if sigungu == "전체" else sigungu
    scope_name = SHORT.get(sido, sido) if sigungu == "전체" else f"{SHORT.get(sido, sido)} {sigungu}"
g["er_rate"] = g["n_er"] / g["population"] * 1e5
g["open_rate"] = g["n_open"] / g["population"] * 1e5

if sigungu != "전체":
    sc = reg[(reg["sido"] == sido) & (reg["sigungu"] == sigungu)]
elif sido != "전국":
    sc = reg[reg["sido"] == sido]
else:
    sc = reg
s_pop, s_fac, s_reg, s_open, s_er = (int(sc[c].sum()) for c in ["population", "n_fac", "n_reg", "n_open", "n_er"])
nat_pop = int(reg["population"].sum())
nat_er_rate = reg["n_er"].sum() / nat_pop * 1e5
nat_open_rate = reg["n_open"].sum() / nat_pop * 1e5
s_er_rate = s_er / s_pop * 1e5
s_open_rate = s_open / s_pop * 1e5

# ---------------------------------------------------------------- 지표 카드
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{scope_name} 인구", f"{s_pop:,}명")
c1.caption(f"주민등록 · {META['population_base_month']}")
c2.metric("응급의료기관", f"{s_er:,}곳")
c2.caption(f"인구 10만 명당 **{s_er_rate:.2f}곳** (전국 {nat_er_rate:.2f}곳)")
c3.metric(f"{day_name} {hour}시 운영 중 병·의원", f"{s_open:,}곳")
c3.caption(f"인구 10만 명당 **{s_open_rate:.1f}곳** (전국 {nat_open_rate:.1f}곳)")
c4.metric(f"{day_name} 운영 시간 등록률", f"{s_reg / s_fac:.0%}" if s_fac else "-")
c4.caption(f"선택한 병·의원 {s_fac:,}곳 중 {s_reg:,}곳이 등록")

# ---------------------------------------------------------------- 차트 1·2: 지역별 10만 명당
ascending = order == "낮은 지역부터"


def rate_bar(col, count_col, color, color_light, base, unit):
    d = g.sort_values(col, ascending=ascending)
    colors = [color if (sel_label is None or lab == sel_label) else color_light for lab in d["label"]]
    fig = go.Figure(go.Bar(
        x=d[col], y=d["label"], orientation="h", marker_color=colors,
        text=[f"{v:.1f}" for v in d[col]] if len(d) <= 20 else None, textposition="outside", cliponaxis=False,
        customdata=np.stack([d["population"], d[count_col]], axis=-1),
        hovertemplate="<b>%{y}</b><br>10만 명당 %{x:.2f}곳<br>" + unit + " %{customdata[1]:,.0f}곳 · 인구 %{customdata[0]:,.0f}명<extra></extra>",
    ))
    fig.add_vline(x=base, line_dash="dash", line_color=INK_SUB, line_width=1,
                  annotation_text=f"전국 {base:.1f}", annotation_position="top", annotation_font_color=INK_SUB)
    fig.update_xaxes(rangemode="tozero", gridcolor=GRID, zeroline=True, zerolinecolor=INK_SUB, title="인구 10만 명당 (곳)")
    fig.update_yaxes(autorange="reversed", title=None)
    return style(fig, max(300, 26 * len(d) + 90))


left, right = st.columns(2)
with left:
    st.subheader("응급의료기관은 10만 명당 몇 곳일까")
    st.caption(f"{level}별 · 응급의료기관 지정·신고 수 ÷ 주민등록인구 · 점선 = 전국")
    show_chart(rate_bar("er_rate", "n_er", ORANGE, ORANGE_LIGHT, nat_er_rate, "응급의료기관"))
with right:
    st.subheader(f"{day_name} {hour}시에 문 연 병·의원은 10만 명당 몇 곳일까")
    st.caption(f"{level}별 · 그 시각 운영 중으로 등록된 병·의원 수 ÷ 주민등록인구 · 점선 = 전국")
    show_chart(rate_bar("open_rate", "n_open", BLUE, BLUE_LIGHT, nat_open_rate, "운영 중 병·의원"))

# ---------------------------------------------------------------- 차트 3·4: 요일·시각 히트맵 / 등록률
grid, reg_by_day, n_scope_fac = heat_grid(sido, sigungu, tuple(kinds))
heat_rate = grid / s_pop * 1e5
left, right = st.columns([3, 2])
with left:
    st.subheader(f"{scope_name}: 언제 문을 여는 곳이 많을까")
    st.caption("요일·시각별 운영 중 병·의원 수 ÷ 인구 × 10만 · 네모 테두리 = 지금 고른 요일·시각")
    fig = go.Figure(go.Heatmap(
        z=heat_rate, x=list(range(24)), y=DAYS_FULL, colorscale="Blues", xgap=2, ygap=2,
        colorbar=dict(title="10만 명당", thickness=12, len=0.9),
        customdata=grid, hovertemplate="%{y} %{x}시<br>10만 명당 %{z:.1f}곳 (%{customdata:,.0f}곳)<extra></extra>",
    ))
    fig.add_shape(type="rect", x0=hour - 0.5, x1=hour + 0.5, y0=day - 0.5, y1=day + 0.5,
                  line=dict(color=INK, width=2.5), fillcolor="rgba(0,0,0,0)")
    fig.update_xaxes(tickmode="array", tickvals=list(range(0, 24, 3)), ticktext=[f"{h}시" for h in range(0, 24, 3)], title=None)
    fig.update_yaxes(autorange="reversed", title=None)
    show_chart(style(fig, 360))
with right:
    st.subheader("요일별 운영 시간 등록률")
    st.caption("요일별로 운영 시간을 등록한 병·의원의 비율 · 미등록은 '쉰다'가 아니라 '모른다' · 낮은 요일의 수치는 실제보다 작게 집계될 수 있음")
    share = reg_by_day / n_scope_fac if n_scope_fac else reg_by_day * 0
    fig = go.Figure(go.Bar(
        x=DAYS, y=share * 100, marker_color=[BLUE if i == day else BLUE_LIGHT for i in range(8)],
        text=[f"{v * 100:.0f}%" for v in share], textposition="outside", cliponaxis=False,
        customdata=np.stack([reg_by_day, np.full(8, n_scope_fac)], axis=-1),
        hovertemplate="%{x}: %{customdata[0]:,.0f}곳 등록 / %{customdata[1]:,.0f}곳<extra></extra>",
    ))
    fig.update_yaxes(range=[0, 112], gridcolor=GRID, title=None, ticksuffix="%", tickvals=[0, 25, 50, 75, 100])
    fig.update_xaxes(title=None)
    show_chart(style(fig, 360))

# ---------------------------------------------------------------- 지도 + 목록
st.subheader(f"{scope_name}: {day_name} {hour}시에 갈 수 있는 곳")
view_mask = scope & kind_ok & open_now
view = FAC.loc[view_mask].copy()
emg_scope = EMG[(EMG["sido"] == sido) if sido != "전국" else np.ones(len(EMG), bool)]
if sigungu != "전체":
    emg_scope = emg_scope[emg_scope["sigungu"] == sigungu]
emg_scope = emg_scope[emg_scope["kind"].isin(ekinds)]

detail = sigungu != "전체"
st.caption(
    "파랑 = 그 시각 운영 중으로 등록된 병·의원, 주황 = 응급의료기관(운영 시간 정보 없음)"
    + ("" if detail else " · 시군구를 고르면 병·의원 한 곳씩 보입니다(지금은 밀도). ")
)
fig = go.Figure()
if len(view):
    if detail:
        fig.add_trace(go.Scattermap(
            lat=view["lat"], lon=view["lon"], mode="markers", name="운영 중 병·의원",
            marker=dict(size=8, color=BLUE, opacity=0.8), text=view["name"],
            customdata=np.stack([view["kind"], view["addr"]], axis=-1),
            hovertemplate="<b>%{text}</b> (%{customdata[0]})<br>%{customdata[1]}<extra></extra>"))
    else:
        fig.add_trace(go.Densitymap(
            lat=view["lat"], lon=view["lon"], radius=14, showscale=False,
            colorscale=[[0, "rgba(120,170,230,0)"], [0.25, "rgba(70,130,220,0.65)"], [1, "rgba(15,60,150,0.95)"]],
            name="운영 중 병·의원 밀도", hoverinfo="skip", showlegend=True))
if len(emg_scope):
    fig.add_trace(go.Scattermap(
        lat=emg_scope["lat"], lon=emg_scope["lon"], mode="markers", name="응급의료기관",
        marker=dict(size=13 if detail else 9, color=ORANGE, opacity=0.95), text=emg_scope["name"],
        customdata=np.stack([emg_scope["kind"], emg_scope["addr"]], axis=-1),
        hovertemplate="<b>%{text}</b> (%{customdata[0]})<br>%{customdata[1]}<extra></extra>"))
pts = pd.concat([view[["lat", "lon"]], emg_scope[["lat", "lon"]]])
if sido == "전국" or pts.empty:
    center, zoom = dict(lat=36.3, lon=127.8), 5.8
else:
    lo, hi = pts.quantile(0.02), pts.quantile(0.98)
    span = max(hi["lat"] - lo["lat"], (hi["lon"] - lo["lon"]) * 0.8, 0.02)
    center = dict(lat=float(pts["lat"].median()), lon=float(pts["lon"].median()))
    zoom = float(np.clip(8.3 - np.log2(span), 6, 13))
fig.update_layout(map=dict(style="open-street-map", center=center, zoom=zoom))
show_chart(style(fig, 520))

tab1, tab2 = st.tabs([f"운영 중 병·의원 {len(view):,}곳", f"응급의료기관 {len(emg_scope):,}곳"])
with tab1:
    if view.empty:
        st.info("이 조건에서 운영 중으로 등록된 병·의원이 없습니다. 요일·시각·종류를 바꿔 보세요.")
    else:
        sk, ck = f"s{day + 1}", f"c{day + 1}"
        table = pd.DataFrame({
            "시도": view["sido"].map(lambda s: SHORT.get(s, s)), "시군구": view["sigungu"], "이름": view["name"],
            "종류": view["kind"], f"{day_name} 운영 시간": [f"{hhmm_text(a)}–{hhmm_text(b)}" if pd.notna(a) else "전날 야간 영업 이어짐"
                                                    for a, b in zip(view[sk], view[ck])],
            "응급실 운영 표시": np.where(view["er"] == 1, "있음", ""), "주소": view["addr"],
        }).sort_values(["시도", "시군구", "이름"])
        st.dataframe(table, hide_index=True, width="stretch", height=320)
        st.download_button("현재 선택 CSV 저장", data=table.to_csv(index=False).encode("utf-8-sig"),
                           file_name="selected_facilities.csv", mime="text/csv")
with tab2:
    et = emg_scope[["sido", "sigungu", "name", "kind", "addr"]].rename(
        columns={"sido": "시도", "sigungu": "시군구", "name": "이름", "kind": "종류", "addr": "주소"})
    et["시도"] = et["시도"].map(lambda s: SHORT.get(s, s))
    st.dataframe(et.sort_values(["시도", "시군구", "이름"]), hide_index=True, width="stretch", height=320)

# ---------------------------------------------------------------- 해석 (선택에 따라 바뀌는 문장)
st.header("이 화면에서 읽을 수 있는 것")
lines = []
is_nation = sido == "전국"
if is_nation:
    lines.append(f"**전국**의 응급의료기관은 {s_er:,}곳으로 인구 10만 명당 **{s_er_rate:.2f}곳**입니다.")
    lines.append(f"{day_name} {hour}시에 운영 중으로 등록된 병·의원은 {s_open:,}곳, 10만 명당 **{s_open_rate:.1f}곳**입니다.")
else:
    ratio = (s_er_rate / nat_er_rate) if nat_er_rate else np.nan
    lines.append(f"**{scope_name}**의 응급의료기관은 {s_er:,}곳으로 인구 10만 명당 **{s_er_rate:.2f}곳**입니다. 전국({nat_er_rate:.2f}곳)의 {ratio:.0%} 수준입니다.")
    ratio2 = (s_open_rate / nat_open_rate) if nat_open_rate else np.nan
    lines.append(f"{day_name} {hour}시에 운영 중으로 등록된 병·의원은 {s_open:,}곳, 10만 명당 **{s_open_rate:.1f}곳**입니다(전국 {nat_open_rate:.1f}곳의 {ratio2:.0%}).")
noon = int(open_at(D["S"][scope & kind_ok], D["C"][scope & kind_ok], day, 1400).sum())
if noon and hour != 14:
    lines.append(f"같은 {day_name} 14시에는 {noon:,}곳이 운영 중으로 등록돼 있어, {hour}시에는 낮의 **{s_open / noon:.0%}** 수준입니다.")
if len(g) >= 3:
    lo_r, hi_r = g.loc[g["open_rate"].idxmin()], g.loc[g["open_rate"].idxmax()]
    spread = f"{hi_r['open_rate'] / lo_r['open_rate']:.1f}배" if lo_r["open_rate"] > 0 else "(가장 낮은 곳은 0곳)"
    lines.append(f"{level} {len(g)}곳을 비교하면 운영 중 병·의원은 {lo_r['label']} {lo_r['open_rate']:.1f}곳에서 {hi_r['label']} {hi_r['open_rate']:.1f}곳까지 퍼져 있습니다(격차 {spread}).")
no_er = reg[reg["n_er"] == 0]
lines.append(f"전국 시군구 {n_regions}곳 중 응급의료기관이 없는 곳은 **{len(no_er)}곳**(인구 {no_er['population'].sum() / 1e4:,.0f}만 명, 전국의 {no_er['population'].sum() / nat_pop:.1%})입니다. 선택한 응급의료기관 종류 기준입니다.")
for t in lines:
    st.markdown(f"- {t}")

st.subheader("결론과 한계")
st.markdown(
    """
**결론** 밤과 주말에는 낮보다 운영 중으로 등록된 병·의원이 크게 줄고, 지역마다 줄어드는 정도와 응급의료기관 수가 다릅니다.
위의 숫자는 *전국 평균과의 상대 비교*이며, 몇 곳이면 '충분'한지는 이 데이터만으로 정할 수 없습니다.

**한계 (숫자를 읽을 때 꼭 함께 보세요)**
- **미등록 ≠ 휴무.** 운영 시간은 기관이 등록한 값입니다. 일요일·공휴일은 등록률이 낮아(위 막대 참고) 실제로 문 연 곳이 더 있을 수 있습니다. 이 요일의 수치는 '등록된 곳만 센 값'입니다.
- **병·의원의 운영 시간은 기관이 등록한 진료 시간입니다.** 응급실의 24시간 운영과는 별개이며, 밤에 갈 수 있는 곳에는 아래 응급의료기관이 따로 들어 있습니다.
- **기관 수 ≠ 접근성.** 거리, 교통, 진료과, 병상, 대기 시간은 반영하지 않았고 의원과 대형병원을 똑같이 1곳으로 셉니다.
- **응급의료기관은 지정·신고 수입니다.** 24시간 운영 여부와 진료 가능 수준은 데이터에 없습니다.
- **행정구역 경계와 거주 인구 기준.** 사람들은 이웃 시군구의 병·의원도 쓰고, 통근·관광 인구는 분모에 없습니다.
- **인구가 적은 군 지역은 값이 크게 흔들립니다.** 기관 1곳 차이로 10만 명당 값이 크게 달라집니다(막대를 올리면 인구가 보입니다).
- **한 시점의 스냅샷입니다.** 변화나 추세가 아니라 기준일의 상태입니다.
"""
)

# ---------------------------------------------------------------- 검산
with st.expander("검산: 화면 숫자를 다른 방법으로 다시 계산"):
    S_sc, C_sc = D["S"], D["C"]
    idx = np.flatnonzero(scope & kind_ok)
    prev = (day - 1) % 7
    n_loop = 0
    for i in idx:  # 벡터 계산과 다른 방식: 행마다 '분' 단위로 계산
        s, c = S_sc[i, day], C_sc[i, day]
        t = hour * 60
        ok = (not np.isnan(s)) and (s // 100 * 60 + s % 100) <= t < (c // 100 * 60 + c % 100)
        if not ok and day != 7:
            pc = C_sc[i, prev]
            ok = (not np.isnan(pc)) and pc > 2400 and t + 1440 < (pc // 100 * 60 + pc % 100)
        n_loop += bool(ok)
    check = pd.DataFrame([
        ["선택 지역·종류의 병·의원 수", f"{s_fac:,}", f"{len(idx):,}"],
        [f"{day_name} {hour}시 운영 중 병·의원 수", f"{s_open:,}", f"{n_loop:,}"],
        ["목록 표의 행 수", f"{len(view):,}", f"{n_loop:,}"],
        ["응급의료기관 수", f"{s_er:,}", f"{len(emg_scope):,}"],
        ["막대 차트 합계 = 지표 카드(운영 중)", f"{int(g['n_open'].sum()):,}", f"{s_open:,}" if sigungu == "전체" else "시군구 선택 시 해당 없음"],
        ["전국 인구 합계 (파일 vs 수집 기록)", f"{nat_pop:,}", f"{META['population_total']:,}"],
    ], columns=["항목", "화면 값", "다시 계산한 값"])
    check["일치"] = np.where(check["화면 값"] == check["다시 계산한 값"], "✅", np.where(check["다시 계산한 값"].str.contains("해당"), "-", "❌"))
    st.dataframe(check, hide_index=True, width="stretch")
    st.caption("행마다 시작·종료 시각을 분으로 바꿔 직접 비교한 값과 화면의 벡터 계산 값이 같은지 확인합니다.")

# ---------------------------------------------------------------- 데이터와 집계 기준
st.header("데이터와 집계 기준")
st.markdown(
    f"""
| 데이터 | 출처 | 기준 |
|---|---|---|
| 병·의원 {META['facilities']:,}곳 | 국립중앙의료원 전국 병·의원 찾기 서비스 (공공데이터포털) | {META['collected_at']} 수집 · 요일별(월~일·공휴일) 운영 시작·종료 시각 |
| 응급의료기관 {META['emergency']:,}곳 | 국립중앙의료원 전국 응급의료기관 정보 조회 서비스 (공공데이터포털) | {META['collected_at']} 수집 · 권역·지역센터, 지역기관, 응급실운영신고기관 |
| 주민등록인구 | 행정안전부 「주민등록인구현황」 (KOSIS) | {META['population_base_month']} 말일 · 시군구 {n_regions}곳 · 외국인 제외 |

**집계 기준**
- 지역은 기관 주소의 시도·시군구입니다. 일반구가 있는 시(수원·청주 등)는 시 단위로 합쳤고 세종은 한 지역입니다.
- *운영 중* = 선택 요일의 시작 ≤ 선택 시각 < 종료. 종료가 24시를 넘으면 다음 날 새벽까지 이어진 것으로 보고, 전날 밤 영업이 이어지는 경우도 셉니다(공휴일은 제외).
- *10만 명당* = 기관 수 ÷ 시군구 인구 합 × 100,000. 시도 값은 시군구를 합산해 다시 나눈 값입니다(시군구 값의 평균이 아님).
- 제외: 약국·구급차 등 의료기관이 아닌 분류, 주소의 시군구가 인구 표와 맞지 않는 병·의원 {META['hospitals_unmatched_region']}곳, 종료 시각이 시작보다 빠르거나 같은 {META['invalid_time_cells']}개 요일 칸(미등록으로 처리).
"""
)
