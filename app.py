#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
realor-map-app / Streamlit  ✨デスクトップ版 rev15

2025-07-16
──────────────────────────────────────────────
● 列名を str.strip() で前後空白除去
● 列名マッピング網羅 + 正規表現で自動判定
● 面積列が見つからない場合は UI で手動指定 (㎡ / 坪)
● 一覧に 登録会員 / TEL / 日付 を表示、ポップアップにも同情報
● 距離・面積スライダー / 坪単価降順 は維持
● 検索結果で土地面積 30 坪以下を常に除外
"""

from __future__ import annotations
import os, re, urllib.parse
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2
from typing import Dict

import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# ──────────────────────────────────────────────
# APIキー読み込み
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
CSV_PATH        = Path("住所付き_緯度経度付きデータ_1.csv")

# ──────────────────────────────────────────────
# ユーティリティ
def geocode(addr: str):
    if not GOOGLE_API_KEY:
        return None, None
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json?"
        + urllib.parse.urlencode(
            {"address": addr, "key": GOOGLE_API_KEY, "language": "ja"}, safe=":"
        )
    )
    try:
        js = requests.get(url, timeout=5).json()
        if js.get("status")=="OK":
            loc = js["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except:
        pass
    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat, dlon = map(radians, (lat2-lat1, lon2-lon1))
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

@st.cache_data(show_spinner="CSVを読み込み中…")
def load_csv(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig","utf-8","cp932"):
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            return df
        except UnicodeDecodeError:
            continue
    import charset_normalizer
    enc = charset_normalizer.detect(path.read_bytes()).get("encoding","utf-8")
    df = pd.read_csv(path, encoding=enc, errors="replace")
    df.columns = df.columns.str.strip()
    return df

# ──────────────────────────────────────────────
# 列名マッピング＋自動判定
ALIAS = {
    **{k:"lon" for k in ["lon","longitude","lng","経度"]},
    **{k:"lat" for k in ["lat","latitude","緯度"]},
    **{k:"所在地" for k in ["所在地","住所","Addr","Address"]},
    **{k:"価格(万円)" for k in ["価格(万円)","価格","登録価格（万円）","金額(万円)"]},
    **{k:"土地面積(㎡)" for k in ["土地面積(㎡)","面積（㎡）","面積㎡"]},
    **{k:"土地面積(坪)" for k in ["土地面積(坪)","面積（坪）"]},
}
REQUIRED = {"価格(万円)","lat","lon","所在地"}

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # alias→正規列名
    df = df.rename(columns={c:ALIAS[c] for c in df.columns if c in ALIAS})
    # 正規表現で「日付」「㎡」「坪」列も補完
    for col in df.columns:
        if re.search(r"(日付|掲載日|公開日|更新日)", col) and "日付" not in df.columns:
            df = df.rename(columns={col:"日付"})
        if re.search(r"(㎡|m2|m²)", col) and "土地面積(㎡)" not in df.columns:
            df = df.rename(columns={col:"土地面積(㎡)"})
        if re.search(r"(坪)", col) and "土地面積(坪)" not in df.columns:
            df = df.rename(columns={col:"土地面積(坪)"})
    # 必須列不足はUIで選択
    for miss in (REQUIRED-set(df.columns)):
        sel = st.selectbox(f"列『{miss}』を選択", [c for c in df.columns if c not in REQUIRED], key=miss)
        if sel: df = df.rename(columns={sel:miss})
    lack = REQUIRED-set(df.columns)
    if lack:
        st.error(f"必須列不足 → {lack}")
        st.stop()
    return df

# ──────────────────────────────────────────────
# メイン
def main():
    st.set_page_config(page_title="売土地検索ツール", layout="wide")
    st.title("🏡 売土地検索ツール")

    if not CSV_PATH.exists():
        st.error(f"{CSV_PATH} が見つかりません。"); return
    df = standardize_columns(load_csv(CSV_PATH))

    # 数値化＋派生
    df["価格(万円)"] = pd.to_numeric(df["価格(万円)"].astype(str).str.replace(",",""), errors="coerce")
    if "土地面積(坪)" not in df.columns and "土地面積(㎡)" in df.columns:
        df["土地面積(坪)"] = (pd.to_numeric(df["土地面積(㎡)"], errors="coerce")/3.305785).round(2)
    if "土地面積(㎡)" not in df.columns and "土地面積(坪)" in df.columns:
        df["土地面積(㎡)"] = (pd.to_numeric(df["土地面積(坪)"], errors="coerce")*3.305785).round(2)
    df["土地面積(坪)"] = pd.to_numeric(df["土地面積(坪)"], errors="coerce").round(2)
    df["坪単価(万円/坪)"] = (df["価格(万円)"]/df["土地面積(坪)"]).round(1)

    # 入力＆距離計算
    st.subheader("① 検索中心の住所を入力")
    addr = st.text_input("例：浜松市中区高林1丁目")
    if not addr: return
    clat, clon = geocode(addr.strip())
    if clat is None:
        st.error("住所が見つかりません。"); return
    df["距離(km)"] = df.apply(lambda r: haversine(clat,clon,r.lat,r.lon), axis=1)

    # 条件
    with st.sidebar:
        st.header("検索条件")
        radius = st.slider("検索半径(km)", 0.5,5.0,2.0,0.1)
        tmin, tmax = st.slider("土地面積(坪) ※500=500坪以上", 0,500,(0,500),step=10)

    cond = (
        (df["距離(km)"]<=radius) &
        (df["土地面積(坪)"]>=tmin) &
        (df["土地面積(坪)"]>30)
    )
    if tmax<500: cond &= df["土地面積(坪)"]<=tmax

    # **ここで「坪単価降順」でソート**
    df_flt = df[cond].sort_values("坪単価(万円/坪)", ascending=False)

    # 一覧表示
    st.subheader(f"② 検索結果：{len(df_flt):,} 件")
    table_cols = [
        c for c in
        ["所在地","日付","距離(km)","価格(万円)","土地面積(坪)","坪単価(万円/坪)","登録会員","TEL"]
        if c in df_flt.columns
    ]
    st.dataframe(df_flt[table_cols], height=320)

    # 地図
    if df_flt.empty:
        st.info("該当物件がありません。")
        return

    m = folium.Map(location=[clat,clon], zoom_start=14, control_scale=True)
    folium.Marker([clat,clon], tooltip="検索中心", icon=folium.Icon(color="red", icon="star")).add_to(m)
    for _, r in df_flt.iterrows():
        raw = r["価格(万円)"]
        try: price = f"{float(raw):,}"
        except: price = "-"
        popup = (
            f"<b>{r['所在地']}</b><br>"
            + (f"日付：{r.get('日付')}<br>" if "日付" in r else "")
            + f"価格：{price} 万円<br>"
            + f"坪単価：{r['坪単価(万円/坪)']:.1f} 万円/坪<br>"
            + f"土地面積：{r['土地面積(坪)']:.1f} 坪<br>"
            + f"登録会員：{r.get('登録会員','-')}<br>"
            + f"TEL：{r.get('TEL','-')}"
        )
        folium.Marker([r.lat,r.lon], popup=folium.Popup(popup, max_width=260),
                      tooltip=r["所在地"], icon=folium.Icon(color="blue", icon="home", prefix="fa")
        ).add_to(m)

    st.markdown("**③ 地図で確認**")
    st_folium(m, width="100%", height=600)

if __name__ == "__main__":
    main()
