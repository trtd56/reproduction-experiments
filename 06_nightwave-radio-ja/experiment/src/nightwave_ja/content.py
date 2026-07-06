"""content.py — NIGHTWAVE-JA 局コンテンツバンク（pure stdlib）。

自律運行する番組の単一情報源。SONG バンクはブラウザへ配信され
（GET /api/songs）、クライアントが生成音楽と now-playing プレートを描画し、
サーバーは各曲の曲名/アーティストを `song_intro` セグメントに使う。
他のバンクはテンプレート系セグメント（station_id / weather / dedication）と
ソニックロゴを支える。

各曲の音楽パラメータはブラウザ内の生成エンジンを駆動する:
  key    : ルート音名（エンジンが MIDI ルートに写像）
  scale  : major | minor | dorian | lydian | pentatonic_minor
  tempo  : BPM（60-90、深夜のテンポ）
  timbre : rhodes | sine_pad | triangle_pluck | soft_saw | music_box
  vibe   : 人間向けラベル（DJ のイントロの味付けに使う。動作には非依存）
"""

# --- 楽曲（架空。24曲以上、key/scale/tempo/timbre に幅を持たせる） --------- #
SONGS = [
    {"title": "ネオンの雨",             "artist": "火曜日の幽霊たち",       "vibe": "melancholy",   "key": "A",  "scale": "minor",            "tempo": 72, "timbre": "rhodes"},
    {"title": "青い時間のラストオーダー", "artist": "真夜中クイン",           "vibe": "jazzy",       "key": "D",  "scale": "dorian",           "tempo": 84, "timbre": "rhodes"},
    {"title": "砂嵐の子守唄",           "artist": "ビロード・アンテナ",     "vibe": "dreamy",       "key": "F",  "scale": "lydian",           "tempo": 64, "timbre": "sine_pad"},
    {"title": "眠る町を継ぐ国道",       "artist": "カセット・サンデー",     "vibe": "nostalgic", "key": "C",  "scale": "major",            "tempo": 78, "timbre": "triangle_pluck"},
    {"title": "午前三時の食堂",         "artist": "エミと空席たち",         "vibe": "lonely",       "key": "E",  "scale": "minor",            "tempo": 68, "timbre": "rhodes"},
    {"title": "ダイヤルに寄る蛾",       "artist": "引き潮ラジオ",           "vibe": "hypnotic", "key": "G",  "scale": "pentatonic_minor", "tempo": 70, "timbre": "soft_saw"},
    {"title": "六番チャンネルの雪",     "artist": "しずかな時間",           "vibe": "wistful",         "key": "Bb", "scale": "major",            "tempo": 74, "timbre": "music_box"},
    {"title": "紙の月モーテル",         "artist": "夕暮れカーディガン",     "vibe": "warm",     "key": "D",  "scale": "major",            "tempo": 80, "timbre": "triangle_pluck"},
    {"title": "スローダンスの亡霊",     "artist": "真夜中クイン",           "vibe": "romantic",   "key": "Ab", "scale": "minor",            "tempo": 66, "timbre": "rhodes"},
    {"title": "電話線",                 "artist": "火曜日の幽霊たち",       "vibe": "pensive",         "key": "C",  "scale": "dorian",           "tempo": 76, "timbre": "sine_pad"},
    {"title": "琥珀の街灯",             "artist": "ビロード・アンテナ",     "vibe": "cozy",       "key": "F",  "scale": "major",            "tempo": 82, "timbre": "rhodes"},
    {"title": "雨天順延",               "artist": "カセット・サンデー",     "vibe": "breezy",         "key": "G",  "scale": "major",            "tempo": 88, "timbre": "triangle_pluck"},
    {"title": "不眠、やさしく",         "artist": "エミと空席たち",         "vibe": "tender",       "key": "E",  "scale": "minor",            "tempo": 62, "timbre": "music_box"},
    {"title": "いちばん長い帰り道",     "artist": "引き潮ラジオ",           "vibe": "hopeful",           "key": "D",  "scale": "lydian",           "tempo": 80, "timbre": "soft_saw"},
    {"title": "空室あり",               "artist": "しずかな時間",           "vibe": "eerie",         "key": "A",  "scale": "pentatonic_minor", "tempo": 60, "timbre": "sine_pad"},
    {"title": "冷めたコーヒー",         "artist": "夕暮れカーディガン",     "vibe": "bittersweet", "key": "Bb", "scale": "minor",            "tempo": 70, "timbre": "rhodes"},
    {"title": "発信音のセレナーデ",     "artist": "真夜中クイン",           "vibe": "jazzy",       "key": "F",  "scale": "dorian",           "tempo": 86, "timbre": "rhodes"},
    {"title": "玄関の灯り",             "artist": "カセット・サンデー",     "vibe": "gentle",       "key": "C",  "scale": "major",            "tempo": 75, "timbre": "triangle_pluck"},
    {"title": "真夜中、くりかえし",     "artist": "ビロード・アンテナ",     "vibe": "hypnotic", "key": "G",  "scale": "minor",            "tempo": 72, "timbre": "soft_saw"},
    {"title": "地図にない町",           "artist": "火曜日の幽霊たち",       "vibe": "mysterious",   "key": "Eb", "scale": "lydian",           "tempo": 68, "timbre": "sine_pad"},
    {"title": "塩水ラジオ",             "artist": "引き潮ラジオ",           "vibe": "dreamy",       "key": "D",  "scale": "major",            "tempo": 78, "timbre": "music_box"},
    {"title": "最終バスは行ってしまった", "artist": "エミと空席たち",        "vibe": "melancholy",   "key": "A",  "scale": "minor",            "tempo": 66, "timbre": "rhodes"},
    {"title": "ゆっくり漂うチャンネル", "artist": "しずかな時間",           "vibe": "ambient",   "key": "F",  "scale": "lydian",           "tempo": 64, "timbre": "sine_pad"},
    {"title": "おやすみ、名前も知らない人", "artist": "夕暮れカーディガン", "vibe": "tender",       "key": "C",  "scale": "major",            "tempo": 70, "timbre": "music_box"},
]

