# -*- coding: utf-8 -*-
"""
build_market_data.py  —  実勢価格レイヤー用データ生成
=====================================================
国土交通省オープンデータ（生ファイル）だけを入力に、realor-map-app 用の
軽量CSVを生成する。手作りの中間Excel（マージ済xlsx）には依存しない。

■ 入力（--src フォルダ直下、または国交省の年次サブフォルダ内を再帰探索）
  1. 不動産取引価格情報 : "*Prefecture*_*.csv"           （cp932 / 28列 / ヘッダーあり）
  2. 地価公示 標準地(宅地): "*TAKUCHI_k*.csv"             （cp932 / 1408列 / ヘッダー無し）
  3. 地価公示の列名定義   : "*ファイル項目.xlsx"          （1行 × 1408列の見出し。無ければ説明書から復元）
     予備               : "*ファイル項目説明書.xlsx"（TAKUCHI_k シート）
  4. 用途地域コード表     : "*用途地域コード*.xlsx"        （数値コード→用途地域名）

■ 出力（realor-map-app 直下）
  - market_torihiki.csv : 直近1年の取引/成約事例（地区名を国土地理院APIでジオコード）
  - market_kouji.csv    : 地価公示の標準地（所在地を国土地理院APIでジオコード）
  - market/_geocache.json : ジオコード結果キャッシュ（コミット対象。再実行が高速化）

■ 使い方
  cd realor-map-app
  python market/build_market_data.py                       # 浜松市のみ
  python market/build_market_data.py --area wide            # 浜松＋近郊
  python market/build_market_data.py --src "D:/data/実勢価格データ・国土交通省データ"

■ データ出典・換算の根拠
  - 坪単価(円/坪) = 単価(円/㎡) × 3.305785         （1坪 = 400/121 ㎡ ≒ 3.305785㎡）
  - 用途地域コード: 国交省「国土交通省データ用途地域コード.xlsx」準拠
  - 市区町村コード→名称: 総務省「全国地方公共団体コード」（静岡県分を同梱）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

# ──────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
CACHE_PATH = HERE / "_geocache.json"

DEFAULT_SRC = Path(
    r"C:/Users/kamakei-t/Documents/claudecode/knowledge/documents/"
    r"実勢価格データ・国土交通省データ"
)

PREF = "静岡県"
SQM_PER_TSUBO = 400 / 121          # ≒ 3.305785 ㎡/坪
YEN_PER_MAN = 10_000

AREA_HAMAMATSU = {"22138": "浜松市中央区", "22139": "浜松市浜名区", "22140": "浜松市天竜区"}
AREA_WIDE_EXTRA = {
    "22211": "磐田市", "22221": "湖西市", "22216": "袋井市",
    "22213": "掛川市", "22461": "周智郡森町",
}
# 静岡県 市区町村コード→名称（総務省コード。地価公示CSVの住所復元に使用）
MUNI_CODE = {
    "22101": "静岡市葵区", "22102": "静岡市駿河区", "22103": "静岡市清水区",
    "22138": "浜松市中央区", "22139": "浜松市浜名区", "22140": "浜松市天竜区",
    "22203": "沼津市", "22205": "熱海市", "22206": "三島市", "22207": "富士宮市",
    "22208": "伊東市", "22209": "島田市", "22210": "富士市", "22211": "磐田市",
    "22212": "焼津市", "22213": "掛川市", "22214": "藤枝市", "22215": "御殿場市",
    "22216": "袋井市", "22219": "下田市", "22220": "裾野市", "22221": "湖西市",
    "22222": "伊豆市", "22223": "御前崎市", "22224": "菊川市", "22225": "伊豆の国市",
    "22226": "牧之原市", "22301": "賀茂郡東伊豆町", "22302": "賀茂郡河津町",
    "22304": "賀茂郡南伊豆町", "22305": "賀茂郡松崎町", "22306": "賀茂郡西伊豆町",
    "22325": "田方郡函南町", "22341": "駿東郡清水町", "22342": "駿東郡長泉町",
    "22344": "駿東郡小山町", "22424": "榛原郡吉田町", "22429": "榛原郡川根本町",
    "22461": "周智郡森町",
}

GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="

# 地価公示 生CSV（TAKUCHI_k）の列位置。ヘッダー付与後に assert で自己検証する。
KOUJI_COL = {
    "価格時点": 0,
    "県コード": 1,
    "市区町村コード": 2,
    "鑑定評価額": 18,
    "m2単価円": 19,            # 1㎡当たりの価格（＝公示価格）
    "相続税路線価": 23,
    "所在地番": 26,
    "住居表示": 27,
    "地積": 29,
    "前面道路方位": 39,
    "前面道路幅員": 41,
    "交通施設": 49,
    "交通距離m": 50,
    "用途地域コード": 53,
    "指定建蔽率": 54,
    "指定容積率": 55,
    "周辺利用状況": 38,
}
KOUJI_HEADER_CHECK = {  # 見出し名にこの語が含まれることを確認
    0: "価格時点", 18: "鑑定評価額", 19: "1㎡当たりの価格",
    23: "相続税路線価", 26: "所在地", 29: "地積",
    41: "道路幅員", 53: "用途地域", 54: "建ぺい率", 55: "容積率",
}


# ──────────────────────────────────────────────────────────────
# ジオコーディング（国土地理院・無料・キー不要）
# ──────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )


def gsi_geocode(query: str, cache: dict, pause: float = 0.4) -> dict | None:
    if query in cache:
        return cache[query]
    try:
        with urllib.request.urlopen(GSI_URL + urllib.parse.quote(query), timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  ! geocode error [{query}]: {e}", file=sys.stderr)
        return None  # ネットワークエラーはキャッシュせず、次回リトライ
    time.sleep(pause)

    if not data:
        cache[query] = None
        return None
    top = data[0]
    lon, lat = top["geometry"]["coordinates"]
    matched = top.get("properties", {}).get("title", "")
    tail = query.replace(PREF, "")
    level = "exact" if tail and tail in matched else "approx"
    rec = {"lat": round(lat, 7), "lon": round(lon, 7), "matched": matched, "level": level}
    cache[query] = rec
    return rec


def _clean_addr_for_geocode(muni: str, raw_local: str) -> str:
    """地番・号・外字を落として大字＋丁目程度に丸める。"""
    s = unicodedata.normalize("NFKC", str(raw_local or "")).strip()
    s = s.split("字")[0]                       # 「○○町字△△123」→「○○町」
    s = re.sub(r"\d+番.*$", "", s)             # 「123番4外」除去
    s = re.sub(r"\d+[-−]\d+([-−]\d+)?$", "", s)  # 「5-6」「1-2-3」除去
    s = re.sub(r"[，、]\s*", "", s)
    s = s.strip(" 　-−")
    return f"{PREF}{muni}{s}"


# ──────────────────────────────────────────────────────────────
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "").str.strip().replace({"": None}),
        errors="coerce",
    )


def _find_file(src: Path, *patterns: str) -> Path | None:
    for pat in patterns:
        hits = sorted(src.glob(pat)) + sorted(src.glob("**/" + pat))
        if hits:
            return hits[-1]
    return None


# ──────────────────────────────────────────────────────────────
# 1) 不動産取引価格情報
# ──────────────────────────────────────────────────────────────
def build_torihiki(src: Path, munis: dict[str, str], cache: dict) -> pd.DataFrame:
    path = _find_file(src, "*Prefecture*_*.csv", "*取引価格*.csv")
    if not path:
        raise FileNotFoundError("取引価格情報CSVが見つかりません（*Prefecture*_*.csv）")
    print(f"[torihiki] read {path.name}")
    for enc in ("cp932", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [c.strip() for c in df.columns]
    df = df[df["市区町村コード"].isin(munis)].copy()
    # 土地の坪単価が取れる「宅地(土地)」のみ採用。「宅地(土地と建物)」は
    # 土地単価が分離できず全欠損になるため除外（相場・地図とも使わない）。
    df = df[df["種類"] == "宅地(土地)"].copy()

    df["面積m2"] = _num(df["面積（㎡）"])
    df["m2単価円"] = _num(df["取引価格（㎡単価）"])
    df["総額円"] = _num(df["取引価格（総額）"])
    # 坪単価: 元データの「坪単価」(円/坪) を優先、空なら ㎡単価 × 3.305785
    tsubo_src = _num(df["坪単価"])
    df["坪単価万円"] = (
        tsubo_src.where(tsubo_src.notna(), df["m2単価円"] * SQM_PER_TSUBO) / YEN_PER_MAN
    ).round(2)

    def _period_key(s: str) -> str:
        m = re.match(r"(\d{4})年第(\d)四半期", str(s))
        return f"{m.group(1)}Q{m.group(2)}" if m else ""

    df["時期"] = df["取引時期"].map(_period_key)

    keys = df[["市区町村名", "地区名"]].dropna().drop_duplicates().sort_values(["市区町村名", "地区名"])
    print(f"[torihiki] geocode {len(keys)} districts ...")
    ll: dict[tuple[str, str], dict] = {}
    for i, (_, row) in enumerate(keys.iterrows(), 1):
        rec = gsi_geocode(f"{PREF}{row['市区町村名']}{row['地区名']}", cache)
        ll[(row["市区町村名"], row["地区名"])] = rec
        if i % 25 == 0:
            print(f"    {i}/{len(keys)}"); _save_cache(cache)
    _save_cache(cache)

    df["lat"] = df.apply(lambda r: (ll.get((r["市区町村名"], r["地区名"])) or {}).get("lat"), axis=1)
    df["lon"] = df.apply(lambda r: (ll.get((r["市区町村名"], r["地区名"])) or {}).get("lon"), axis=1)
    df["位置精度"] = df.apply(
        lambda r: (ll.get((r["市区町村名"], r["地区名"])) or {}).get("level", "none"), axis=1
    )
    df = df[df["lat"].notna()].copy()

    out = pd.DataFrame({
        "市区町村": df["市区町村名"], "地区名": df["地区名"],
        "lat": df["lat"], "lon": df["lon"], "位置精度": df["位置精度"],
        "種類": df["種類"], "時期": df["時期"], "取引時期": df["取引時期"],
        "面積m2": df["面積m2"].round(1), "坪単価万円": df["坪単価万円"],
        "m2単価円": df["m2単価円"], "総額円": df["総額円"],
        "地域": df["地域"], "用途地域": df["都市計画"],
        "建蔽率": _num(df["建ぺい率（％）"]), "容積率": _num(df["容積率（％）"]),
        "最寄駅": df["最寄駅：名称"], "駅距離": df["最寄駅：距離（分）"],
        "前面道路幅員m": _num(df["前面道路：幅員（ｍ）"]),
        "土地形状": df["土地の形状"], "今後の利用目的": df["今後の利用目的"],
    })
    return out.sort_values(["時期", "市区町村", "地区名"], ascending=[False, True, True]).reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
# 2) 地価公示 標準地（生 TAKUCHI_k CSV から）
# ──────────────────────────────────────────────────────────────
def _load_kouji_header(src: Path) -> list[str]:
    hp = _find_file(src, "*ファイル項目.xlsx")
    if hp:
        names = pd.read_excel(hp, header=None, dtype=str).iloc[0].tolist()
        if len(names) >= 1400:
            print(f"[kouji] header <- {hp.name}")
            return [str(x) for x in names]
    # 予備: 説明書 TAKUCHI_k シートから復元（親項目フィル）
    sp = _find_file(src, "*ファイル項目説明書.xlsx")
    if not sp:
        raise FileNotFoundError("列名定義（ファイル項目.xlsx / 説明書）が見つかりません")
    print(f"[kouji] header <- {sp.name}（復元）")
    spec = pd.read_excel(sp, sheet_name="TAKUCHI_k", header=None, dtype=str)
    parents = {}
    rows = {}
    for _, r in spec.iterrows():
        no = r[0]
        parts = [str(r[c]).strip() for c in (3, 4, 5, 6, 7, 8)
                 if c < spec.shape[1] and pd.notna(r[c]) and str(r[c]).strip() not in ("", "nan")]
        if str(no).strip().isdigit():
            rows[int(no)] = " ".join(parts)
    return [rows.get(i, f"col{i}") for i in range(1, max(rows) + 1)]


def _load_yoto_map(src: Path) -> dict[str, str]:
    yp = _find_file(src, "*用途地域コード*.xlsx", "*用途地域*コード*.xlsx")
    if not yp:
        print("[kouji] 用途地域コード表なし → コードのまま出力")
        return {}
    y = pd.read_excel(yp, dtype=str)
    ccol = next(c for c in y.columns if "コード" in c or "数値" in c)
    ncol = next(c for c in y.columns if "名" in c)
    m: dict[str, str] = {}
    for k, v in zip(y[ccol], y[ncol]):
        if pd.isna(k):
            continue
        key = str(k).strip()
        name = str(v).strip()
        m[key] = name
        if key.isdigit():           # "0"/"4" と "00"/"04" の両表記に対応
            m[str(int(key))] = name
            m[key.zfill(2)] = name
    return m


def build_kouji(src: Path, munis: dict[str, str], cache: dict) -> pd.DataFrame:
    path = _find_file(src, "*TAKUCHI_k*.csv", "*TAKUCHI*_k_*.csv")
    if not path:
        print("[kouji] TAKUCHI_k CSV が見つからないためスキップ")
        return pd.DataFrame()
    print(f"[kouji] read {path.name}")
    raw = pd.read_csv(path, encoding="cp932", header=None, dtype=str)
    header = _load_kouji_header(src)
    if len(header) != raw.shape[1]:
        print(f"[kouji] ⚠ 列数不一致 header={len(header)} csv={raw.shape[1]} → 位置ベースで続行")
    else:
        # 自己検証: 主要列の見出しに期待語が含まれるか
        for pos, kw in KOUJI_HEADER_CHECK.items():
            got = header[pos] if pos < len(header) else ""
            assert kw in got, f"列位置検証NG: col{pos} 期待『{kw}』 実際『{got}』"
        print("[kouji] 列位置の自己検証 OK")

    C = KOUJI_COL
    code = raw[C["県コード"]].str.zfill(2) + raw[C["市区町村コード"]].str.zfill(3)
    df = raw[code.isin(munis)].copy()
    df["_muni"] = code[code.isin(munis)].map(munis)
    print(f"[kouji] {len(df)} 標準地（対象市区町村）")

    yoto = _load_yoto_map(src)
    recs = []
    for i, (_, r) in enumerate(df.iterrows(), 1):
        local = r[C["住居表示"]]
        if pd.isna(local) or not str(local).strip():
            local = r[C["所在地番"]]
        q = _clean_addr_for_geocode(r["_muni"], local)
        g = gsi_geocode(q, cache)
        if not g:
            continue
        m2 = _num(pd.Series([r[C["m2単価円"]]])).iloc[0]
        ycode = str(r[C["用途地域コード"]]).strip()
        if ycode.isdigit():
            ycode = str(int(ycode))
        recs.append({
            "住所": f"{r['_muni']}{unicodedata.normalize('NFKC', str(local or '')).strip()}",
            "lat": g["lat"], "lon": g["lon"], "位置精度": g["level"],
            "価格時点年": r[C["価格時点"]],
            "公示m2単価円": m2,
            "坪単価万円": round(m2 * SQM_PER_TSUBO / YEN_PER_MAN, 1) if pd.notna(m2) else None,
            "相続税路線価": _num(pd.Series([r[C["相続税路線価"]]])).iloc[0],
            "地積m2": _num(pd.Series([r[C["地積"]]])).iloc[0],
            "前面道路幅員m": _num(pd.Series([r[C["前面道路幅員"]]])).iloc[0],
            "用途地域": yoto.get(ycode, ycode),
            "建蔽率": _num(pd.Series([r[C["指定建蔽率"]]])).iloc[0],
            "容積率": _num(pd.Series([r[C["指定容積率"]]])).iloc[0],
            "最寄交通施設": r[C["交通施設"]],
            "交通距離m": _num(pd.Series([r[C["交通距離m"]]])).iloc[0],
            "周辺利用状況": r[C["周辺利用状況"]],
        })
        if i % 25 == 0:
            print(f"    {i}/{len(df)}"); _save_cache(cache)
    _save_cache(cache)
    out = pd.DataFrame(recs)
    # 同一標準地が地価公示・地価調査の両方で登録される（共通地点）→ 住所で1本化
    if not out.empty:
        before = len(out)
        out = out.sort_values("公示m2単価円", ascending=False).drop_duplicates("住所", keep="first")
        print(f"[kouji] 共通地点の重複を統合: {before} → {len(out)}")
    return out.sort_values("住所").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--area", choices=["hamamatsu", "wide"], default="hamamatsu")
    args = ap.parse_args()
    if not args.src.exists():
        sys.exit(f"src が存在しません: {args.src}")

    munis = dict(AREA_HAMAMATSU)
    if args.area == "wide":
        munis.update(AREA_WIDE_EXTRA)
    cache = _load_cache()

    tori = build_torihiki(args.src, munis, cache)
    p = APP_DIR / "market_torihiki.csv"
    tori.to_csv(p, index=False, encoding="utf-8-sig")
    n_land = int((tori["種類"] == "宅地(土地)").sum())
    print(f"✅ {p.name}  {len(tori)} 行（うち宅地・土地 {n_land}）")

    kouji = build_kouji(args.src, munis, cache)
    if not kouji.empty:
        p = APP_DIR / "market_kouji.csv"
        kouji.to_csv(p, index=False, encoding="utf-8-sig")
        ex = int((kouji["位置精度"] == "exact").sum())
        print(f"✅ {p.name}  {len(kouji)} 行（座標exact {ex} / approx {len(kouji)-ex}）")
        print(f"   公示坪単価 中央値 {kouji['坪単価万円'].median():.1f} 万円 / "
              f"範囲 {kouji['坪単価万円'].min():.1f}–{kouji['坪単価万円'].max():.1f}")

    _save_cache(cache)
    print("done.")


if __name__ == "__main__":
    main()
