import os
import re
import time
from typing import List, Any
from tqdm.auto import tqdm

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain.vectorstores import FAISS
from openai import InternalServerError


class JapaneseCharacterTextSplitter(RecursiveCharacterTextSplitter):
    def __init__(self, **kwargs: Any):
        separators = ["\n\n", "\n", "。", "、", " ", ""]
        super().__init__(separators=separators, **kwargs)

def clean_text(text: str) -> str:
    """
    Markdown由来の記法や余分な改行・空白を除去または整理するクリーニング処理の例。

    ・コードブロック（```）は除去
    ・インラインコード（`...`）は記号を除いてテキストのみ残す
    ・リンクはリンクテキストのみを残す
    ・**や*、__や_による強調は除去
    ・ヘッダー（#）は除去
    ・3回以上連続する改行は2回の改行に整理
    ・連続する空白を1つに整理
    ・前後の余分な空白を除去
    """
    # コードブロックの除去（複数行に渡る部分）
    text = re.sub(r'```[\s\S]*?```', '', text)

    # インラインコードの除去（バッククォートを除いて中身だけ残す）
    text = re.sub(r'`([^`]*)`', r'\1', text)

    # リンクの処理：[リンクテキスト](URL) → リンクテキストのみ
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # 太字・斜体の記法の除去（**や__で囲まれた部分をそのまま残す）
    text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
    text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)

    # ヘッダー記法の除去：行頭の#を削除
    text = re.sub(r'^\s*#{1,6}\s*', '', text, flags=re.MULTILINE)

    # ページ番号の除去：例として "P.58" や "p.  58" のようなパターン
    text = re.sub(r'\b[Pp]\.?\s*\d+\b', '', text)

    # 3つ以上連続する改行は2つに整理
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 複数の空白を1つの空白に整理
    text = re.sub(r' +', ' ', text)

    # 前後の不要な空白・改行の除去
    return text.strip()

def process_files_in_batches(
        embeddings,
        md_paths: List[str],
        chunk_size: int = 512,
        chunk_overlap: int = 32,
        batch_size: int = 10,
        max_retries: int = 3,
        retry_interval: int = 5
        ):
    """
    指定されたディレクトリ内のMarkdownファイルをファイルごとに逐次処理する
    """

    all_documents = []
    vector_store = None

    for md_path in tqdm(md_paths):
        loader = UnstructuredMarkdownLoader(md_path)
        content = loader.load()

        text_splitter = JapaneseCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        doc_chunks = text_splitter.split_documents(content)
        for doc in doc_chunks:
            doc.page_content = clean_text(doc.page_content)
            filename = os.path.basename(md_path)
            base_filename = os.path.splitext(filename)[0]
            doc.page_content = f"{base_filename}\n\n" + doc.page_content
        all_documents.extend(doc_chunks)

    # すべてのドキュメントをバッチ処理
    for i in tqdm(range(0, len(all_documents), batch_size)):
        batch_documents = all_documents[i:i + batch_size]
        retries = 0
        while retries < max_retries:
            try:
                if vector_store is None:
                    vector_store = FAISS.from_documents(batch_documents, embeddings)
                else:
                    vector_store.add_documents(batch_documents)
                break
            except InternalServerError:
                retries += 1
                print(f"Internal Server Error. リトライ {retries}/{max_retries}...")
                time.sleep(retry_interval)
            except Exception as e:
                print(f"予期しないエラーが発生しました: {e}")
                break

    return vector_store
