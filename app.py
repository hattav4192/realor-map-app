#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
realor-map-app / Streamlit  ✨デスクトップ版 rev18

2025-07-16
──────────────────────────────────────────────
● 列名 strip & マッピング + 正規表現で自動判定
● 必要ならUIで面積列指定
● 30坪以下は常に除外
● ソートは常に「坪単価(万円/坪) 降順」
● 列とデータを物理的に入れ替えて「価格 → 坪単価 → 土地面積」の順に表示
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

import market_layer as ml   # 実勢価格レイヤー（国交省データ）

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
        if js.get("status") == "OK":
            loc = js["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except:
        pass
    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

@st.cache_data(show_spinner="CSV読み込み中…")
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
ALIAS: Dict[str,str] = {
    **{k:"lon" for k in ["lon","longitude","lng","経度"]},
    **{k:"lat" for k in ["lat","latitude","緯度"]},
    **{k:"所在地" for k in ["所在地","住所","Addr","Address"]},
    **{k:"価格(万円)" for k in ["価格(万円)","価格","登録価格（万円）","金額(万円)"]},
    **{k:"土地面積(㎡)" for k in ["土地面積(㎡)","面積（㎡）","面積㎡"]},
    **{k:"土地面積(坪)" for k in ["土地面積(坪)","面積（坪）"]},
}
REQUIRED={"価格(万円)","lat","lon","所在地"}

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c:ALIAS[c] for c in df.columns if c in ALIAS})
    for col in df.columns:
        if re.search(r"(日付|掲載日|公開日|更新日)",col) and "日付" not in df.columns:
            df = df.rename(columns={col:"日付"})
        if re.search(r"(㎡|m2|m²)",col) and "土地面積(㎡)" not in df.columns:
            df = df.rename(columns={col:"土地面積(㎡)"})
        if re.search(r"(坪)",col) and "土地面積(坪)" not in df.columns:
            df = df.rename(columns={col:"土地面積(坪)"})
    for miss in (REQUIRED-set(df.columns)):
        sel = st.selectbox(f"列『{miss}』を選択", [c for c in df.columns if c not in REQUIRED], key=miss)
        if sel: df = df.rename(columns={sel:miss})
    lack = REQUIRED-set(df.columns)
    if lack:
        st.error(f"必須列不足 → {', '.join(lack)}")
        st.stop()
    return df

