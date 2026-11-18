"""規則檔的讀寫、驗證，以及規則 → 中文句子 / Gmail 搜尋語法。"""

import json
import os
import sys

from .config import ACTION_KEYS, CATEGORY_TEXT, CONFIG_DIR, FIELD_BY_KEY, RULES_FILE


def load_rules():
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_rules(rules):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = RULES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, RULES_FILE)


def describe_filter(node, top=True):
    if "and" in node:
        s = "，而且".join(describe_filter(n, False) for n in node["and"])
        return s if top else f"（{s}）"
    if "or" in node:
        parts = [describe_filter(n, False) for n in node["or"]]
        # 同一個欄位的 or：寄件者是 a 或 b
        keys = {next(iter(n)) for n in node["or"]}
        if len(keys) == 1 and next(iter(keys)) in FIELD_BY_KEY:
            key = next(iter(keys))
            vals = "或".join(f"「{n[key]}」" for n in node["or"])
            return f"{FIELD_BY_KEY[key][2]}{vals}"
        s = "，或".join(parts)
        return s if top else f"（{s}）"
    if "not" in node:
        return f"不是{describe_filter(node['not'], False)}"
    key = next(iter(node))
    if key in FIELD_BY_KEY:
        return f"{FIELD_BY_KEY[key][2]}「{node[key]}」"
    return f"{key}: {node[key]}"


def describe_actions(actions):
    parts = []
    if actions.get("delete"):
        parts.append("移到垃圾桶")
    for label in actions.get("labels", []):
        parts.append(f"貼上標籤「{label}」")
    if actions.get("archive"):
        parts.append("略過收件匣")
    if actions.get("markRead"):
        parts.append("標示為已讀")
    if actions.get("star"):
        parts.append("加上星號")
    if actions.get("markImportant") is True:
        parts.append("標示為重要")
    if actions.get("markImportant") is False:
        parts.append("不標示為重要")
    if actions.get("category"):
        parts.append(f"歸類到「{CATEGORY_TEXT.get(actions['category'], actions['category'])}」")
    return "、".join(parts) or "（沒有動作）"


def describe_rule(rule):
    return f"如果{describe_filter(rule['filter'])} → {describe_actions(rule['actions'])}"


def _term(value):
    value = value.replace('"', "")
    return f'"{value}"' if any(c.isspace() for c in value) else value


def to_query(node):
    if "and" in node:
        return "(" + " ".join(to_query(n) for n in node["and"]) + ")"
    if "or" in node:
        return "{" + " ".join(to_query(n) for n in node["or"]) + "}"
    if "not" in node:
        return "-" + to_query(node["not"])
    if "query" in node:
        return f"({node['query']})"
    key = next(iter(node))
    if key == "has":
        return _term(node[key])
    return f"{key}:{_term(node[key])}"


def normalize_label(name):
    parts = [p.strip() for p in name.split("/") if p.strip()]
    return "/".join(parts)


def validate_filter(node, path="filter"):
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError(f"{path} 必須是只有一個 key 的物件")
    key, val = next(iter(node.items()))
    if key in ("and", "or"):
        if not isinstance(val, list) or len(val) < 2:
            raise ValueError(f"{path}.{key} 至少要有兩個條件")
        for i, n in enumerate(val):
            validate_filter(n, f"{path}.{key}[{i}]")
    elif key == "not":
        validate_filter(val, f"{path}.not")
    elif key in FIELD_BY_KEY:
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{path}.{key} 必須是非空字串")
    else:
        raise ValueError(f"{path} 不支援的欄位 {key}（可用：{', '.join(FIELD_BY_KEY)}、and、or、not）")


def validate_rule(rule):
    if not isinstance(rule, dict):
        raise ValueError("規則必須是 JSON 物件")
    if not str(rule.get("name", "")).strip():
        raise ValueError("缺少 name")
    validate_filter(rule.get("filter"))
    actions = rule.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise ValueError("actions 至少要有一個動作")
    unknown = set(actions) - ACTION_KEYS
    if unknown:
        raise ValueError(f"不支援的動作：{', '.join(sorted(unknown))}")
    if actions.get("delete") and len(actions) > 1:
        raise ValueError("delete 不能和其他動作一起使用")
    if "labels" in actions:
        labels = actions["labels"]
        if not isinstance(labels, list) or not labels or not all(isinstance(l, str) and l.strip() for l in labels):
            raise ValueError("labels 必須是非空的字串陣列")
        actions["labels"] = [normalize_label(l) for l in labels]
    if "category" in actions and actions["category"] not in CATEGORY_TEXT:
        raise ValueError(f"category 必須是 {', '.join(CATEGORY_TEXT)} 其中之一")
    if "markImportant" in actions and not isinstance(actions["markImportant"], bool):
        raise ValueError("markImportant 必須是 true 或 false")
    for k in ("archive", "markRead", "star", "delete"):
        if k in actions and actions[k] is not True:
            raise ValueError(f"{k} 只能是 true（不需要就不要放）")
    return {"name": rule["name"].strip(), "filter": rule["filter"], "actions": actions}


def parse_rule_arg(args):
    if not args:
        raise ValueError("請提供規則 JSON")
    raw = args[0]
    if raw == "-":
        raw = sys.stdin.read()
    try:
        return validate_rule(json.loads(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 格式錯誤：{e}")
