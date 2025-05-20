import os
import urllib.parse
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --------------------------------------------------
# .env から OAuth2 情報とスプレッドシート ID／シート名を読み込む
# --------------------------------------------------
load_dotenv()
CLIENT_ID      = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET  = os.getenv("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN  = os.getenv("GOOGLE_REFRESH_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME     = os.getenv("SHEET_NAME", "Sheet1")

# --------------------------------------------------
# Sheets API サービス取得
# --------------------------------------------------
def get_sheets_service():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds).spreadsheets()

# --------------------------------------------------
# シートからデータ読み込み（ヘッダー行→データ行の二段階取得）
# --------------------------------------------------
def load_data_from_sheet():
    svc = get_sheets_service()

    # 1) ヘッダー行だけ取得（1行目）
    header_res = svc.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!1:1"
    ).execute()
    headers = header_res.get("values", [[]])[0]
    if not headers:
        return []

    # 列数に応じて「終了列」を計算（A→B→…→Z→AA→AB …）
    # ※ 26 列以内なら単純に A-Z の範囲で対応できます
    last_col = chr(ord('A') + len(headers) - 1)

    # 2) データ行を A2:最後列 で取得
    data_res = svc.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:{last_col}"
    ).execute()
    rows = data_res.get("values", [])

    data = []
    for r in rows:
        # 足りないセルは空文字で埋める
        r += [""] * (len(headers) - len(r))
        row = dict(zip(headers, r))
        # 型変換
        row["acute_level"] = int(row.get("acute_level") or 0)
        row["priority"]    = int(row.get("priority")    or 0)
        row["focus"]       = str(row.get("focus","")).lower() in ("true","1")
        row["group"]       = [g.strip() for g in row.get("group","").split(",") if g.strip()]
        data.append(row)
    return data

# --------------------------------------------------
# シートへデータ書き込み（管理者画面用）
# --------------------------------------------------
def save_data_to_sheet(data):
    svc = get_sheets_service()
    headers = [
        "name","address","acute_level","features","points",
        "website_main","website_internal","website_extra",
        "focus","priority","group"
    ]
    values = [headers]
    for h in data:
        values.append([
            h.get("name",""),
            h.get("address",""),
            str(h.get("acute_level","")),
            h.get("features",""),
            h.get("points",""),
            h.get("website_main",""),
            h.get("website_internal",""),
            h.get("website_extra",""),
            "TRUE" if h.get("focus",False) else "FALSE",
            str(h.get("priority","")),
            ",".join(h.get("group",[]))
        ])
    svc.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

# --------------------------------------------------
# 共通ユーティリティ
# --------------------------------------------------
def stars_display(level: int) -> str:
    return "★" * level + "☆" * (5 - level)

def generate_gmap_link(from_address: str, to_address: str) -> str:
    if not from_address or not to_address:
        return ""
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={urllib.parse.quote(from_address)}"
        f"&destination={urllib.parse.quote(to_address)}"
    )

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------
st.set_page_config(page_title="🏥 提案パッケージ")
st.title("🏥 提案パッケージ")

if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

mode = st.sidebar.radio("モードを選択", ["ユーザー画面", "管理者画面"])
data = load_data_from_sheet()

