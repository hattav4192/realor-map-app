#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""app_mobile.py – Streamlit 売土地検索ツール（モバイル版）
2025-07-14 rev2

- スマホ画面での連続操作を想定し、すべての検索スライダーを常時表示
- 面積スライダーの上限値を固定 500 坪とし、「500=500坪以上」として扱う
- ポップアップに 登録会員 / TEL を追加
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2

import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# ────────────────────────────────────────────────
# 🔑 Google Maps API Key
# ------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
CSV_PATH = Path("住所付き_緯度経度付きデータ_1.csv")  # データファイル名

# ────────────────────────────────────────────────
# ユーティリティ
# ------------------------------------------------
@st.cache_data(show_spinner=False)
def geocode_address(addr: str):
    """住所 → (lat, lon)。API キーが無い場合は (None, None)"""
    if not GOOGLE_API_KEY:
        return None, None
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(
        {"address": addr, "key": GOOGLE_API_KEY, "language": "ja"}, safe=":"
    )
    try:
        data = requests.get(url, timeout=5).json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception:
        pass
    return None, None


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2 点間距離 (km)"""
    R = 6371.0
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    """UTF-8 / UTF-8-BOM / Shift-JIS の順に試す → 坪 / 坪単価 列追加"""
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        st.error("CSV 読み込みに失敗しました。文字コードをご確認ください。")
        st.stop()

    df.columns = df.columns.str.strip()
    df = df.rename(columns={"lat": "latitude", "lng": "longitude"})

    if not {"latitude", "longitude"}.issubset(df.columns):
        st.error("CSV に latitude / longitude 列が見当たりません。")
        st.stop()

    # 土地面積(坪)
    if "土地面積（坪）" not in df.columns:
        if "土地面積（㎡）" in df.columns:
            df["土地面積（坪）"] = (df["土地面積（㎡）"] / 3.305785).round(2)
        else:
            st.error("CSV に土地面積列が見当たりません。")
            st.stop()

    df["土地面積（坪）"] = pd.to_numeric(
        df["土地面積（坪）"].astype(str).str.replace(",", ""), errors="coerce"
    )

    price_col = "登録価格（万円）" if "登録価格（万円）" in df.columns else "価格(万円)"
    df["坪単価（万円/坪）"] = (df[price_col] / df["土地面積（坪）"]).round(1)
    return df

# ────────────────────────────────────────────────
# ページ設定
# ------------------------------------------------
st.set_page_config(page_title="売土地検索 (モバイル)", page_icon="🏠", layout="centered")
st.title("🏠 売土地検索（モバイル版）")

_df = load_data(CSV_PATH)

# ────────────────────────────────────────────────
# 住所入力
# ------------------------------------------------
st.subheader("① 検索中心の住所を入力")
address = st.text_input("例：浜松市中区高林1丁目")
if not address:
    st.stop()

center_lat, center_lon = geocode_address(address.strip())
if center_lat is None:
    st.warning("住所が見つかりませんでした。再入力してください。")
    st.stop()

# ────────────────────────────────────────────────
# 検索条件（スライダー常時表示）
# ------------------------------------------------
radius_km = st.slider("検索半径 (km)", 0.5, 5.0, 2.0, 0.1)

MAX_TSUBO_UI = 500
min_t, max_t = st.slider(
    "土地面積 (坪)  ※500=500坪以上",
    0,
    MAX_TSUBO_UI,
    (0, MAX_TSUBO_UI),
    step=10,
)

# ────────────────────────────────────────────────
# フィルタ & 距離計算
# ------------------------------------------------
_df["距離(km)"] = _df.apply(lambda r: haversine(center_lat, center_lon, r.latitude, r.longitude), axis=1)

cond = (_df["距離(km)"] <= radius_km) & (_df["土地面積（坪）"] >= min_t)
if max_t < MAX_TSUBO_UI:
    cond &= _df["土地面積（坪）"] <= max_t

flt = _df[cond].copy().sort_values("坪単価（万円/坪）")

# ────────────────────────────────────────────────
# 結果テーブル
# ------------------------------------------------
st.markdown(f"**② 検索結果：{len(flt)} 件**")
cols_order = [
    "住所", "距離(km)", "登録価格（万円）", "坪単価（万円/坪）", "土地面積（坪）", "用途地域", "取引態様", "登録会員", "TEL"
]
cols = [c for c in cols_order if c in flt.columns]
flt["距離(km)"] = flt["距離(km)"].round(2)
st.dataframe(flt[cols], hide_index=True, height=300)

# ────────────────────────────────────────────────
# 地図表示
# ------------------------------------------------
st.markdown("**③ 地図で確認**")
map_center = [center_lat, center_lon]

m = folium.Map(location=map_center, zoom_start=14, control_scale=True)
folium.Marker(map_center, tooltip="検索中心", icon=folium.Icon(color="red", icon="star")).add_to(m)

for _, r in flt.iterrows():
    html = (
        f"<b>{r['住所']}</b><br>"
        f"価格：{r.get('登録価格（万円）', r.get('価格(万円)', '-')):,} 万円<br>"
        f"面積：{r['土地面積（坪）']:.1f} 坪<br>"
        f"<span style='color:#d46b08;'>坪単価：{r['坪単価（万円/坪）']:.1f} 万円/坪</span><br>"
        f"登録会員：{r.get('登録会員', '-') }<br>"
        f"TEL：{r.get('TEL', '-') }"
    )
    folium.Marker(
        [r.latitude, r.longitude],
        popup=folium.Popup(html, max_width=260),
        tooltip=r["住所"],
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
    ).add_to(m)

st_folium(m, width="100%", height=480)

# ────────────────────────────────────────────────
st.caption("Powered by Streamlit ❘ Google Maps Geocoding API")
