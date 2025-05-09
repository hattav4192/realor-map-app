import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# ------------------------------
# Google Maps APIキー（Geocoding APIを有効化したもの）
# ------------------------------
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFS5_myBGJVi45Iyg"

# ------------------------------
# Googleジオコーディング（params 方式）
# ------------------------------
def geocode_address(address, api_key):
    try:
        params = {"address": address, "key": api_key}
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=5
        )
        data = resp.json()
        status = data.get("status")
        st.write("📥 Geocoding status:", status)
        if status == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception as e:
        st.error(f"Geocoding error: {e}")
    return None, None

# ------------------------------
# 距離計算（haversine）
# ------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# ------------------------------
# データ読み込み
# ------------------------------
df = pd.read_csv("住所付き_緯度経度付きデータ.csv", encoding="utf-8-sig")
df.columns = [c.strip() for c in df.columns]  # 列名の空白除去
st.write("### CSV 列一覧:", df.columns.tolist())

# 必要に応じて列名をリネーム
if "lat" in df.columns and "lng" in df.columns:
    df = df.rename(columns={"lat":"latitude", "lng":"longitude"})

# ------------------------------
# Streamlit UI：住所入力
# ------------------------------
st.title("売土地データ検索ツール")
address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")
if not address_query:
    st.info("検索する住所を入力してください。")
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None:
    st.warning("📍 Googleで該当住所が見つかりませんでした。")
    st.stop()
st.success(f"中心座標：{center_lat:.6f}, {center_lon:.6f}")

# ------------------------------
# UI：検索範囲スライダー
# ------------------------------
max_distance = st.slider("📏 検索範囲（km）", 0.0, 10.0, 2.0, 0.1)

# ------------------------------
# 距離計算とフィルタ
# ------------------------------
df["距離km"] = df.apply(
    lambda r: haversine(center_lat, center_lon, r["latitude"], r["longitude"]),
    axis=1
)
filtered_df = df[df["距離km"] <= max_distance].sort_values("坪単価（万円）", ascending=False)
if len(filtered_df) > 2:
    filtered_df = filtered_df.iloc[1:-1]

# ------------------------------
# 表示列と CSV 出力
# ------------------------------
display_columns = [
    "住所",
    "登録価格（万円）",
    "坪単価（万円）",
    "土地面積（坪）",   # CSV 中の坪単位列をそのまま使う
    "用途地域",
    "取引態様",
    "登録会員",
    "TEL",
    "公開日",
]
display_columns = [c for c in display_columns if c in filtered_df.columns]

st.subheader(f"🔎 抽出結果：{len(filtered_df)} 件")
st.dataframe(filtered_df[display_columns])

csv_data = filtered_df[display_columns].to_csv(index=False, encoding="utf-8-sig")
st.download_button("📥 結果をCSVでダウンロード", data=csv_data, file_name="filtered_data.csv")

# ------------------------------
# 地図表示：Folium＋Popup
# ------------------------------
if not filtered_df.empty:
    st.subheader("🗺️ 該当物件の地図表示")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    for _, row in filtered_df.iterrows():
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
            location=[row["latitude"], row["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row.get("住所","")
        ).add_to(m)
    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
