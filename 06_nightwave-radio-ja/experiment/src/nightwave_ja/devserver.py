"""NIGHTWAVE-JA のローカル開発サーバー -- gradio 不使用。

生のラジオドキュメントを GET "/" で配信し（トップレベル。iframe に包まない）、
ブラウザがドキュメントルートでマイク + 自動再生を許可できるようにする。
加えて server.create_api() の /api/* を全部持つ。

モック運転（モデル不要、UI と API 形状の確認用）:

    NIGHTWAVE_MOCK=1 python devserver.py

実運転（TinySwallow + faster-whisper + Kokoro をローカルロード）:

    python devserver.py

その後ブラウザで http://localhost:7860 を開く。初回はモデルのロードと
TTS つなぎクリップの合成でリクエストが遅くなることがある。先に温めるには
PRELOAD=1 を付けて起動する。
"""

import os

import uvicorn
from fastapi.responses import HTMLResponse

from server import create_api, read_radio_html

api = create_api()


@api.get("/", response_class=HTMLResponse)
def root_radio():
    # ローカルのブラウザ確認用に、生のラジオドキュメントを直接（トップレベルで）配信。
    return HTMLResponse(read_radio_html())


if __name__ == "__main__":
    if os.environ.get("PRELOAD") == "1" and os.environ.get("NIGHTWAVE_MOCK") != "1":
        import engine
        print("モデルを事前ロードしています（LLM / ASR / TTS）……")
        engine.preload()
        print("ロード完了。")
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(api, host="0.0.0.0", port=port)
