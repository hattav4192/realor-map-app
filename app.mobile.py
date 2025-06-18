import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# ------------------------------
# 設定
# ------------------------------
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"
st.set_page_config(page_title="売土地検索", layout="centered")

st.title("🏠 売土地検索")
st.markdown("指定した住所を中心に、半径2km以内の土地情報を表示します。")

# ------------------------------
# 逆ジオコーディング（必要な場合のみ）
# ------------------------------
def reverse_geocode(lat: float, lon: float, api_key: str) -> str:
    """緯度経度から住所を取得します。"""
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}"
    data = requests.get(url).json()
    if data.get("status") == "OK":
        return data["results"][0]["formatted_address"]
    return ""

# ------------------------------
# ジオコーディング（住所→座標）
# ------------------------------
def geocode_address(address: str, api_key: str):
    """住所から緯度経度を取得します。失敗した場合は (None, None) を返す。"""
    try:
        clean = address.strip().replace("　", "").replace(" ", "")
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={clean}&key={api_key}"
        data = requests.get(url).json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
        else:
            st.error(f"住所が見つかりません（APIステータス: {data['status']}）")
    except Exception as e:
        st.error(f"ジオコーディング中にエラーが発生しました: {e}")
    return None, None

# ------------------------------
# 距離計算（ハバースイン法）
# ------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離（km）を計算"""
    R = 6371  # 地球半径 (km)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# ------------------------------
# 住所入力フォーム
# ------------------------------
address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")

if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None:
    st.stop()

# ------------------------------
# データ読み込み・前処理
# ------------------------------
csv_file = "住所付き_緯度経度付きデータ_1.csv"
df = pd.read_csv(csv_file, encoding="utf-8-sig")
# 列名の余分な空白除去
df.columns = df.columns.str.strip()

# メートル→坪変換 (1㎡ ≒ 0.3025坪)
if "土地面積（坪）" not in df.columns and "土地面積（㎡）" in df.columns:
    df["土地面積（坪）"] = (df["土地面積（㎡）"] * 0.3025).round(2)

# 必要な列を空白文字ではなく NaN と扱う
for col in ["用途地域", "登録会員", "TEL", "公開日"]:
    if col in df.columns:
        df[col] = df[col].replace({"": pd.NA})

# 緯度経度と坪面積が揃っている行のみ残す
required_cols = ["latitude", "longitude", "土地面積（坪）"]
df = df.dropna(subset=required_cols)

# 距離計算
_df = df.copy()
_df["距離km"] = _df.apply(
    lambda r: haversine(center_lat, center_lon, r["latitude"], r["longitude"]), axis=1
)

# ------------------------------
# フィルタリング・並び替え
# ------------------------------
filtered = _df[_df["距離km"] <= 2.0].sort_values(by="坪単価（万円）", ascending=False)
if len(filtered) > 2:
    filtered = filtered.iloc[1:-1]

# ------------------------------
# 結果表示
# ------------------------------
st.subheader("📋 該当物件一覧")
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

display_cols = [c for c in cols if c in filtered.columns]

st.dataframe(filtered[display_cols])

# ------------------------------
# 地図表示
# ------------------------------
if not filtered.empty:
    st.subheader("🗺️ 地図で確認")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    # 中心マーカー
    folium.Marker(
        [center_lat, center_lon],
        popup="検索中心",
        icon=folium.Icon(color="red", icon="star"),
    ).add_to(m)

    # 物件マーカー
    for _, r in filtered.iterrows():
        popup_html = f"""
<div style='width:250px;'>
  <strong>{r['住所']}</strong><br>
  <ul style='padding-left:15px;margin:0;'>
    <li>価格：{r['登録価格（万円）']} 万円</li>
    <li>坪単価：{r['坪単価（万円）']} 万円</li>
    <li>土地面積：{r['土地面積（坪）']} 坪</li>
    <li>用途地域：{r.get('用途地域', '(情報なし)')}</li>
    <li>取引態様：{r.get('取引態様', '(情報なし)')}</li>
    <li>登録会員：{r.get('登録会員', '(情報なし)')}</li>
    <li>TEL：{r.get('TEL', '(情報なし)')}</li>
    <li>公開日：{r.get('公開日', '(情報なし)')}</li>
  </ul>
</div>
"""
        folium.Marker(
            [r['latitude'], r['longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=r['住所'],
            icon=folium.Icon(color="blue", icon="info-sign"),
        ).add_to(m)

    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
