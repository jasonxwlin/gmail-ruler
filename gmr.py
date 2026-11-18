#!/usr/bin/env python3
"""gmr — gmailctl 的簡易包裝。用法請看 `python3 gmr.py help` 或 README。"""

import sys

from gmailruler.cli import main

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n已中斷。")