if mode == "ユーザー画面":
    st.subheader("病院検索")
    name_input     = st.text_input("病院名を入力してください")
    seeker_address = st.text_input("求職者の住所を入力（任意）")
    if name_input:
        found = next((h for h in data if name_input in h["name"]), None)
        if found:
            prefix = "◎" if found.get("focus") else ""
            st.markdown(f"### 🏥 {prefix}[{found['name']}]({found['website_main']})")
            st.write(f"📍 **住所**: {found['address']}")
            if seeker_address:
                st.markdown(f"🛆 [Googleマップで経路を表示]({generate_gmap_link(seeker_address, found['address'])})")
            st.write(f"🔡️ **急性期度合い**: {stars_display(found['acute_level'])}")
            st.write(f"💡 **特徴**: {found['features']}")
            st.write(f"🌟 **提案ポイント**: {found['points']}")
            st.write(f"🔗 **DF: [リンク]({found['website_internal']})**")
            if found.get("website_extra"):
                st.write(f"🔗 **その他リンク: [リンク]({found['website_extra']})**")

            st.markdown("---")
            st.subheader("📌 提案すべき病院")
            sort_opt = st.selectbox(
                "並び替え方法",
                ["優先順位順（デフォルト）", "急性期度合高い順", "急性期度合い低い順"],
                index=0, key="sort_select"
            )
            related = [
                h for h in data
                if h["name"] in found.get("group", []) and h["name"] != found["name"]
            ]
            if sort_opt == "急性期度合高い順":
                related.sort(key=lambda x: x["acute_level"], reverse=True)
            elif sort_opt == "急性期度合い低い順":
                related.sort(key=lambda x: x["acute_level"])
            for h in related:
                pre = "◎" if h.get("focus") else ""
                with st.expander(f"🏥 {pre}{h['name']}"):
                    st.write(f"🔗 **HP**: [リンク]({h['website_main']})")
                    st.write(f"📍 **住所**: {h['address']}")
                    if seeker_address:
                        st.markdown(f"🛆 [Googleマップで経路を表示]({generate_gmap_link(seeker_address, h['address'])})")
                    st.write(f"🔡️ **急性期度合い**: {stars_display(h['acute_level'])}")
                    st.write(f"💡 **特徴**: {h['features']}")
                    st.write(f"🌟 **提案ポイント**: {h['points']}")
                    st.write(f"🔗 **DF: [リンク]({h['website_internal']})**")
                    if h.get("website_extra"):
                        st.write(f"🔗 **その他リンク: [リンク]({h['website_extra']})**")

elif mode == "管理者画面":
    if not st.session_state.admin_logged_in:
        st.subheader("🔒 管理者ログイン")
        pw = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン"):
            if pw == "levlevle":
                st.session_state.admin_logged_in = True
                st.success("ログインに成功しました")
            else:
                st.error("パスワードが間違っています")
        st.stop()

    st.subheader("病院情報を編集")
    names     = [h["name"] for h in data]
    selected  = st.selectbox("病院を選択", names)
    target    = next(h for h in data if h["name"] == selected)

    new_name     = st.text_input("病院名", value=target["name"])
    new_address  = st.text_input("住所", value=target["address"])
    new_acute    = st.slider("急性期度合い（1〜5）", 1, 5, value=target["acute_level"])
    new_features = st.text_area("特徴", value=target["features"])
    new_points   = st.text_area("提案ポイント", value=target["points"])
    new_web_main = st.text_input("1. 病院HPリンク", value=target.get("website_main",""))
    new_web_int  = st.text_input("2. 社内DBリンク", value=target.get("website_internal",""))
    new_web_ext  = st.text_input("3. その他リンク", value=target.get("website_extra",""))
    new_focus    = st.checkbox("重点提案└", value=target.get("focus", False))
    new_priority = st.number_input("表示順位（1が最優先）", 1, 100, value=target.get("priority",10))
    other_names  = [n for n in names if n != new_name]
    default_grp  = [g for g in target.get("group", []) if g != new_name]
    grp_sel      = st.multiselect("グループ登録（複数病院を相互に関連付け）", options=other_names, default=default_grp)

    if st.button("保存"):
        new_group = list(set(grp_sel + [new_name]))
        for h in data:
            if h["name"] in new_group:
                h["group"] = new_group.copy()
            elif new_name in h.get("group", []):
                h["group"] = [h["name"]]
        target.update({
            "name":             new_name,
            "address":          new_address,
            "acute_level":      new_acute,
            "features":         new_features,
            "points":           new_points,
            "website_main":     new_web_main,
            "website_internal": new_web_int,
            "website_extra":    new_web_ext,
            "focus":            new_focus,
            "priority":         new_priority,
            "group":            new_group
        })
        save_data_to_sheet(data)
        st.success("シートに保存されました")
