# -*- coding: utf-8 -*-
"""
market_layer.py  —  実勢価格レイヤー（app.py / app.mobile.py 共通）
================================================================
国土交通省の「不動産取引価格情報」と「地価公示」を読み込み、
・検索中心まわりの取引事例の坪単価統計
・最寄りの地価公示ポイントの公示坪単価
・売地一覧の坪単価が周辺相場に対して割高/割安かの乖離率
を提供する。データCSVが無い場合も例外を出さず、機能を無効化するだけ。

生成元: market/build_market_data.py
"""
from __future__ import annotations

from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
import streamlit as st
import folium

APP_DIR = Path(__file__).resolve().parent
TORIHIKI_CSV = APP_DIR / "market_torihiki.csv"
KOUJI_CSV = APP_DIR / "market_kouji.csv"


# ──────────────────────────────────────────────────────────────
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


@st.cache_data(show_spinner=False)
def load_market() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(取引事例, 地価公示) を返す。無ければ空DataFrame。"""
    def _read(p: Path) -> pd.DataFrame:
        if not p.exists():
            return pd.DataFrame()
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                return pd.read_csv(p, encoding=enc)
            except UnicodeDecodeError:
                continue
        return pd.DataFrame()

    tori = _read(TORIHIKI_CSV)
    kouji = _read(KOUJI_CSV)
    for df in (tori, kouji):
        if not df.empty:
            for c in ("lat", "lon", "坪単価万円"):
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
    return tori, kouji


def market_available() -> bool:
    return TORIHIKI_CSV.exists() or KOUJI_CSV.exists()


# ──────────────────────────────────────────────────────────────
def nearby_torihiki(
    tori: pd.DataFrame,
    clat: float,
    clon: float,
    radius_km: float,
    land_only: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """検索中心から radius_km 以内の取引事例と統計を返す。"""
    if tori.empty:
        return tori, {}
    df = tori.copy()
    if land_only and "種類" in df.columns:
        df = df[df["種類"] == "宅地(土地)"]
    df = df[df["lat"].notna() & df["lon"].notna()]
    df["距離km"] = df.apply(lambda r: haversine(clat, clon, r["lat"], r["lon"]), axis=1)
    df = df[df["距離km"] <= radius_km].copy()
    s = df["坪単価万円"].dropna()
    stats = {}
    if len(s):
        stats = {
            "n": int(len(s)),
            "median": round(float(s.median()), 1),
            "mean": round(float(s.mean()), 1),
            "min": round(float(s.min()), 1),
            "max": round(float(s.max()), 1),
            "p25": round(float(s.quantile(0.25)), 1),
            "p75": round(float(s.quantile(0.75)), 1),
        }
    return df.sort_values("距離km"), stats


def nearest_kouji(kouji: pd.DataFrame, clat: float, clon: float) -> dict | None:
    if kouji.empty:
        return None
    df = kouji[kouji["lat"].notna() & kouji["lon"].notna()].copy()
    if df.empty:
        return None
    df["距離km"] = df.apply(lambda r: haversine(clat, clon, r["lat"], r["lon"]), axis=1)
    r = df.sort_values("距離km").iloc[0]
    return r.to_dict()


def kouji_within(kouji: pd.DataFrame, clat: float, clon: float, radius_km: float) -> pd.DataFrame:
    if kouji.empty:
        return kouji
    df = kouji[kouji["lat"].notna() & kouji["lon"].notna()].copy()
    df["距離km"] = df.apply(lambda r: haversine(clat, clon, r["lat"], r["lon"]), axis=1)
    return df[df["距離km"] <= radius_km].sort_values("距離km")


def deviation_pct(price_tsubo: float, benchmark: float) -> float | None:
    """price_tsubo が benchmark に対して何%高い/安いか。"""
    try:
        if not benchmark or pd.isna(price_tsubo) or price_tsubo <= 0:
            return None
        return round((float(price_tsubo) / float(benchmark) - 1.0) * 100.0, 0)
    except (TypeError, ValueError):
        return None


def deviation_label(pct: float | None) -> str:
    if pct is None:
        return "-"
    if pct >= 0:
        return f"▲ +{pct:.0f}%（割高）"
    return f"▼ {pct:.0f}%（割安）"


# ──────────────────────────────────────────────────────────────
# 地図マーカー
# ──────────────────────────────────────────────────────────────
def _num(v):
    try:
        f = float(v)
        return f if pd.notna(f) else None
    except (TypeError, ValueError):
        return None


def add_market_markers(
    fmap: folium.Map,
    tori_near: pd.DataFrame,
    kouji_near: pd.DataFrame,
    max_points: int = 60,
) -> None:
    if tori_near is not None and not tori_near.empty:
        fg = folium.FeatureGroup(name="取引事例（実勢）", show=True)
        for _, r in tori_near.head(max_points).iterrows():
            t = _num(r.get("坪単価万円"))
            rows = [f"<b>取引事例</b>", f"{r.get('市区町村','')}{r.get('地区名','')}",
                    f"時期：{r.get('取引時期','-')}"]
            if t is not None:
                rows.append(f"坪単価：<b>{t:.1f} 万円/坪</b>")
            rows += [f"面積：{r.get('面積m2','-')} ㎡",
                     f"用途地域：{r.get('用途地域','-')}",
                     f"前面道路：{r.get('前面道路幅員m','-')} m",
                     "<span style='color:#888'>※ 地区名の代表座標（点は目安）</span>"]
            folium.CircleMarker(
                [r["lat"], r["lon"]],
                radius=6, color="#7b2ff7", fill=True, fill_color="#7b2ff7", fill_opacity=0.7,
                popup=folium.Popup("<br>".join(rows), max_width=260),
                tooltip=(f"取引 {t:.1f}万/坪" if t is not None else "取引事例"),
            ).add_to(fg)
        fg.add_to(fmap)

    if kouji_near is not None and not kouji_near.empty:
        fg = folium.FeatureGroup(name="地価公示", show=True)
        for _, r in kouji_near.iterrows():
            t = _num(r.get("坪単価万円"))
            m2 = _num(r.get("公示m2単価円"))
            rows = [f"<b>地価公示 標準地</b>", f"{r.get('住所','')}"]
            if t is not None:
                rows.append(f"公示坪単価：<b>{t:.1f} 万円/坪</b>")
            if m2 is not None:
                rows.append(f"公示㎡単価：{m2:,.0f} 円/㎡")
            rows += [f"用途地域：{r.get('用途地域','-')}",
                     f"建蔽/容積：{r.get('建蔽率','-')} / {r.get('容積率','-')} %",
                     f"相続税路線価：{r.get('相続税路線価','-')}"]
            folium.Marker(
                [r["lat"], r["lon"]],
                icon=folium.Icon(color="orange", icon="usd", prefix="fa"),
                popup=folium.Popup("<br>".join(rows), max_width=260),
                tooltip=(f"公示 {t:.1f}万/坪" if t is not None else "地価公示"),
            ).add_to(fg)
        fg.add_to(fmap)

    try:
        folium.LayerControl(collapsed=True).add_to(fmap)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# 相場パネル（Streamlit UI）
# ──────────────────────────────────────────────────────────────
def render_market_panel(
    clat: float,
    clon: float,
    radius_km: float,
    *,
    compact: bool = False,
) -> dict:
    """
    相場サマリを描画し、一覧の乖離率計算に使うベンチマークを返す。
    戻り値: {"benchmark": float|None, "stats": dict, "tori_near": df, "kouji_near": df, "nearest_kouji": dict|None}
    """
    tori, kouji = load_market()
    if tori.empty and kouji.empty:
        st.info("実勢価格データ（market_torihiki.csv / market_kouji.csv）が未生成です。`python market/build_market_data.py` を実行してください。")
        return {"benchmark": None, "stats": {}, "tori_near": pd.DataFrame(),
                "kouji_near": pd.DataFrame(), "nearest_kouji": None}

    tori_near, stats = nearby_torihiki(tori, clat, clon, radius_km, land_only=True)
    nk = nearest_kouji(kouji, clat, clon)
    kouji_near = kouji_within(kouji, clat, clon, max(radius_km, 3.0))

    benchmark = stats.get("median") or (nk.get("坪単価万円") if nk else None)

    st.markdown("### 💰 周辺の実勢相場")
    if stats:
        cols = st.columns(2 if compact else 4)
        cols[0].metric("取引事例（宅地・土地）", f"{stats['n']} 件", help=f"半径{radius_km:.1f}km・直近1年")
        cols[1].metric("坪単価 中央値", f"{stats['median']:.1f} 万円")
        if not compact:
            cols[2].metric("坪単価 レンジ(25–75%)", f"{stats['p25']:.0f}–{stats['p75']:.0f}")
            cols[3].metric("最小 / 最大", f"{stats['min']:.0f} / {stats['max']:.0f}")
    else:
        st.caption(f"半径{radius_km:.1f}km以内に土地の取引事例が見つかりませんでした（半径を広げてください）。")

    if nk is not None:
        d = nk.get("距離km", 0.0)
        tsubo = nk.get("坪単価万円")
        line = f"🏛️ **最寄りの地価公示**（{d:.1f}km） {nk.get('住所','')}"
        if pd.notna(tsubo):
            line += f" ／ 公示坪単価 **{tsubo:.1f} 万円**"
        yoto = nk.get("用途地域")
        if isinstance(yoto, str) and yoto:
            line += f" ／ {yoto}"
        st.markdown(line)

    if benchmark:
        st.caption(f"▶ 一覧の「周辺相場比」は基準 **{benchmark:.1f} 万円/坪** に対する乖離です（＋＝割高 / −＝割安）。")

    return {
        "benchmark": benchmark,
        "stats": stats,
        "tori_near": tori_near,
        "kouji_near": kouji_near,
        "nearest_kouji": nk,
    }
