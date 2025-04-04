import os
import re

def process_markdown_file(input_file: str, line_target_words: list, header_keywords: list, output_dir: str) -> None:
    """
    Markdownファイルを読み込み、フィルタを適用して出力

    1. 行削除フィルタ:
        - 各行に対し、line_target_words のいずれかのワードが含まれている場合、その行は除外
    2. セクション削除フィルタ:
        - 行頭が '#' のヘッダー行に対し、header_keywords のいずれかが含まれる場合、
        そのヘッダー行から次のヘッダー行が現れるまでのすべての行（ヘッダー行自体も含む）を除外します。
    3. ページ数表記削除フィルタ:
        - 行に "P.数字"（例: P.1）の表記が含まれている場合、その行は除外します。

    Parameters:
        input_file (str): 入力Markdownファイルのパス。
        output_file (str): 出力先Markdownファイルのパス。
        line_target_words (list): 行単位で削除対象とするワードのリスト。
        header_keywords (list): ヘッダー行に対して削除対象とするキーワードのリスト。
                                ヘッダーにこれらのキーワードが含まれる場合、そのヘッダーから次のヘッダーまでを削除します。
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
                    continue
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