# --- リスナーからのリクエスト（架空のハンドル。デモ安全な canned データ） -- #
# 曲名をキーに SONGS の各エントリへ付与する。載っていない曲はリクエストなし
# （DJ は帰属を省略する）。
SONG_RECS = {
    "ネオンの雨": "@kokudo9_truck",
    "砂嵐の子守唄": "@mayonaka_mari",
    "午前三時の食堂": "@yakin_nurse_j",
    "ダイヤルに寄る蛾": "@haishin_fukurou",
    "紙の月モーテル": "@shimeno_ippai",
    "電話線": "@soushiki_gairo",
    "不眠、やさしく": "@niji_no_theo",
    "いちばん長い帰り道": "@nagakyori_hando",
    "冷めたコーヒー": "@shokudou_dot",
    "玄関の灯り": "@porch_no_pete",
    "最終バスは行ってしまった": "@yofukashi_nadia",
    "おやすみ、名前も知らない人": "@signoff_samu",
}
for _song in SONGS:
    _song["recommended_by"] = SONG_RECS.get(_song["title"], "")

# --- 局名アナウンス（曲間に読む。エンジンはソニックロゴのスティングも鳴らす） #
STATION_IDS = [
    "お聴きの放送は NIGHTWAVE、周波数98.6 -- ダイヤルの一番端の局です。",
    "こちら NIGHTWAVE。夜が明けるまで、ひとりぼっちの傍にいます。",
    "NIGHTWAVE -- 夜通し、毎晩、まだ起きているあなたのために。",
    "お聴きの局は NIGHTWAVE。あなたと同じくらい夜更かしな、唯一の周波数です。",
    "こちら NIGHTWAVE、98.6。どこか暖かい場所からお送りしています。",
]

SONIC_LOGO = "NIGHTWAVE……ダイヤルの一番端の局。"

# --- 架空の天気 + ありえない時計（実在しない町のために） ------------------ #
WEATHER = [
    "灯里町（あかりちょう）の今夜: どの地図にも載っていない川から低い霧が上がって、気温は16度、本が読めるくらいの月が出ています。",
    "松洞（まつほら）の天気です: よく晴れて、東から柔らかい風。それからスタジオの時計がさっき、見覚えのない数字の15分過ぎを打ちました。",
    "澪浦（みおうら）は静かな夜、気温は15度。あの街角にだけ、私が覚えている限りずっと、同じ雨が降り続いています。",
    "小燠町（こおきちょう）の今夜: 季節のわりに暖かく、道には誰もいません。空の色は、点けっぱなしにされたラジオの色です。",
    "鎮水（しずみ）は霧が深くなってきました。気温14度。どこかの家の玄関灯が、私がこのシフトを始めるより前から点いたままです。",
]

# --- あらかじめ仕込まれたリスナー献呈（DJ が放送で読む） ------------------- #
DEDICATIONS = [
    {"name": "国道9号を走る運転手さん",     "message": "今夜も暗闇を走り抜けるすべての人へ"},
    {"name": "マリエさん",                   "message": "今どの道を歩いていても、届きますように"},
    {"name": "夜勤の看護師のみなさん",       "message": "世界が眠っているあいだ、世界を支えている人たちへ"},
    {"name": "眠れない子",                   "message": "家が静かすぎるんだそうです"},
    {"name": "長いシフトを終えたあなた",     "message": "ようやく、おうちに帰れますね"},
    {"name": "終夜営業の食堂の常連さんたち", "message": "夜明け前の、もう一杯に"},
    {"name": "サムというリスナーさん",       "message": "最近、夜が長く感じるそうです"},
    {"name": "ひとりで夜を過ごしている誰か", "message": "いま感じているほど、ひとりじゃありませんよ"},
]

