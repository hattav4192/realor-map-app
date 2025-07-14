#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
realor-map-app / Streamlit  ✨デスクトップ版（フルリファクタ）

2025-07-14 rev3
──────────────────────────────────────────────
• 文字コードを自動判定して CSV を読み込み
• 列名の表記ゆれを大幅拡張し、必須列不足を極力回避
• なお不足する場合は UI で手動マッピング可能
• 土地面積(坪)・坪単価(万円/坪) を自動付与
• スライダー上限は常に「500 坪以上」
• Folium ポップアップに坪単価を表示
"""

from __future__ import annotations

import os
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, List

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# ──────────────────────────────────────────────
# 🔑 Google Maps API Key（未使用でも OK）
# ──────────────────────────────────────────────
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

CSV_PATH = Path("住所付き_緯度経度付きデータ_1.csv")

# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────

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


# 表記ゆれ辞書（大幅拡張）
ALIAS: Dict[str, str] = {
    # 経度
    "lon": "lon", "longitude": "lon", "lng": "lon", "経度": "lon", "Long": "lon",
    # 緯度
    "lat": "lat", "latitude": "lat", "緯度": "lat", "Lat": "lat",
    # 所在地
    "所在地": "所在地", "住所": "所在地", "所在地（住所）": "所在地", "Addr": "所在地",
    # 価格
    "価格(万円)": "価格(万円)", "価格": "価格(万円)", "登録価格（万円）": "価格(万円)", "登録価格(万円)": "価格(万円)", "値段": "価格(万円)", "金額(万円)": "価格(万円)",
    # 面積㎡
    "土地面積(㎡)": "土地面積(㎡)", "土地面積㎡": "土地面積(㎡)", "面積（㎡）": "土地面積(㎡)", "面積㎡": "土地面積(㎡)", "土地面積_m2": "土地面積(㎡)",
}

REQUIRED = {"価格(万円)", "土地面積(㎡)", "lat", "lon", "所在地"}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # 1) rename via ALIAS
    ren = {col: ALIAS[col] for col in df.columns if col in ALIAS}
    df = df.rename(columns=ren)

    # 2) 必須列がまだ足りなければ UI で手動マッピング
    missing = list(REQUIRED - set(df.columns))
    if missing:
        st.warning("CSV の列名を自動マッピングできませんでした。以下を指定してください。")
        for miss in missing:
            candidate_cols = [c for c in df.columns if c not in REQUIRED]
            choice = st.selectbox(f"→ {miss} に該当する列", candidate_cols, key=miss)
            if choice:
                df = df.rename(columns={choice: miss})

    # 3) 最終チェック
    still = REQUIRED - set(df.columns)
    if still:
        st.error(f"最終的に不足した列: {', '.join(still)} \nCSV と列設定を確認してください。")
        st.stop()
    return df


# ──────────────────────────────────────────────
# メインアプリ
# ──────────────────────────────────────────────

def main():
    st.set_page_config(page_title="売土地検索ツール", layout="wide")
    st.title("🏡 売土地検索ツール")

    if not CSV_PATH.exists():
        st.error(f"{CSV_PATH} が見つかりません。パスをご確認ください。")
        st.stop()

    df_raw = load_csv(CSV_PATH)
    df = standardize_columns(df_raw.copy())

    # 数値整形
    df["価格(万円)"] = pd.to_numeric(df["価格(万円)"].astype(str).str.replace(",", ""), errors="coerce")
    df["土地面積(㎡)"] = pd.to_numeric(df["土地面積(㎡)"].astype(str).str.replace(",", ""), errors="coerce")

    # 派生列
    df["土地面積(坪)"] = (df["土地面積(㎡)"] / 3.305785).round(2)
    df["坪単価(万円/坪)"] = (df["価格(万円)"].div(df["土地面積(坪)"]).round(1))

    # ── サイドバー ─────────────────────
    with st.sidebar:
        st.header("検索条件")
        tsubo_min, tsubo_max = st.slider("土地面積 (坪) ※500=500坪以上", 0, 500, (0, 500), step=10)
        price_min, price_max = st.slider("価格 (万円)", int(df["価格(万円)"].min()), int(df["価格(万円)"].max()), (int(df["価格(万円)"].min()), int(df["価格(万円)"].max())), step=100)

    # フィルタ
    cond = df["土地面積(坪)"] >= tsubo_min
    if tsubo_max < 500:
        cond &= df["土地面積(坪)"] <= tsubo_max
    cond &= df["価格(万円)"].between(price_min, price_max)
    df_flt = df[cond]

    st.subheader(f"検索結果: {len(df_flt):,} 件")
    st.dataframe(df_flt[["所在地", "価格(万円)", "土地面積(坪)", "坪単価(万円/坪)"]].sort_values("坪単価(万円/坪)"), height=300)

    if df_flt.empty:
        st.info("該当する物件がありません。条件を見直してください。")
        return

    # 地図
    m = folium.Map(location=[df_flt["lat"].mean(), df_flt["lon"].mean()], zoom_start=13, control_scale=True)
    for _, r in df_flt.iterrows():
        html = (
            f"<b>{r['所在地']}</b><br>"
            f"価格：{r['価格(万円)']:,} 万円<br>"
            f"面積：{r['土地面積(坪)']:.1f} 坪 ({r['土地面積(㎡)']:.1f} ㎡)<br>"
            f"<span style='color:#d46b08;'>坪単価：{r['坪単価(万円/坪)']:.1f} 万円/坪</span>"
        )
        folium.Marker([r['lat'], r['lon']], popup=folium.Popup(html, max_width=260), tooltip=r['所在地'], icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(m)
    st_folium(m, width="100%", height=600)


if __name__ == "__main__":
    main()