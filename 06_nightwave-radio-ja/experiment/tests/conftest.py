"""NIGHTWAVE-JA テスト共通設定。

src/nightwave_ja を import パスに載せ、テスト全体を既定でモック運転にする
（モデルのロードなしで API 形状と決定的ロジックを検証する）。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.normpath(os.path.join(_HERE, "..", "src", "nightwave_ja"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

os.environ.setdefault("NIGHTWAVE_MOCK", "1")