# --- フォールバックの「ひとこと」（LLM の thought セグメント失敗時のみ） ---- #
THOUGHTS = [
    "夜の一番深い時間の不思議なところは -- 誰もが正直者になってしまうことです。",
    "誰かが今夜、まだ口に出していない理由で起きています。この一曲は、あなたに。",
    "この時間の世界は、少しだけ本当に近い気がします -- 誰も、誰かのために演技をしていないから。",
    "今夜眠れずに心配ごとを抱えているなら、一、二曲のあいだ、私に持たせてください。そのための深夜シフトです。",
    "ラジオの声には、独特の連れ添い方があります。今夜あなたのそれでいられて、嬉しいですよ。",
]

# --- 再識別ライン: 戻ってくるたびに DJ が名乗る ---------------------------- #
REJOINS = [
    "引き続き、宵野サムがお送りしています。NIGHTWAVE、98.6。",
    "宵野サムです。夜の一番深いところで、まだあなたと一緒にいます。",
    "宵野サムでした -- お聴きの放送は NIGHTWAVE、夜通しお送りしています。",
    "おかえりなさい。オールナイトの机から宵野サム、NIGHTWAVE 98.6です。",
    "こちら宵野サム。NIGHTWAVE で、ひとりぼっちの傍にいます。",
]

# モデル出力が degenerate だったときの、コーラーターン用の温かいフォールバック。
CALLER_FALLBACKS = [
    "この時間に向き合うには、ちょうどいい問いですね。そのまま、そこにいてください。",
    "聞こえていますよ。いい問いというのは、長い夜のいい連れです。お電話ありがとう。",
    "今夜かけてきてくれて嬉しいです。しばらくは、次のレコードに答えてもらいましょう。",
    "そちらこそ、お気をつけて -- 放送に付き合ってくれて、ありがとう。",
]

# --- プレコーラーイントロ: 電話がつながった瞬間に流す ---------------------- #
CALLER_INTROS = [
    "おや -- どうやら、お電話がつながっているようです。どうぞ: お名前と、"
    "今夜の御用は何でしょう。",
    "スイッチボードのランプが点きました。宵野サムです、放送に乗っていますよ -- "
    "お名前と、聞きたいことを教えてください。",
    "誰かが夜更かしして、手を伸ばしてくれたようです。NIGHTWAVE につながって"
    "います -- どちらさまですか、今夜は何が眠らせてくれないんです？",
]

# --- ダイヤル外のゴースト断片（SP4 テンプレートフォールバック） ------------ #
FRAGMENTS = [
    "9キロポスト付近の夜勤の看護師さんたちへ、応答願います",
    "実在しない町の気温は5度、下がり続けています",
    "お聴きの周波数は、割り当てられたことがありません",
    "橋がぜんぶラジオでできている夢を、誰も渡らなかったと彼女は言った",
    "このあと、プレスされたことのないレコードをお送りします",
    "こちらは1974年に止まった時計の時報です",
    "まだ走っている人たちへ、道はもう少しだけ続きます",
]

# --- 手続き生成レコードカードの語バンク（SP3 のモデル失敗時フォールバック） - #
CARD_TITLE_A = ["最終", "ゆるやかな", "誰もいない", "紙の", "砂嵐の", "琥珀の", "真夜中の",
                "しずかな", "塩水の", "ネオンの", "遠い", "うつろな", "青ざめた", "長い"]
CARD_TITLE_B = ["列車", "時間", "灯り", "雨", "子守唄", "国道", "街灯",
                "チャンネル", "モーテル", "電話線", "港", "夢", "窓", "ラジオ"]
CARD_ARTIST_A = ["ザ・", "引き潮", "ビロード", "カセット", "夕暮れ", "しずかな", "紙の", "ゆるやか"]
CARD_ARTIST_B = ["タイド・ラジオ", "アンテナ", "サンデー", "アワーズ", "カーディガン", "幽霊たち",
                 "高架橋", "並木通り", "周波数帯"]

# --- 許可される音楽 enum（コンテンツ整合性テスト用） ----------------------- #
SCALES = ("major", "minor", "dorian", "lydian", "pentatonic_minor")
TIMBRES = ("rhodes", "sine_pad", "triangle_pluck", "soft_saw", "music_box")
