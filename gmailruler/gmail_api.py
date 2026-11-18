"""Gmail API：授權、標籤、搜尋（套用到既有信件用）。"""

import os
import sys

from .config import BACKFILL_SCOPES, BACKFILL_TOKEN_FILE, CATEGORY_LABEL_IDS, CREDENTIALS_FILE


def gmail_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("缺少套件，請先執行：pip3 install -r requirements.txt")
        sys.exit(1)

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"找不到 {CREDENTIALS_FILE}，請照 README 建立 OAuth 用戶端並下載 credentials.json。")
        sys.exit(1)

    creds = None
    if os.path.exists(BACKFILL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(BACKFILL_TOKEN_FILE, BACKFILL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("第一次使用需要授權修改 Gmail 信件（會打開瀏覽器）。")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, BACKFILL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(BACKFILL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        os.chmod(BACKFILL_TOKEN_FILE, 0o600)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def ensure_labels(service, names):
    """確保標籤存在（含巢狀標籤的上層），回傳 {名稱: label id}。"""
    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    by_name = {l["name"]: l["id"] for l in existing}
    for name in names:
        parts = name.split("/")
        for i in range(1, len(parts) + 1):
            path = "/".join(parts[:i])
            if path not in by_name:
                created = service.users().labels().create(userId="me", body={
                    "name": path,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                }).execute()
                by_name[path] = created["id"]
                print(f"  建立標籤「{path}」")
    return {n: by_name[n] for n in names}


def actions_to_modify(service, actions):
    """把 gmailctl 動作轉成 Gmail API 的 add/remove label id。"""
    add, remove = [], []
    if actions.get("delete"):
        return ["TRASH"], []
    if actions.get("labels"):
        add += list(ensure_labels(service, actions["labels"]).values())
    if actions.get("archive"):
        remove.append("INBOX")
    if actions.get("markRead"):
        remove.append("UNREAD")
    if actions.get("star"):
        add.append("STARRED")
    if actions.get("markImportant") is True:
        add.append("IMPORTANT")
    if actions.get("markImportant") is False:
        remove.append("IMPORTANT")
    if actions.get("category"):
        target = CATEGORY_LABEL_IDS[actions["category"]]
        add.append(target)
        remove += [c for c in CATEGORY_LABEL_IDS.values() if c != target]
    return add, remove


def search_ids(service, query):
    ids, token = [], None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=500, pageToken=token).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            return ids
