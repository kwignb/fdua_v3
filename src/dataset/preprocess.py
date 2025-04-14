import os
import re
from pdf2image import convert_from_path

import numpy as np
import cv2

import fitz


def analyze_page(image):
    """
    PDFの1ページを左右に分割するかどうかを判定
    ステップ1: エッジ検出による分割可能性の探索
    ステップ2: ページ中央の特定の範囲が均一な配色になっているかで判定
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape

    # 1.エッジ検出による分割可能性の探索
    middle_region = gray[:, width // 2 - 10: width // 2 + 10]  # Central strip
    edges = cv2.Canny(middle_region, 50, 150)
    edge_density = np.sum(edges) / edges.size

    # エッジ検出を行う際のしきい値の決定
    split_threshold = 0.95
    if edge_density < split_threshold:
        return True  # Split based on edge detection

    # 2.ページ中央の特定の範囲が均一な配色になっているかで判定
    center_region = image[:, width // 2 + 10: width // 2 + 30]
    max_value = np.max(center_region)
    min_value = np.min(center_region)
    if max_value - min_value < 10:
        return True

    return False

def split_and_save_pdf(pdf_path, output_pdf_path):
    """
    PDFを左右に分割して保存
    """
    doc = fitz.open(pdf_path)
    new_pdf = fitz.open()

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap()

        if pix.alpha:
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
        else:
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))

        if pix.n - pix.alpha == 3:
            pass
        elif pix.n - pix.alpha == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            raise ValueError(f"Unsupported number of color channels: {pix.n - pix.alpha}")

        if analyze_page(img):
            # print(f"Page {page_num + 1}: Splitting...")
            width, height = pix.width, pix.height

            left_rect = fitz.Rect(0, 0, width // 2, height)
            right_rect = fitz.Rect(width // 2, 0, width, height)

            left_page = new_pdf.new_page(width=width // 2, height=height)
            left_page.show_pdf_page(left_page.rect, doc, page_num, clip=left_rect)

            right_page = new_pdf.new_page(width=width // 2, height=height)
            right_page.show_pdf_page(right_page.rect, doc, page_num, clip=right_rect)
        else:
            # print(f"Page {page_num + 1}: Keeping as is.")
            new_page = new_pdf.new_page(width=page.rect.width, height=page.rect.height)
            new_page.show_pdf_page(new_page.rect, doc, page_num)

    new_pdf.save(output_pdf_path)
    new_pdf.close()

def combine_text_information(blocks, raw_text, words, tables_info):
    """
    複数のテキスト抽出方法の結果を組み合わせて、より完全なテキスト情報を構築
    表情報もあわせてblocksに挿入

    Args:
        blocks (list): page.get_text("dict")["blocks"] の結果
        raw_text (str): page.get_text("text") の結果
        words (list): page.get_text("words") の結果
        tables_info(list): page.find_tables() の結果

    Returns:
        list: 結合および補完されたテキスト情報（ブロック単位）
    """
    # 1. blocksが信頼できる場合は、それをベースにする
    if blocks and len(blocks) > 0 and blocks[0]['type'] == 0:
        # blocks内にtables_infoを挿入
        for table_info in reversed(tables_info):
            table_bbox = table_info["bbox"]
            inserted = False
            for i, block in enumerate(blocks):
                block_bbox = block["bbox"]
                if block_bbox[1] > table_bbox[3]:
                    blocks.insert(i, {"type": "table", "bbox": table_bbox, "data": table_info["data"]})
                    inserted = True
                    break
            if not inserted:
                blocks.append({"type": "table", "bbox": table_bbox, "data": table_info["data"]})

        return blocks

    # 2. blocksが空または不完全な場合、raw_textをベースにwordsで情報を補完
    if not raw_text:
        return []

    combined_blocks = []
    current_block = {"number": 0, "type": 0, "bbox": None, "lines": []}
    current_line = {"spans": [], "wmode": 0, "dir": (1.0, 0.0), "bbox": None}
    x0, y0, x1, y1 = float('inf'), float('inf'), -float('inf'), -float('inf')

    for word in words:
        wx0, wy0, wx1, wy1, wtext, _, _, _ = word

        x0 = min(x0, wx0)
        y0 = min(y0, wy0)
        x1 = max(x1, wx1)
        y1 = max(y1, wy1)

        current_line["spans"].append({
            "text": wtext,
            "font": "unknown",
            "size": 0,
            "flags": 0,
            "bbox": (wx0, wy0, wx1, wy1)
            })

    current_line["bbox"] = (x0, y0, x1, y1)
    current_block["lines"].append(current_line)
    current_block["bbox"] = (x0, y0, x1, y1)
    combined_blocks.append(current_block)

    # blocks内にtables_infoを挿入
    for table_info in reversed(tables_info):
        table_bbox = table_info["bbox"]
        inserted = False
        for i, block in enumerate(combined_blocks):
            block_bbox = block["bbox"]
            if block_bbox[1] > table_bbox[3]:  # ブロックの下端がテーブルの下端より下にある場合
                combined_blocks.insert(i, {"type": "table", "bbox": table_bbox, "data": table_info["data"]})
                inserted = True
                break
        if not inserted:
            combined_blocks.append({"type": "table", "bbox": table_bbox, "data": table_info["data"]})

    return combined_blocks

def pdf_to_blocks_and_png(pdf_path, output_folder):
    """
    PDFをページごとにPNG画像に変換し、構造化されたテキスト情報（ブロック単位）を抽出

    Args:
        pdf_path (str): PDFファイルのパス
        output_folder (str): 出力フォルダのパス

    Returns:
        list: ページごとのテキストブロック情報 (表情報含)
        list: PNG画像のパスのリスト
    """
    os.makedirs(output_folder, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=300)
    document = fitz.open(pdf_path)

    pages_blocks = []
    image_paths = []

    for i, image in enumerate(images):
        page = document[i]

        # 複数の方法でテキスト情報を取得
        blocks = page.get_text("dict")["blocks"]
        raw_text = page.get_text("text")
        words = page.get_text("words")

        # 表情報を取得
        tables_info = []
        tables = page.find_tables(strategy='text')
        if tables.tables:
            for table in tables.tables:
                table_info = table.extract()
                tables_info.append({"bbox": table.bbox, "data": table_info})

        # テキスト情報を組み合わせて補完 (表情報も一緒に)
        combined_text_info = combine_text_information(blocks, raw_text, words, tables_info)
        pages_blocks.append(combined_text_info)

        image_path = f"{output_folder}/page_{i+1:03}.png"
        image.save(image_path, "PNG")
        image_paths.append(image_path)

    return pages_blocks, image_paths

def process_markdown_file(input_file: str, line_target_words: list, header_keywords: list, output_dir: str) -> None:
    """
    Markdownファイルを読み込み、フィルタを適用して出力

    1. 行削除フィルタ:
        - 各行に対し、line_target_words のいずれかのワードが含まれている場合、その行は除外
    2. セクション削除フィルタ:
        - 行頭が '#' のヘッダー行に対し、header_keywords のいずれかが含まれる場合、
        そのヘッダー行から次のヘッダー行が現れるまでのすべての行（ヘッダー行自体も含む）を除外
    3. ページ数表記削除フィルタ:
        - 行に "P.数字"（例: P.1）の表記が含まれている場合、その行は除外

    Parameters:
        input_file (str): 入力Markdownファイルのパス
        output_file (str): 出力先Markdownファイルのパス
        line_target_words (list): 行単位で削除対象とするワードのリスト
        header_keywords (list): ヘッダー行に対して削除対象とするキーワードのリスト
                                ヘッダーにこれらのキーワードが含まれる場合、そのヘッダーから次のヘッダーまでを削除
    """

    def clean_text(line):
        line = re.sub(r'\n{3,}', '\n\n', line)
        line = re.sub(r' +', ' ', line)
        line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
        return line.strip()

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 元の改行形式を検出する（CRLF, LF, CR のいずれか）
    if '\r\n' in content:
        newline_char = '\r\n'
    elif '\r' in content:
        newline_char = '\r'
    elif '\n' in content:
        newline_char = '\n'
    else:
        newline_char = os.linesep

    # 改行文字を除いた各行のリストを取得する
    lines = content.splitlines()


    output_lines = []
    skip_section = False  # ヘッダーにより削除対象セクション内かどうかのフラグ

    for line in lines:
        # ページ数表記の削除: 例 "P.1", "P.2", … を含む行はスキップ
        if re.search(r'P\.\d+', line):
            continue

        line = clean_text(line)

        # Markdown のヘッダー行かどうかをチェック（行頭の空白を除いて '#' で始まるか）
        if line.lstrip().startswith('#'):
            if skip_section:
                # 現在、削除対象のセクション内の場合
                if any(keyword in line for keyword in header_keywords):
                    # 新たなヘッダーも削除対象なら、そのヘッダー行自体も出力しない
                    continue
                else:
                    # 新たなヘッダーが削除対象でなければ、削除対象セクションを終了
                    skip_section = False
                    # ヘッダー行自体が行削除対象ワードを含むかチェック
                    if any(word in line for word in line_target_words):
                        continue
                    else:
                        output_lines.append(line)
            else:
                # 現在、削除対象セクション外の場合
                if any(keyword in line for keyword in header_keywords):
                    # このヘッダー行が削除対象の場合、以降のセクションを除外開始
                    skip_section = True
                    continue  # ヘッダー行自体は出力しない
                else:
                    if any(word in line for word in line_target_words):
                        continue
                    else:
                        output_lines.append(line)
        else:
            # ヘッダー行でない通常の行の場合
            if skip_section:
                # 現在、削除対象セクション内なら出力しない
                continue
            else:
                if any(word in line for word in line_target_words):
                    continue
                else:
                    output_lines.append(line)

    # 検出した改行形式を使って再度内容を構築する
    new_content = newline_char.join(output_lines) + newline_char

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, os.path.basename(input_file)), 'w', encoding='utf-8', newline='') as f:
        f.writelines(new_content)
