#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""realor-map-app / Streamlit
改訂版 2025‑07‑14
- CSV 読み込み時のエンコーディング自動判定を強化
- 土地面積(坪) 列を追加し、スライダー上限を常に "500 坪以上" で表示
- マーカーポップアップに坪単価(万円/坪) を追加
"""

from __future__ import annotations

import os
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2
from typing import Tuple, List

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────────
# 🔑 Google Maps API Key (optional)
# ----------------------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv  # pip install python-dotenv

    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    # .env を使わない場合はスルー
    pass

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ──────────────────────────────────────────────────────────────
# 📄 データ読み込み
# ----------------------------------------------------------------
CSV_PATH = Path("data/merged.csv")  # 適宜パス変更

@st.cache_data(show_spinner="CSV を読み込み中 …")
def load_data(path: Path) -> pd.DataFrame:
    """UTF‑8 / UTF‑8‑BOM / Shift‑JIS の順に試し、読めなければ自動判定"""
    encodings = ("utf-8-sig", "utf-8", "cp932")
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue

    # ここに来るのはレアケース
    import charset_normalizer  # pip install charset-normalizer

    guessed = charset_normalizer.detect(path.read_bytes()).get("encoding", "utf-8")
    return pd.read_csv(path, encoding=guessed, errors="replace")


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2 点間距離 (km)"""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


# ──────────────────────────────────────────────────────────────
# 📊 メイン処理
# ----------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="売土地検索ツール", layout="wide")
    st.title("🏡 売土地検索ツール")

    # データロード
    df = load_data(CSV_PATH).copy()

    if df.empty:
        st.error("CSV が空、または読み込めませんでした。パスと内容を確認してください。")
        st.stop()

    # 必須列 チェック
    required = {"価格(万円)", "土地面積(㎡)", "lat", "lon", "所在地"}
    missing = required - set(df.columns)
    if missing:
        st.error(f"CSV に必須列が見つかりません: {', '.join(missing)}")
        st.stop()

    # 土地面積(坪) 列を追加
    df["土地面積(坪)"] = df["土地面積(㎡)"] / 3.305785

    # 坪単価列 (価格 / 坪)
    df["坪単価(万円/坪)"] = df["価格(万円)"] / df["土地面積(坪)"]

    # ── サイドバー フィルター
    with st.sidebar:
        st.header("検索条件")

        # 土地面積スライダー (坪)
        tsubo_max_default = max(500, int(df["土地面積(坪)"].max()) + 50)
        tsubo_min, tsubo_max = st.slider(
            "土地面積 (坪)",
            min_value=0,
            max_value=tsubo_max_default,
            value=(0, tsubo_max_default),
            step=10,
        )

        # 価格スライダー (任意)
        price_min, price_max = st.slider(
            "価格 (万円)",
            min_value=int(df["価格(万円)"].min()),
            max_value=int(df["価格(万円)"].max()),
            value=(int(df["価格(万円)"].min()), int(df["価格(万円)"].max())),
            step=100,
        )

    # ── データフィルタリング
    cond = (
        (df["土地面積(坪)"] >= tsubo_min)
        & (df["土地面積(坪)"] <= tsubo_max)
        & (df["価格(万円)"] >= price_min)
        & (df["価格(万円)"] <= price_max)
    )
    df_flt = df[cond]

    # ── 結果テーブル
    st.subheader(f"検索結果: {len(df_flt):,} 件")
    st.dataframe(
        df_flt[
            [
                "所在地",
                "価格(万円)",
                "土地面積(坪)",
                "坪単価(万円/坪)",
            ]
        ].sort_values("坪単価(万円/坪)"),
        height=300,
    )

    # ── 地図描画
    if not df_flt.empty:
        m = create_map(df_flt)
        st_folium(m, width="100%", height=600)
    else:
        st.info("該当する物件がありません。スライダー条件を調整してください。")


# ──────────────────────────────────────────────────────────────
# 🗺️ folium Map 生成
# ----------------------------------------------------------------

def create_map(df: pd.DataFrame) -> folium.Map:
    # 地図中心は全ピンの平均座標
    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, control_scale=True)

    # マーカー作成
    for _, row in df.iterrows():
        popup_html = (
            f"<b>{row['所在地']}</b><br>"
            f"価格：{row['価格(万円)']:,} 万円<br>"
            f"土地面積：{row['土地面積(坪)']:.1f} 坪 ({row['土地面積(㎡)']:.1f} ㎡)<br>"
            f"<span style='color:#d46b08;'>坪単価：{row['坪単価(万円/坪)']:.1f} 万円/坪</span>"
        )
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_html, max_width=270),
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        ).add_to(m)

    return m


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
