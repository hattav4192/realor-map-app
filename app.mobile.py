# app.mobile.py  ―― スマホ向け 売土地検索ツール (.env でキー管理)
import os
import urllib.parse
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# スマホで現在地を取得するために使用
try:
    from streamlit_js_eval import get_geolocation   # pip install streamlit-js-eval
except ImportError:
    get_geolocation = None

# ------------------------------------------------------------
# 🔑 API キー取得（.env のみを見る）
# ------------------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv     # pip install python-dotenv
except ImportError:
    st.error("python-dotenv がインストールされていません。  pip install python-dotenv")
    st.stop()

load_dotenv(find_dotenv(usecwd=True), override=False)

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_API_KEY:
    st.error(
        ".env が見つからないか、GOOGLE_MAPS_API_KEY が設定されていません。\n"
        '同じフォルダに .env を作成し、次の 1 行を記載してください：\n\n'
        'GOOGLE_MAPS_API_KEY="YOUR_API_KEY"'
    )
    st.stop()

# ------------------------------------------------------------
# ページ設定
# ------------------------------------------------------------
st.set_page_config(page_title="売土地検索（スマホ）", page_icon="🏠", layout="centered")
st.title("🏠 売土地検索（スマホ）")
st.caption("現在地または住所を中心に、半径 0.5〜5 km 内の土地情報を検索します。")

CSV_PATH = "住所付き_緯度経度付きデータ.csv"   # 既存ファイル名そのまま

# ------------------------------------------------------------
# ユーティリティ
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def geocode_address(address: str):
    params = {"address": address, "key": GOOGLE_API_KEY, "language": "ja"}
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(params, safe=":")
    try:
        data = requests.get(url, timeout=5).json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception:
        pass
    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# ------------------------------------------------------------
# データ読み込み & 前処理
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"lat": "latitude", "lng": "longitude"})

    if not {"latitude", "longitude"}.issubset(df.columns):
        st.error("CSV に latitude / longitude 列がありません。")
        st.stop()

    if "土地面積（坪）" not in df.columns:
        if "土地面積（㎡）" in df.columns:
            df["土地面積（坪）"] = (df["土地面積（㎡）"] * 0.3025).round(2)
        else:
            st.error("CSV に土地面積列が見つかりません。")
            st.stop()

    df["土地面積（坪）"] = pd.to_numeric(
        df["土地面積（坪）"].astype(str).str.replace(",", ""), errors="coerce"
    )
    return df

df = load_data(CSV_PATH)

# ------------------------------------------------------------
# 検索中心の入力 UI
# ------------------------------------------------------------
st.subheader("1️⃣ 検索中心の指定")

col1, col2 = st.columns([3, 1])
with col1:
    addr_input = st.text_input("🔍 住所を入力（例：浜松市中区）")
with col2:
    use_geo = st.button("📍 現在地取得")

center_lat = center_lon = None

# 住所入力優先
if addr_input:
    center_lat, center_lon = geocode_address(addr_input.strip())

# 住所なし → 現在地ボタン
if center_lat is None and use_geo:
    if get_geolocation is None:
        st.warning("streamlit_js_eval がインストールされていません。  pip install streamlit-js-eval")
    else:
        loc = get_geolocation()
        if loc and "coords" in loc:
            center_lat = loc["coords"]["latitude"]
            center_lon = loc["coords"]["longitude"]
            st.success("現在地を取得しました")

if center_lat is None:
    st.stop()

st.success(f"検索中心：{center_lat:.6f}, {center_lon:.6f}")

# ------------------------------------------------------------
# 検索設定
# ------------------------------------------------------------
radius = st.slider("📏 検索半径 (km)", 0.5, 5.0, 2.0, 0.1)
min_area, max_area = st.slider(
    "📐 土地面積（坪）の範囲",
    0.0,
    float(df["土地面積（坪）"].max()),
    (0.0, 1000.0),
    1.0,
)

# ------------------------------------------------------------
# フィルタ
# ------------------------------------------------------------
df["距離km"] = df.apply(
    lambda r: haversine(center_lat, center_lon, r.latitude, r.longitude),
    axis=1,
)
filtered = df[
    (df["距離km"] <= radius) &
    (df["土地面積（坪）"].between(min_area, max_area))
].copy()

filtered = filtered.sort_values("坪単価（万円）", ascending=False)
if len(filtered) > 2:
    filtered = filtered.iloc[1:-1]

# ------------------------------------------------------------
# 結果表示
# ------------------------------------------------------------
st.subheader(f"2️⃣ 検索結果：{len(filtered)} 件")
show_cols = [
    "住所","距離km","登録価格（万円）","坪単価（万円）",
    "土地面積（坪）","用途地域","取引態様","登録会員","TEL","公開日"
]
show_cols = [c for c in show_cols if c in filtered.columns]
filtered["距離km"] = filtered["距離km"].round(2)
st.dataframe(filtered[show_cols], hide_index=True)

# ------------------------------------------------------------
# 地図表示
# ------------------------------------------------------------
if filtered.empty:
    st.info("該当する物件がありませんでした。")
    st.stop()

st.subheader("3️⃣ 地図で確認")
m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
folium.Marker(
    [center_lat, center_lon],
    tooltip="検索中心",
    icon=folium.Icon(color="red", icon="star")
).add_to(m)

for _, r in filtered.iterrows():
    popup_html = f"""
<strong>{r['住所']}</strong><br>
価格: {r['登録価格（万円）']} 万円<br>
坪単価: {r['坪単価（万円）']} 万円<br>
距離: {r['距離km']:.2f} km
"""
    folium.Marker(
        [r.latitude, r.longitude],
        tooltip=r.住所,
        popup=folium.Popup(popup_html, max_width=250),
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)

st_folium(m, width=700, height=500)
