import os
import urllib.parse
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# ------------------------------------------------------------
# 🔑 API キー取得（.env のみを見る）
# ------------------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv   # pip install python-dotenv
except ImportError:
    st.error("python-dotenv がインストールされていません。  pip install python-dotenv")
    st.stop()

load_dotenv(find_dotenv(usecwd=True), override=False)

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_API_KEY:
    st.error(
        ".env が見つからないか、GOOGLE_MAPS_API_KEY が設定されていません。\n"
        '同じフォルダに .env を作成し、1 行だけ\n'
        'GOOGLE_MAPS_API_KEY="YOUR_API_KEY"\n'
        "と記載してください。"
    )
    st.stop()

# ------------------------------------------------------------
# ページ設定
# ------------------------------------------------------------
st.set_page_config(page_title="売土地検索（スマホ）", page_icon="🏠", layout="centered")
st.title("🏠 売土地検索（スマホ）")
st.caption("住所を入力して、半径 0.5〜5 km 内の土地情報を検索します。")

CSV_PATH = "住所付き_緯度経度付きデータ_1.csv"   # 既定の CSV 名

# ------------------------------------------------------------
# ユーティリティ
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def geocode_address(address: str):
    """住所 → (lat, lon)。失敗時は (None, None)。"""
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
# 住所入力のみの UI
# ------------------------------------------------------------
st.subheader("1️⃣ 検索中心の住所を入力")
address_input = st.text_input("🔍 住所（例：浜松市中区）")

if not address_input:
    st.stop()

center_lat, center_lon = geocode_address(address_input.strip())
if center_lat is None:
    st.warning("📍 住所が見つかりませんでした。もう一度入力してください。")
    st.stop()

st.success(f"検索中心：{center_lat:.6f}, {center_lon:.6f}")

# ------------------------------------------------------------
# 検索条件
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
# フィルタ & 距離計算
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
st.subheader("3️⃣ 地図で確認")
m = folium.Map(location=[center_lat, center_lon], zoom_start=14)

# 検索中心マーカー
folium.Marker(
    [center_lat, center_lon],
    tooltip="検索中心",
    icon=folium.Icon(color="red", icon="star")
).add_to(m)

# 物件マーカー
for _, r in filtered.iterrows():
    popup_html = f"""
    <strong>{r['住所']}</strong><br>
    登録価格: {r['登録価格（万円）']} 万円<br>
    坪数: {r['土地面積（坪）']} 坪<br>
    登録会員: {r.get('登録会員', '-') if '登録会員' in r else '-'}<br>
    電話番号: {r.get('TEL', '-') if 'TEL' in r else '-'}
    """
    folium.Marker(
        [r.latitude, r.longitude],
        tooltip=r['住所'],
        popup=folium.Popup(popup_html, max_width=250),
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)

st_folium(m, width=700, height=500)
