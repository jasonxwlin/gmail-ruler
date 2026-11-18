"""
gmr — gmailctl 的簡易包裝

用固定的問答建立 Gmail 篩選規則（存成 gmailctl 格式），同步到 Gmail，
並且可以把規則套用到信箱裡既有的信件（gmailctl 本身不支援這件事）。

用法：
  python3 gmr.py            互動選單
  python3 gmr.py new        問答建立新規則
  python3 gmr.py list       列出規則
  python3 gmr.py remove N   刪除第 N 條規則
  python3 gmr.py diff       看本機規則和 Gmail 篩選器的差異
  python3 gmr.py sync       同步到 Gmail（gmailctl apply）
  python3 gmr.py backfill [N ...]  把規則套用到既有信件（預設全部規則）

非互動指令（給腳本或 Claude 呼叫）：
  python3 gmr.py preview '<rule json>'   驗證規則，印出中文描述與搜尋語法（不儲存）
  python3 gmr.py add '<rule json>'       驗證並新增規則
  python3 gmr.py list --json             以 JSON 輸出所有規則
  python3 gmr.py remove N --yes          不經確認直接刪除第 N 條
  python3 gmr.py backfill [N ...] --dry-run   只預覽會影響幾封信
  python3 gmr.py backfill [N ...] --yes       不經確認直接套用
  python3 gmr.py sync --yes              不經確認直接 gmailctl apply
"""

import sys

from .commands import cmd_add, cmd_backfill, cmd_diff, cmd_list, cmd_preview, cmd_remove, cmd_sync
from .prompts import ask, choose, split_values
from .wizard import cmd_new


def menu():
    while True:
        print()
        choice = choose("=== Gmail 規則小幫手 ===", [
            ("new", "建立新規則"),
            ("list", "檢視現有規則"),
            ("remove", "刪除規則"),
            ("sync", "同步規則到 Gmail（之後的新信自動套用）"),
            ("backfill", "把規則套用到既有信件"),
            ("quit", "離開"),
        ])
        print()
        if choice == "quit":
            return
        if choice == "backfill":
            cmd_list()
            raw = ask("要套用哪幾條？直接按 Enter 代表全部", required=False)
            nums = [int(x) for x in split_values(raw)] if raw else []
            cmd_backfill([str(n) for n in nums])
        elif choice == "remove":
            cmd_remove([])
        else:
            COMMANDS[choice]()


COMMANDS = {
    "new": cmd_new,
    "list": cmd_list,
    "diff": cmd_diff,
    "sync": cmd_sync,
}


def main(argv):
    if not argv:
        return menu()
    cmd = argv[0]
    flags = {a for a in argv[1:] if a.startswith("--")}
    args = [a for a in argv[1:] if not a.startswith("--")]
    assume_yes = "--yes" in flags
    try:
        if cmd == "new":
            return cmd_new()
        if cmd == "list":
            return cmd_list(as_json="--json" in flags)
        if cmd == "diff":
            return cmd_diff()
        if cmd == "sync":
            return cmd_sync(assume_yes=assume_yes)
        if cmd == "remove":
            return cmd_remove(args, assume_yes=assume_yes)
        if cmd == "backfill":
            return cmd_backfill(args, assume_yes=assume_yes, dry_run="--dry-run" in flags)
        if cmd == "preview":
            return cmd_preview(args)
        if cmd == "add":
            return cmd_add(args)
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(2)
    print(__doc__)