# ──────────────────────────────────────────────
def main():
    st.set_page_config(page_title="売土地検索ツール", page_icon="🏡", layout="wide")

    # iPhoneホーム画面アイコン（Apple Touch Icon）
    _ICON_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAIAAACyr5FlAAAEC0lEQVR4nO3dXU7bQBSGYYO6h160"
        "+0AqW2nXUAnhVQQhsQbW0ovuY266i0qkjQLOZ9nOjOf8vM8VQiHEZ96MkxCRmy/fvg/AJbcXvwsQ"
        "B+YQByTigEQckIgDEnFAIg5IxAGJOCARByTigEQckIgDEnFAIg5IxAGJOCARByTigEQckIgDEnFA"
        "Ig5IxAGJOCARByTieKf8eu19Ewwhjo9l0McJcfxz3gR9HBHH5RoKfRDHTAclfR/Z45gvoOTuI3Uc"
        "S9a+JO4jbxzLV71k7SNpHGvXu6TsI2Mc21a65OvjJtt/E7xyjb/e/9h8Vec/60KuneP6e3/JtH8k"
        "iqPWupY0fWSJo+6Klhx9pIijxVqWBH3EjyPDKjYSPw5sFjwOto1rRI6DMq4UNg7KuF7MOCijioBx"
        "UEYt0eKgjIpCxUEZdcWJgzKqCxIHZbQQIQ7KaMR9HJTRju84KKMpx3FQRmte46CMHbiMgzL24S8O"
        "v2UUb7fcWRzu5uv69nuKw9dkAxyFmzgczTTMsfiIw8s0gx2RgzhczDHkcVmPw/4EAx+d6TiMzy78"
        "MdqNw/LUkhyp0TjMzivV8VqMw+akEh61uTgMzijtsduKw9p0kk/AUBym5tKRnTlYicPORCwoNqZh"
        "JQ4YZCIOI3cUU4qBmfSPw8IUbCq9J3Ob/PiNK13n0zMOyjA+pW5xUIb9WfWJgzJcTKxDHJThZW57"
        "x0EZjqa3axyU4WuG+8VBGe4muVMclOFxnnvEQRlOp9o8DsrwO9u2cVBGa00n3DAOythHuzl3/gBA"
        "ArL8sYH9/2QPs4gDEnFAIg5IxAGJOCARByTigEQckIgDEnFAIg5IxAFvr5Aaf79dyfHuRnYOSMQB"
        "iTggEQck4oBEHJCIAxJxwNuLYAbfMxf+lk+xc0AiDkjEAYk4IBEHJOKARByQiAMScUAiDkjEAYk4"
        "IBEHJOKARByQiAMScUAiDkjEAYk4IBEHJOKARByQiAMScUAiDkjEAYk4IBEHrH4iNSxj54BEHJCI"
        "AxJxIGUc4/NT3cuP4gJrf5EXkeNAzH8Yt9aq+/Th4bHWLz1UuiqbgsRxcZF2XrzxLcRIuXBaWWR8"
        "fjqu/emL6QUiZRHtFdKFjwpPS7j28sOkgPNrOH4/WCJBTisb9vPp5Zcv7fg/i1MTQ0ScVrY4PDxG"
        "2iGC7xyr7rsZ1rWKIHEsX/J2p4Ax3Mkl5mnlfJ3qrtkonq2EPNcE2TmWr8q29RvfPwJNIuDOMf+k"
        "Y9tGcnjbFdTVque33gXZOdY+He3ycrs7QV4Em9/2Pyx5xcUeQ8cUJA60EPAxB2ohDkjEAYk4IBEH"
        "JOKARByQiAMScUAiDgzKX+nMdDUJ3qNWAAAAAElFTkSuQmCC"
    )
    st.markdown(
        f'<link rel="apple-touch-icon" href="data:image/png;base64,{_ICON_B64}">',
        unsafe_allow_html=True,
    )

    st.title("🏡 売土地検索ツール")

    if not CSV_PATH.exists():
        st.error(f"{CSV_PATH} が見つかりません"); return
    df = standardize_columns(load_csv(CSV_PATH))

    # 数値変換＋面積・単価計算
    df["価格(万円)"] = pd.to_numeric(df["価格(万円)"].astype(str).str.replace(",",""), errors="coerce")
    if "土地面積(坪)" not in df.columns and "土地面積(㎡)" in df.columns:
        df["土地面積(坪)"] = (pd.to_numeric(df["土地面積(㎡)"], errors="coerce")/3.305785).round(2)
    if "土地面積(㎡)" not in df.columns and "土地面積(坪)" in df.columns:
        df["土地面積(㎡)"] = (pd.to_numeric(df["土地面積(坪)"], errors="coerce")*3.305785).round(2)
    df["土地面積(坪)"]   = pd.to_numeric(df["土地面積(坪)"], errors="coerce").round(2)
    df["坪単価(万円/坪)"] = (df["価格(万円)"] / df["土地面積(坪)"]).round(1)

    # 住所入力→距離
    st.subheader("① 検索中心の住所を入力")
    addr = st.text_input("例：浜松市中区高林1丁目")
    if not addr: return
    clat, clon = geocode(addr.strip())
    if clat is None:
        st.error("住所が見つかりません"); return
    df["距離(km)"] = df.apply(lambda r: haversine(clat, clon, r.lat, r.lon), axis=1)

    # 条件
    with st.sidebar:
        st.header("検索条件")
        radius = st.slider("検索半径 (km)", 0.5, 5.0, 2.0, 0.1)
        tmin, tmax = st.slider("土地面積 (坪) ※500=500坪以上", 0, 500, (0, 500), step=10)

    cond = (
        (df["距離(km)"] <= radius) &
        (df["土地面積(坪)"] >= tmin) &
        (df["土地面積(坪)"] > 30)
    )
    if tmax < 500:
        cond &= df["土地面積(坪)"] <= tmax

    # 坪単価降順でソート
    df_flt = df[cond].sort_values("坪単価(万円/坪)", ascending=False)

    # ── 実勢相場パネル ＋ 各物件の「周辺相場比」列 ─────────────
    _mkt = ml.render_market_panel(clat, clon, radius)
    _bench = _mkt.get("benchmark")
    if _bench:
        df_flt["周辺相場比"] = df_flt["坪単価(万円/坪)"].apply(
            lambda p: ml.deviation_label(ml.deviation_pct(p, _bench))
        )

    # テーブル表示：価格 → 坪単価 → 周辺相場比 → 土地面積
    st.subheader(f"② 検索結果：{len(df_flt):,} 件")
    cols_order = ["所在地","日付","距離(km)","価格(万円)","坪単価(万円/坪)","周辺相場比","土地面積(坪)","登録会員","TEL"]
    display_cols = [c for c in cols_order if c in df_flt.columns]
    st.dataframe(df_flt[display_cols], height=300)

    # 地図表示
    if df_flt.empty:
        st.info("該当物件なし"); return

    m = folium.Map(location=[clat, clon], zoom_start=14, control_scale=True)
    folium.Marker([clat, clon], tooltip="検索中心",
                  icon=folium.Icon(color="red", icon="star")).add_to(m)

    for _, r in df_flt.iterrows():
        raw = r["価格(万円)"]
        price = f"{float(raw):,}" if pd.notna(raw) else "-"
        popup = (
            f"<b>{r['所在地']}</b><br>"
            + (f"日付：{r.get('日付')}<br>" if "日付" in r else "")
            + f"価格：{price} 万円<br>"
            + f"坪単価：{r['坪単価(万円/坪)']:.1f} 万円/坪<br>"
            + f"土地面積：{r['土地面積(坪)']:.1f} 坪<br>"
            + f"登録会員：{r.get('登録会員','-')}<br>"
            + f"TEL：{r.get('TEL','-')}"
        )
        folium.Marker([r.lat, r.lon],
                      popup=folium.Popup(popup, max_width=260),
                      tooltip=r["所在地"],
                      icon=folium.Icon(color="blue", icon="home", prefix="fa")
        ).add_to(m)

    # 実勢価格レイヤー（取引事例＝紫の点 / 地価公示＝オレンジのピン）
    ml.add_market_markers(m, _mkt.get("tori_near"), _mkt.get("kouji_near"))

    st.markdown("**③ 地図で確認**")
    st_folium(m, width="100%", height=600)

if __name__ == "__main__":
    main()
