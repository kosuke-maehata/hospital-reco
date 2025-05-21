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
GROUP_SHEET    = os.getenv("GROUP_SHEET_NAME", "Groups")

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
# 病院データの読み書き
# --------------------------------------------------
def load_data_from_sheet():
    svc = get_sheets_service()
    header_res = svc.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!1:1").execute()
    headers = header_res.get("values", [[]])[0]
    if not headers:
        return []
    last_col = chr(ord('A') + len(headers) - 1)
    data_res = svc.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A2:{last_col}").execute()
    rows = data_res.get("values", [])
    data = []
    for r in rows:
        r += [""] * (len(headers) - len(r))
        row = dict(zip(headers, r))
        row["acute_level"] = int(row.get("acute_level") or 0)
        row["priority"]    = int(row.get("priority") or 0)
        row["focus"]       = str(row.get("focus","")) in ("true", "1", "TRUE")
        data.append(row)
    return data

def save_data_to_sheet(data):
    svc = get_sheets_service()
    headers = ["name","address","acute_level","features","points","website_main","website_internal","website_extra","focus","priority"]
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
            str(h.get("priority",""))
        ])
    svc.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

# --------------------------------------------------
# グループデータの読み書き
# --------------------------------------------------
def load_group_data():
    svc = get_sheets_service()
    res = svc.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{GROUP_SHEET}!A2:B").execute()
    rows = res.get("values", [])
    groups = {}
    for r in rows:
        if len(r) >= 2:
            group_name = r[0]
            hospitals = [h.strip() for h in r[1].split(",") if h.strip()]
            groups[group_name] = hospitals
    return groups

def save_group_data(groups):
    svc = get_sheets_service()
    values = [["group_name", "hospitals"]]
    for g, hs in groups.items():
        values.append([g, ",".join(hs)])
    svc.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{GROUP_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

# --------------------------------------------------
# 共通関数
# --------------------------------------------------
def stars_display(level):
    return "★" * level + "☆" * (5 - level)

def generate_gmap_link(from_address, to_address):
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
groups = load_group_data()

if mode == "ユーザー画面":
    st.subheader("病院検索")
    name_input = st.selectbox("病院名を選択してください", [h["name"] for h in data])
    seeker_address = st.text_input("求職者の住所を入力（任意）")
    if name_input:
        found = next(h for h in data if h["name"] == name_input)
        prefix = "◎" if found.get("focus") else ""
        st.markdown(f"### 🏥 {prefix}[{found['name']}]({found['website_main']})")
        st.write(f"📍 **住所**: {found['address']}")
        if seeker_address:
            st.markdown(f"🗖 [Googleマップで経路を表示]({generate_gmap_link(seeker_address, found['address'])})")
        st.write(f"🔡️ **急性期度合い**: {stars_display(found['acute_level'])}")
        st.write(f"💡 **特徴**: {found['features']}")
        st.write(f"🌟 **提案ポイント**: {found['points']}")
        st.write(f"🔗 **DF: [リンク]({found['website_internal']})**")
        if found.get("website_extra"):
            st.write(f"🔗 **その他リンク: [リンク]({found['website_extra']})**")
        st.markdown("---")
        st.subheader("📌 グループ選択と関連病院の表示")
        related_groups = [g for g, hs in groups.items() if found['name'] in hs]
        if not related_groups:
            st.info("この病院はどのグループにも所属していません。")
        else:
            selected_group = st.selectbox("表示するグループを選択", related_groups)
            related_names = [h for h in groups[selected_group] if h != found['name']]
            related = [h for h in data if h['name'] in related_names]
            if not related:
                st.info("関連病院が存在しません。")
            else:
                for h in related:
                    with st.expander(f"🏥 {'◎' if h.get('focus') else ''}{h['name']}"):
                        st.write(f"🔗 **HP**: [リンク]({h['website_main']})")
                        st.write(f"📍 **住所**: {h['address']}")
                        if seeker_address:
                            st.markdown(f"🗖 [Googleマップで経路を表示]({generate_gmap_link(seeker_address, h['address'])})")
                        st.write(f"🔡️ **急性期度合い**: {stars_display(h['acute_level'])}")
                        st.write(f"💡 **特徴**: {h['features']}")
                        st.write(f"🌟 **提案ポイント**: {h['points']}")
                        st.write(f"🔗 **DF: [リンク]({h['website_internal']})**")
                        if h.get('website_extra'):
                            st.write(f"🔗 **その他リンク: [リンク]({h['website_extra']})**")

elif mode == "管理者画面":
    # ログイン処理
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

    # 病院情報編集
    st.subheader("病院情報を編集")
    selected = st.selectbox("病院を選択", [h['name'] for h in data])
    target = next(h for h in data if h['name'] == selected)
    target['name'] = st.text_input("病院名", value=target['name'])
    target['address'] = st.text_input("住所", value=target['address'])
    target['acute_level'] = st.slider("急性期度合い（1〜5）", 1, 5, value=target['acute_level'])
    target['features'] = st.text_area("特徴", value=target['features'])
    target['points'] = st.text_area("提案ポイント", value=target['points'])
    target['website_main'] = st.text_input("1. 病院HPリンク", value=target.get('website_main',''))
    target['website_internal'] = st.text_input("2. 社内DBリンク", value=target.get('website_internal',''))
    target['website_extra'] = st.text_input("3. その他リンク", value=target.get('website_extra',''))
    target['focus'] = st.checkbox("重点提案", value=target.get('focus',False))
    target['priority'] = st.number_input("表示順位（1が最優先）", 1, 100, value=target.get('priority',10))

    # グループ設定（病院→グループ）
    st.markdown("---")
    st.subheader("グループ設定（病院→グループ）")
    current_groups = [g for g, hs in groups.items() if target['name'] in hs]
    updated_groups = st.multiselect("所属するグループを選択・追加", list(groups.keys()), default=current_groups)
    new_group_name = st.text_input("新しいグループ名を追加（任意）")
    if new_group_name and new_group_name not in groups:
        groups[new_group_name] = []
        updated_groups.append(new_group_name)
    # 反映処理
    for g in list(groups.keys()):
        if target['name'] in groups[g] and g not in updated_groups:
            groups[g].remove(target['name'])
        elif target['name'] not in groups[g] and g in updated_groups:
            groups[g].append(target['name'])

    if st.button("病院情報とグループ情報を保存"):
        save_data_to_sheet(data)
        save_group_data(groups)
        st.success("情報を保存しました")

    # グループ管理（グループ→病院）
    st.markdown("---")
    st.subheader("グループ管理（グループ→所属病院）")
    group_sel = st.selectbox("グループを選択", [""] + list(groups.keys()))
    if group_sel:
        hosps = groups.get(group_sel, [])
        updated_hosps = st.multiselect("所属病院を選択・追加・削除", [h['name'] for h in data], default=hosps)
        if st.button("グループを更新"):
            groups[group_sel] = updated_hosps
            save_group_data(groups)
            st.success("グループを更新しました")
        if st.button("このグループを削除"):
            del groups[group_sel]
            save_group_data(groups)
            st.success("グループを削除しました")
