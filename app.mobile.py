# streamlit_app.py  (キーをハードコードしない安全版)
import os
import time
import urllib.parse
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium
from folium import Map, Marker, Icon, Popup

# ------------------------------------------------------------------
# API キー取得  (.env > 環境変数)
# ------------------------------------------------------------------
try:
    from dotenv import load_dotenv      # pip install python-dotenv
except ImportError:
    load_dotenv = None                  # 未インストールでも動く

def get_api_key() -> str:
    """GOOGLE_MAPS_API_KEY を .env または環境変数から取得（見つからなければ停止）"""
    if load_dotenv:
        load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)

    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        st.error(
            "環境変数 GOOGLE_MAPS_API_KEY が設定されていません。\n"
            "  例）PowerShell:  $Env:GOOGLE_MAPS_API_KEY = \"YOUR_KEY\"\n"
            "       bash/zsh  :  export GOOGLE_MAPS_API_KEY=\"YOUR_KEY\"\n"
            "  もしくはこのスクリプトと同じフォルダに .env を作成し\n"
            "  GOOGLE_MAPS_API_KEY=\"YOUR_KEY\" と記載してください。"
        )
        st.stop()
    return key

GOOGLE_API_KEY = get_api_key()

# ------------------------------------------------------------------
# Streamlit 初期設定
# ------------------------------------------------------------------
st.set_page_config(page_title="🏠 売土地検索", layout="centered")
st.title("🏠 売土地検索")
st.caption("指定した住所または現在地を中心に、半径 0.5〜5 km 内の土地情報を検索します。")

# ------------------------------------------------------------------
# 住所⇔座標
# ------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def geocode(address: str):
    params = {
        "address": address,
        "key": GOOGLE_API_KEY,
        "language": "ja",
    }
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(params, safe=":")
    data = requests.get(url, timeout=10).json()
    if data.get("status") == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, None

def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# ------------------------------------------------------------------
# サイドバー：設定
# ------------------------------------------------------------------
with st.sidebar:
    st.header("🔧 検索条件")
    csv_file = st.file_uploader("📄 CSV を選択（UTF-8-BOM）", type="csv")
    if csv_file is None:
        csv_file = "住所付き_緯度経度付きデータ_1.csv"        # 既定値
    radius = st.slider("検索半径 (km)", 0.5, 5.0, 2.0, 0.1)
    sort_price = st.toggle("坪単価でソート", value=False)

# ------------------------------------------------------------------
# 中心地点の取得
# ------------------------------------------------------------------
st.subheader("1️⃣ 検索中心を指定")
addr_input = st.text_input("🔍 住所を入力（例：浜松市中区）")

center_lat = center_lon = None
if addr_input:
    center_lat, center_lon = geocode(addr_input.strip())

if (center_lat, center_lon) == (None, None):
    st.stop()

# ------------------------------------------------------------------
# データ読込 & 前処理
# ------------------------------------------------------------------
try:
    df = pd.read_csv(csv_file, encoding="utf-8-sig")
except Exception as e:
    st.error(f"CSV 読み込み失敗: {e}")
    st.stop()

df.columns = df.columns.str.strip()
if "土地面積（坪）" not in df and "土地面積（㎡）" in df:
    df["土地面積（坪）"] = (df["土地面積（㎡）"] * 0.3025).round(2)

df = df.dropna(subset=["latitude", "longitude", "土地面積（坪）"])

df["距離km"] = df.apply(lambda r: haversine(center_lat, center_lon, r.latitude, r.longitude), axis=1)
df = df[df["距離km"] <= radius]

if sort_price and "坪単価（万円）" in df:
    df = df.sort_values("坪単価（万円）", ascending=False)
else:
    df = df.sort_values("距離km")

# ------------------------------------------------------------------
# 結果表示
# ------------------------------------------------------------------
st.subheader(f"2️⃣ 検索結果（{len(df)} 件）")
if df.empty:
    st.info("該当物件がありませんでした。")
    st.stop()

show_cols = [
    c for c in [
        "住所","距離km","登録価格（万円）","坪単価（万円）",
        "土地面積（坪）","用途地域","取引態様","登録会員","TEL","公開日"
    ] if c in df.columns
]
df["距離km"] = df["距離km"].round(2)
st.dataframe(df[show_cols], hide_index=True)

# ------------------------------------------------------------------
# 地図
# ------------------------------------------------------------------
st.subheader("3️⃣ 地図で確認")
m = Map(location=[center_lat, center_lon], zoom_start=14)
Marker([center_lat, center_lon],
       tooltip="検索中心",
       icon=Icon(color="red", icon="star")).add_to(m)

for _, r in df.iterrows():
    html = f"""
<strong>{r['住所']}</strong><br>
価格: {r['登録価格（万円）']} 万円<br>
坪単価: {r['坪単価（万円）']} 万円<br>
距離: {r['距離km']:.2f} km
"""
    Marker([r.latitude, r.longitude],
           tooltip=r.住所,
           popup=Popup(html, max_width=250),
           icon=Icon(color="blue", icon="info-sign")).add_to(m)

st_folium(m, width=700, height=500)
