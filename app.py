import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# ★ APIキーは、Geocoding API を有効化したものを使ってください
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFS5_myBGJVi45Iyg"

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

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# --- 1) データ読み込み & 列名クリーンアップ ---
df = pd.read_csv("住所付き_緯度経度付きデータ.csv", encoding="utf-8-sig")
# 余計な空白除去
df.columns = [c.strip() for c in df.columns]

# もし「テーブル1_1.登録会員」という名前なら「登録会員」にリネーム
rename_map = {}
if "テーブル1_1.登録会員" in df.columns:
    rename_map["テーブル1_1.登録会員"] = "登録会員"
if "土地面積（㎡）" in df.columns:
    # 後で坪に換算するため残す
    rename_map["土地面積（㎡）"] = "土地面積_m2"
if "latitude" not in df.columns and "lat" in df.columns:
    rename_map["lat"] = "latitude"
if "longitude" not in df.columns and "lng" in df.columns:
    rename_map["lng"] = "longitude"

df = df.rename(columns=rename_map)

# 「土地面積（坪）」がない場合は㎡→坪に変換して追加
if "土地面積_m2" in df.columns and "土地面積（坪）" not in df.columns:
    df["土地面積（坪）"] = df["土地面積_m2"] * 0.3025

# --- 2) Streamlit UI ---
st.title("売土地データ検索ツール")

# デバッグ：列一覧を確認
st.write("### CSV 列一覧", df.columns.tolist())

address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")
if not address_query:
    st.info("検索する住所を入力してください。")
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None:
    st.warning("📍 Googleで該当住所が見つかりませんでした。")
    st.stop()
st.success(f"中心座標：{center_lat:.6f}, {center_lon:.6f}")

max_distance = st.slider("📏 検索範囲（km）", 0.0, 10.0, 2.0, 0.1)

# 距離計算＆フィルタ
df["距離km"] = df.apply(
    lambda r: haversine(center_lat, center_lon, r["latitude"], r["longitude"]),
    axis=1
)
filtered = df[df["距離km"] <= max_distance].sort_values("坪単価（万円）", ascending=False)
if len(filtered) > 2:
    filtered = filtered.iloc[1:-1]

# 表示列の指定
cols = [
    "住所",
    "登録価格（万円）",
    "坪単価（万円）",
    "土地面積（坪）",
    "用途地域",
    "取引態様",
    "登録会員",
    "TEL",
    "公開日",
]
cols = [c for c in cols if c in filtered.columns]

st.subheader(f"🔎 抽出結果：{len(filtered)} 件")
st.dataframe(filtered[cols])

csv = filtered[cols].to_csv(index=False, encoding="utf-8-sig")
st.download_button("📥 結果をCSVでダウンロード", data=csv, file_name="filtered_data.csv")

# 地図表示
if not filtered.empty:
    st.subheader("🗺️ 該当物件の地図表示")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    for _, r in filtered.iterrows():
        html = f"""
        <div style="width:250px;">
          <strong>{r.get('住所','-')}</strong><br>
          <ul style="padding-left:15px;margin:0;">
            <li>価格：{r.get('登録価格（万円）','-')} 万円</li>
            <li>坪単価：{r.get('坪単価（万円）','-')} 万円</li>
            <li>土地面積：{r.get('土地面積（坪）','-')} 坪</li>
            <li>用途地域：{r.get('用途地域','-')}</li>
            <li>取引態様：{r.get('取引態様','-')}</li>
            <li>登録会員：{r.get('登録会員','-')}</li>
            <li>TEL：{r.get('TEL','-')}</li>
            <li>公開日：{r.get('公開日','-')}</li>
          </ul>
        </div>
        """
        folium.Marker(
            location=[r["latitude"], r["longitude"]],
            popup=folium.Popup(html, max_width=300),
            tooltip=r.get("住所","")
        ).add_to(m)
    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
