"""不需要問答的指令：列出、刪除、diff、同步、套用到既有信件、preview、add。"""

import json
import os
import shutil
import subprocess
import sys

from .config import CONFIG_DIR
from .gmail_api import actions_to_modify, ensure_labels, gmail_service, search_ids
from .prompts import ask, yes
from .rules import describe_rule, load_rules, parse_rule_arg, save_rules, to_query


def cmd_list(as_json=False):
    rules = load_rules()
    if as_json:
        out = [dict(r, number=i, description=describe_rule(r), query=to_query(r["filter"]))
               for i, r in enumerate(rules, 1)]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    if not rules:
        print("還沒有任何規則，用 `python3 gmr.py new` 新增。")
        return
    for i, r in enumerate(rules, 1):
        print(f"{i}. {r.get('name', '')}")
        print(f"   {describe_rule(r)}")
        print(f"   搜尋語法：{to_query(r['filter'])}")


def cmd_remove(args, assume_yes=False):
    rules = load_rules()
    if not rules:
        print("沒有規則可以刪除。")
        return
    if args:
        n = int(args[0])
    else:
        cmd_list()
        n = int(ask("要刪除第幾條？"))
    if not 1 <= n <= len(rules):
        print("沒有這一條。")
        return
    rule = rules[n - 1]
    print(describe_rule(rule))
    if assume_yes or yes("確定刪除這條規則？（只會移除規則，不會動到信件）", default=False):
        rules.pop(n - 1)
        save_rules(rules)
        print("已刪除。記得執行 sync 讓 Gmail 上的篩選器也一起移除。")


def gmailctl(*args):
    exe = shutil.which("gmailctl")
    if not exe:
        print("找不到 gmailctl，請先安裝：brew install gmailctl")
        sys.exit(1)
    return subprocess.call([exe, "--config", CONFIG_DIR, *args])


def cmd_diff():
    gmailctl("diff")


def cmd_sync(assume_yes=False):
    if not os.path.exists(os.path.join(CONFIG_DIR, "token.json")):
        print("gmailctl 還沒授權，請先執行：gmailctl --config gmailctl init")
        return
    labels = sorted({l for r in load_rules() for l in r["actions"].get("labels", [])})
    if labels:
        # gmailctl 只會引用既有標籤，所以先把缺的標籤建好
        service = gmail_service()
        ensure_labels(service, labels)
    gmailctl("apply", *(["--yes"] if assume_yes else []))


def backfill(numbers=None, assume_yes=False, dry_run=False):
    rules = load_rules()
    if not rules:
        print("還沒有任何規則。")
        return
    numbers = numbers or list(range(1, len(rules) + 1))
    service = gmail_service()

    plan = []
    print("\n=== 套用到既有信件：預覽 ===")
    for n in numbers:
        rule = rules[n - 1]
        query = to_query(rule["filter"])
        ids = search_ids(service, query)
        plan.append((n, rule, ids))
        print(f"{n}. {describe_rule(rule)}")
        print(f"   搜尋語法：{query} → 符合 {len(ids)} 封")
        if rule["actions"].get("forward"):
            print("   （轉寄動作不會套用到舊信）")

    total = sum(len(ids) for _, _, ids in plan)
    if total == 0:
        print("沒有符合的既有信件。")
        return
    if dry_run:
        print(f"\n（預覽模式）共 {total} 封會受影響，沒有做任何修改。")
        return
    deleting = sum(len(ids) for _, r, ids in plan if r["actions"].get("delete"))
    if deleting:
        print(f"\n⚠ 其中 {deleting} 封會被移到垃圾桶（30 天內可以救回）。")
    if not assume_yes and not yes(f"\n確定要處理這 {total} 封信嗎？", default=False):
        print("已取消。")
        return

    for n, rule, ids in plan:
        if not ids:
            continue
        add, remove = actions_to_modify(service, rule["actions"])
        if not add and not remove:
            continue
        for i in range(0, len(ids), 1000):  # batchModify 一次最多 1000 封
            body = {"ids": ids[i:i + 1000]}
            if add:
                body["addLabelIds"] = add
            if remove:
                body["removeLabelIds"] = remove
            service.users().messages().batchModify(userId="me", body=body).execute()
        print(f"  第 {n} 條規則：已處理 {len(ids)} 封")
    print("完成。")


def cmd_backfill(args, assume_yes=False, dry_run=False):
    rules = load_rules()
    nums = []
    for a in args:
        n = int(a)
        if not 1 <= n <= len(rules):
            print(f"沒有第 {n} 條規則。")
            return
        nums.append(n)
    backfill(nums or None, assume_yes=assume_yes, dry_run=dry_run)


def cmd_preview(args):
    rule = parse_rule_arg(args)
    print(describe_rule(rule))
    print(f"搜尋語法：{to_query(rule['filter'])}")


def cmd_add(args):
    rule = parse_rule_arg(args)
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    print(f"已新增第 {len(rules)} 條規則：{describe_rule(rule)}")
    print(f"搜尋語法：{to_query(rule['filter'])}")
