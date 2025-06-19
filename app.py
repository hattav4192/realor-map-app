# app.py  ――― Streamlit 売土地検索ツール
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
    from dotenv import load_dotenv, find_dotenv          # pip install python-dotenv
except ImportError:
    st.error("python-dotenv がありません。  pip install python-dotenv でインストールしてください。")
    st.stop()

# `.env` を現在の作業フォルダ〜上位階層で検索して読み込む
load_dotenv(find_dotenv(usecwd=True), override=False)

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_API_KEY:
    st.error(
        ".env が見つからないか、GOOGLE_MAPS_API_KEY が設定されていません。\n"
        "同じフォルダに .env を置き、次の 1 行を記載してください：\n\n"
        'GOOGLE_MAPS_API_KEY="YOUR_API_KEY"'
    )
    st.stop()

# ------------------------------------------------------------
# ページ設定
# ------------------------------------------------------------
st.set_page_config(page_title="売土地検索ツール", page_icon="🏠", layout="centered")
CSV_PATH = "住所付き_緯度経度付きデータ.csv"    # 既存ファイル名そのまま

# ------------------------------------------------------------
# 補助関数
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
# Streamlit UI
# ------------------------------------------------------------
st.title("🏠 売土地検索ツール")

address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")
if not address_query:
    st.info("検索する住所を入力してください。")
    st.stop()

center_lat, center_lon = geocode_address(address_query)
if center_lat is None:
    st.warning("📍 Google で該当住所が見つかりませんでした。")
    st.stop()
st.success(f"中心座標：{center_lat:.6f}, {center_lon:.6f}")

max_distance = st.slider("📏 検索範囲（km）", 0.0, 50.0, 2.0, 0.1)
min_area, max_area = st.slider(
    "📐 土地面積（坪）の範囲",
    0.0,
    float(df["土地面積（坪）"].max()),
    (0.0, 1000.0),
    1.0,
)

# ------------------------------------------------------------
# フィルタ処理
# ------------------------------------------------------------
df["距離km"] = df.apply(
    lambda r: haversine(center_lat, center_lon, r.latitude, r.longitude),
    axis=1,
)

filtered = df[
    (df["距離km"] <= max_distance) &
    (df["土地面積（坪）"].between(min_area, max_area))
].copy()

filtered = filtered.sort_values("坪単価（万円）", ascending=False)
if len(filtered) > 2:
    filtered = filtered.iloc[1:-1]

# ------------------------------------------------------------
# 結果表示
# ------------------------------------------------------------
show_cols = [
    "住所","登録価格（万円）","坪単価（万円）","土地面積（坪）",
    "用途地域","取引態様","登録会員","TEL","公開日"
]
show_cols = [c for c in show_cols if c in filtered.columns]

st.subheader(f"🔎 抽出結果：{len(filtered)} 件")
st.dataframe(filtered[show_cols], use_container_width=True)

csv_data = filtered[show_cols].to_csv(index=False, encoding="utf-8-sig")
st.download_button(
    "📥 結果を CSV でダウンロード",
    data=csv_data,
    file_name="filtered_data.csv",
    mime="text/csv",
)

# ------------------------------------------------------------
# 地図表示
# ------------------------------------------------------------
if filtered.empty:
    st.info("該当する物件がありませんでした。")
    st.stop()

st.subheader("🗺️ 該当物件の地図表示")
m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
folium.Marker(
    [center_lat, center_lon],
    tooltip="検索中心",
    icon=folium.Icon(color="red", icon="star"),
).add_to(m)

for _, row in filtered.iterrows():
    popup_html = f"""
    <div style="width:250px;">
      <strong>{row.get('住所','-')}</strong><br>
      <ul style="padding-left:15px;margin:0;">
        <li>価格：{row.get('登録価格（万円）','-')} 万円</li>
        <li>坪単価：{row.get('坪単価（万円）','-')} 万円</li>
        <li>土地面積：{row.get('土地面積（坪）','-')} 坪</li>
        <li>用途地域：{row.get('用途地域','-')}</li>
        <li>取引態様：{row.get('取引態様','-')}</li>
        <li>登録会員：{row.get('登録会員','-')}</li>
        <li>TEL：{row.get('TEL','-')}</li>
        <li>公開日：{row.get('公開日','-')}</li>
      </ul>
    </div>
    """
    folium.Marker(
        [row.latitude, row.longitude],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=row.get("住所", ""),
    ).add_to(m)

st_folium(m, width=700, height=500)
