import base64
from typing import List


def analyze_image_with_blocks(client, image_path, blocks, model):
    """
    画像とテキストブロック情報を用いて、GPT-4o-miniによるテキスト抽出を実施

    Args:
        image_path (str): 画像のパス
        blocks (list): テキストブロック情報

    Returns:
        str: GPT-4o-miniによる解析結果
    """
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")

    blocks_content = ""
    for block in blocks:
        if block['type'] == 0:
            for line in block["lines"]:
                for span in line["spans"]:
                    blocks_content += span["text"] + " "
                blocks_content += "\n"
        elif block['type'] == 'table':
            for row in block['data']:
                blocks_content += str(row) + "\n"
            blocks_content += "\n"

    template_prompt = f"""
    以下はPDFドキュメントの画像と、そのページから抽出されたテキストブロック情報です。
    この情報を使用して、元のPDFの構造を保ちながら、正確なテキスト抽出を行い、Markdown形式で出力してください。
    Markdown形式で出力時に```markdown```といった記載は不要です。

    特に以下の点に注意してください：
    - 表、箇条書き、見出しなどのドキュメントの構造を正確に再現する
    - テキストブロック情報（特に座標情報）を活用して、各要素の配置を正しく理解し、テキストの順序を正確に決定する
    - 画像に含まれるテキストが、テキストブロック情報にない場合、確信度合いによってはそれも出力対象とする
    - 抽出したテキスト情報以外の余計な要素は出力しない
    - 重複した情報は出力しない
    - ページ数は出力しない（例：P.1など）
    - 出力すべきテキストがない場合、何も出力しない

    テキストブロック情報:
    {blocks_content}
    """

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": template_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                    },
                ],
            }
        ],
        max_tokens=4096,
        temperature=0.0
    )

    return response.choices[0].message.content

def extract_company_name(lines: List):
    """
    Markdownファイルから候補の行を抽出する関数

    処理の流れ:
        1. 新しい候補抽出処理
            - 「統合報告書」または「統合レポート」が含まれる行を検出し、
            その1行前と1行後の行を候補とする
            - その候補のうち、「株式会社」または「グループ」を含むもの（上段優先）を採用する
        2. 従来の候補抽出処理（フォールバック）
            - 1で適切な候補が得られなかった場合、順次他の手法で候補を抽出する
        3. 後処理
            - 候補行に「株式会社」が含まれている場合、そのワード以降（または前）の文字列を整形する
            - 半角スペースが複数含まれる場合、最後の半角スペースを基準に不要な部分を削除する
            - 候補行に「グループ」が含まれている場合、「グループ」以降の文字列を削除する

    :param file_path: 対象のMarkdownファイルのパス
    :return: 加工済みの候補行（見つからなければ None）
    """

    candidate = None

    # 1. 新しい候補抽出処理（統合報告書／統合レポート関連）
    for i, line in enumerate(lines):
        if "統合報告書" in line or "統合レポート" in line:
            prev_line = lines[i - 1] if i > 0 else ""
            next_line = lines[i + 1] if i < len(lines) - 1 else ""
            # 1行前が優先
            if "株式会社" in prev_line or "グループ" in prev_line:
                candidate = prev_line
                break
            elif "株式会社" in next_line or "グループ" in next_line:
                candidate = next_line
                break
            else:
                break

    # 2. その他の抽出処理：候補がまだ見つからない場合
    if not candidate:
        # (a) 「## P.1～## P.2」間の行を探索
        start_idx = end_idx = None
        for i, line in enumerate(lines):
            if "## P.1" in line:
                start_idx = i
            if "## P.2" in line and start_idx is not None:
                end_idx = i
                break
        if start_idx is not None and end_idx is not None and start_idx < end_idx:
            for i in range(start_idx + 1, end_idx):
                if "株式会社" in lines[i] or "グループ" in lines[i]:
                    candidate = lines[i]
                    break

    if not candidate:
        # (b) 「〒」を含む行の直前の行を候補とする
        for i, line in enumerate(lines):
            if "〒" in line:
                candidate = lines[i - 1] if i > 0 else ""
                break

    # 3. フォールバック処理：候補に会社名キーワードが含まれていない場合
    if not candidate or (("株式会社" not in candidate) and ("グループ" not in candidate)):
        # 統合報告書の1行前を候補とする
        for i, line in enumerate(lines):
            if "統合報告書" in line:
                if i > 0:
                    candidate = lines[i - 1]
                    j = i - 1
                    # 候補が空欄の場合、後続の行を探索
                    while candidate.strip() == "" and j < len(lines) - 1:
                        j += 1
                        candidate = lines[j]
                break

        if not candidate or (("株式会社" not in candidate) and ("グループ" not in candidate)):
            for i, line in enumerate(lines):
                if any(kw in line for kw in ["## 会社概要", "## 会社情報", "お問い合わせ先"]):
                    if i + 1 < len(lines):
                        candidate = lines[i + 1]
                        j = i + 1
                        while candidate.strip() == "" and j < len(lines) - 1:
                            j += 1
                            candidate = lines[j]
                    break

    if not candidate:
        return "Unknown"

    # 3. 後処理
    # (a) 「株式会社」に関する処理
    pos = candidate.find("株式会社")
    if pos != -1:
        if pos == 0:
            # 候補行が「株式会社」で始まる場合は除去する
            candidate = candidate[len("株式会社"):]
        else:
            # 先頭以外に現れる場合は、その前までを採用
            candidate = candidate[:pos]
            # もし複数の半角スペースがある場合は、最後のスペース以降の文字列にする
            if candidate.count(" ") > 1:
                last_space = candidate.rfind(" ")
                candidate = candidate[last_space + 1:]
    # (b) 半角スペースが複数ある場合（必要なら count でチェック）
    if candidate.count(" ") >= 1:
        last_space = candidate.rfind(" ")
        candidate = candidate[last_space + 1:]
    # (c) 「グループ」が含まれている場合は、「グループ」以降（グループ自体は残す）を切り落とす
    idx_group = candidate.find("グループ")
    if idx_group != -1:
        candidate = candidate[: idx_group + len("グループ")]

    return candidate.strip()