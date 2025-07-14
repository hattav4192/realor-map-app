#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
realor-map-app / Streamlit  ✨デスクトップ版 rev5 〈完全版〉

2025-07-14
──────────────────────────────────────────────
• 必須列から **土地面積(㎡)** を除外し、坪⇄㎡ を相互換算
• 一覧テーブルに **登録会員 / TEL** を復活（列がある場合のみ）
• ポップアップにも 登録会員 / TEL を追加
• 距離・面積スライダー、坪単価降順は維持
"""

from __future__ import annotations

import os, urllib.parse, requests
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2
from typing import Dict

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# ──────────────────────────────────────────────
# 🔑 Google Maps API Key
# ------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
CSV_PATH = Path("住所付き_緯度経度付きデータ_1.csv")

# ──────────────────────────────────────────────
# ユーティリティ
# ------------------------------------------------
def geocode(addr: str):
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
    R = 6371.0
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


@st.cache_data(show_spinner="CSV を読み込み中 …")
def load_csv(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    import charset_normalizer
    enc = charset_normalizer.detect(path.read_bytes()).get("encoding", "utf-8")
    return pd.read_csv(path, encoding=enc, errors="replace")


# 列名マッピング辞書
ALIAS: Dict[str, str] = {
    **{k: "lon" for k in ["lon", "longitude", "lng", "経度", "Long"]},
    **{k: "lat" for k in ["lat", "latitude", "緯度", "Lat"]},
    **{k: "所在地" for k in ["所在地", "住所", "所在地（住所）", "Addr"]},
    **{
        k: "価格(万円)"
        for k in ["価格(万円)", "価格", "登録価格（万円）", "登録価格(万円)", "値段", "金額(万円)"]
    },
    **{
        k: "土地面積(㎡)"
        for k in ["土地面積(㎡)", "土地面積㎡", "面積（㎡）", "面積㎡", "土地面積_m2"]
    },
    **{k: "土地面積(坪)" for k in ["土地面積(坪)", "土地面積（坪）", "面積（坪）"]},
}
# 必須列（㎡ を除外）
REQUIRED = {"価格(万円)", "lat", "lon", "所在地"}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: ALIAS[c] for c in df.columns if c in ALIAS})
    missing = list(REQUIRED - set(df.columns))
    if missing:
        st.warning("列名を選択して不足を補完してください：")
        for miss in missing:
            cand = [c for c in df.columns if c not in REQUIRED]
            sel = st.selectbox(f"→ {miss} に該当する列", cand, key=miss)
            if sel:
                df = df.rename(columns={sel: miss})
    still = REQUIRED - set(df.columns)
    if still:
        st.error(f"不足列: {', '.join(still)} → CSV を確認してください。")
        st.stop()
    return df


# ──────────────────────────────────────────────
# メインアプリ
# ------------------------------------------------
def main():
    st.set_page_config(page_title="売土地検索ツール", layout="wide")
    st.title("🏡 売土地検索ツール")

    if not CSV_PATH.exists():
        st.error(f"{CSV_PATH} が見つかりません。")
        st.stop()

    df = standardize_columns(load_csv(CSV_PATH))

    # 数値整形
    df["価格(万円)"] = pd.to_numeric(
        df["価格(万円)"].astype(str).str.replace(",", ""), errors="coerce"
    )

    # 面積列の相互補完
    if "土地面積(㎡)" not in df.columns and "土地面積(坪)" in df.columns:
        df["土地面積(㎡)"] = (
            pd.to_numeric(df["土地面積(坪)"], errors="coerce") * 3.305785
        ).round(2)
    if "土地面積(坪)" not in df.columns and "土地面積(㎡)" in df.columns:
        df["土地面積(坪)"] = (
            pd.to_numeric(df["土地面積(㎡)"], errors="coerce") / 3.305785
        ).round(2)

    if {"土地面積(坪)", "土地面積(㎡)"}.isdisjoint(df.columns):
        st.error("土地面積列が見当たりません。CSV をご確認ください。")
        st.stop()

    # 坪単価計算
    df["坪単価(万円/坪)"] = (df["価格(万円)"].div(df["土地面積(坪)"])).round(1)

    # 住所入力
    st.subheader("① 検索中心の住所を入力")
    addr = st.text_input("例：浜松市中区高林1丁目")
    if not addr:
        st.stop()
    center_lat, center_lon = geocode(addr.strip())
    if center_lat is None:
        st.error("住所が見つかりませんでした。")
        st.stop()

    # 距離計算
    df["距離(km)"] = df.apply(
        lambda r: haversine(center_lat, center_lon, r.lat, r.lon), axis=1
    )

    # サイドバー条件
    with st.sidebar:
        st.header("検索条件")
        radius = st.slider("検索半径 (km)", 0.5, 5.0, 2.0, 0.1)
        tsubo_min, tsubo_max = st.slider(
            "土地面積 (坪) ※500=500坪以上", 0, 500, (0, 500), step=10
        )

    cond = (df["距離(km)"] <= radius) & (df["土地面積(坪)"] >= tsubo_min)
    if tsubo_max < 500:
        cond &= df["土地面積(坪)"] <= tsubo_max
    df_flt = df[cond]

    # 一覧表示
    st.subheader(f"② 検索結果：{len(df_flt):,} 件")
    base_cols = [
        "所在地",
        "距離(km)",
        "価格(万円)",
        "土地面積(坪)",
        "坪単価(万円/坪)",
        "登録会員",
        "TEL",
    ]
    cols = [c for c in base_cols if c in df_flt.columns]
    st.dataframe(
        df_flt[cols].sort_values("坪単価(万円/坪)", ascending=False), height=300
    )

    if df_flt.empty:
        st.info("該当する物件がありません。条件を調整してください。")
        return

    # 地図
    m = folium.Map(
        location=[center_lat, center_lon], zoom_start=14, control_scale=True
    )
    folium.Marker(
        [center_lat, center_lon],
        tooltip="検索中心",
        icon=folium.Icon(color="red", icon="star"),
    ).add_to(m)

    for _, r in df_flt.iterrows():
        html = (
            f"<b>{r['所在地']}</b><br>"
            f"価格：{r['価格(万円)']:,} 万円<br>"
            f"面積：{r['土地面積(坪)']:.1f} 坪<br>"
            f"<span style='color:#d46b08;'>坪単価：{r['坪単価(万円/坪)']:.1f} 万円/坪</span><br>"
            f"登録会員：{r.get('登録会員', '-') }<br>"
            f"TEL：{r.get('TEL', '-') }"
        )
        folium.Marker(
            [r.lat, r.lon],
            popup=folium.Popup(html, max_width=260),
            tooltip=r["所在地"],
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        ).add_to(m)

    st_folium(m, width="100%", height=600)


if __name__ == "__main__":
    main()
