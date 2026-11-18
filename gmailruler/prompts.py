"""互動輸入的小工具。"""

import sys


def ask(prompt, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            ans = input(f"{prompt}{suffix}：").strip()
        except EOFError:
            print()
            sys.exit(1)
        if not ans and default is not None:
            return default
        if ans or not required:
            return ans
        print("  這一題必填喔。")


def yes(prompt, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        ans = ask(f"{prompt} ({d})", required=False).lower()
        if not ans:
            return default
        if ans in ("y", "yes", "是", "好"):
            return True
        if ans in ("n", "no", "否", "不"):
            return False


def choose(prompt, options, multi=False):
    """options: [(key, text)]。multi=True 時可輸入 1,3 多選。回傳 key 或 key 的 list。"""
    print(prompt)
    for i, (_, text) in enumerate(options, 1):
        print(f"  {i}. {text}")
    hint = "（可多選，用逗號分開，例如 1,3）" if multi else ""
    while True:
        raw = ask(f"請輸入編號{hint}")
        try:
            nums = [int(x) for x in raw.replace("，", ",").split(",") if x.strip()]
        except ValueError:
            nums = []
        if nums and all(1 <= n <= len(options) for n in nums) and (multi or len(nums) == 1):
            keys = list(dict.fromkeys(options[n - 1][0] for n in nums))
            return keys if multi else keys[0]
        print("  編號不正確，請再輸入一次。")


def split_values(raw):
    """「a, b、c」→ ['a', 'b', 'c']"""
    for sep in ("，", "、", ";", "；"):
        raw = raw.replace(sep, ",")
    return [v.strip() for v in raw.split(",") if v.strip()]
