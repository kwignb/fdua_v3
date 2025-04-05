# （金融庁共催）第３回金融データ活用チャレンジ コード共有

## 概要
- PDFドキュメントからテキスト情報を抽出し、検索を可能とするためのRAGシステムを構築
- GPT-4o-miniを用いたマルチモーダルな手法で文書構造を維持したMarkdown形式でのテキスト抽出を実施
- コンペ内容については[リンク](https://signate.jp/competitions/1515)を参考

## フォルダツリー
```
fdua_v3/
├── .env                           # 環境変数ファイル
├── .gitignore
├── .python-version
├── uv.lock
├── pyproject.toml                 # 依存ライブラリリスト (uvで同期可能)
├── README.md
├── src/
│   ├── __init__.py
│   ├── dataset/
│   │   ├── __init__.py
│   │   ├── preprocess.py          # PDF前処理
│   │   └── postprocess.py         # 抽出Markdownの後処理
│   ├── model/
│   │   ├── __init__.py
│   │   └── retriever.py           # Retriever構築
│   └── tools/
│       ├── __init__.py
│       ├── create_docs.py         # テキスト分割、Vector DB構築、Markdownクリーニング
│       └── text_extract.py        # 画像とテキスト情報からのMarkdown生成、会社名抽出
└── notebooks/                     # 実行用ノートブック
    ├── 001_pdf_to_md.ipynb        # PDFをMarkdownに変換するノートブック
    └── 002_create_answers.ipynb   # RAGを実装し、答えを推論

```

## セットアップ
1. uvのインストール
    - [公式ドキュメント](https://github.com/astral-sh/uv)に従ってインストール
        ```
        # 例 (macOS/Linux)
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```
2. レポジトリのクローンと仮想環境の構築
    ```
    git clone git@github.com:kwignb/fdua_v3.git
    cd fdua_v3
    uv sync
    ```
    - 注意：
        - `pdf2image`を使用するために`poppler`がシステムに必要となるため、OSに合わせてインストールを実施
            - macOS: `brew install poppler`
            - Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y poppler-utils`
3. 環境変数の設定
    - プロジェクトルートの`.env`にOpenAI APIキーなどを記述
4. Signateからデータをダウンロードし、プロジェクトルートに`signate_data`として配置