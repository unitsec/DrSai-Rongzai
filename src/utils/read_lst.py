import re
from pathlib import Path

def _decode_bytes(raw: bytes) -> str:
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best and best.encoding:
            return raw.decode(best.encoding, errors="replace")
    except Exception:
        pass
    for enc in ("utf-8", "latin-1", "gbk"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")

def prune_lst_keep_main(path: str, save_to: str | None = None) -> str:
    """
    读取指定 .lst 文件，删除：
      - 文件开头的抬头（从文件开始直到首个 'Phases:' 行之前）
      - 'The equivalent positions are:' 到下一处 'Atoms:' 之前的等价位置段
    返回处理后的完整字符串（保留其余所有内容）。
    如果提供 save_to，会把结果写到该文件并返回路径内容。
    """
    p = Path(path)
    if not p.exists():
        print(f"lst file not found: {path}")
        return ""
    raw = p.read_bytes()
    text = _decode_bytes(raw)

    # 1) 删除开头直到首个 'Phases:'（保留 'Phases:' 行及其后内容）
    m = re.search(r'(?is)\A.*?(?=^\s*Phases:\s*$)', text, flags=re.M)
    if m:
        text = text[m.end():]

    # 2) 删除 'The equivalent positions are:' 到下一处 'Atoms:' 之前的内容（包含标题行）
    # 使用非贪婪匹配，确保保留 'Atoms:' 开头
    text = re.sub(r'(?is)The equivalent positions are:.*?(?=^\s*Atoms:\s*$)', '', text, flags=re.M)

    # 清理可能留下的多余空行（保留最多一个连续空行）
    text = re.sub(r'\n{3,}', '\n\n', text)

    if save_to:
        Path(save_to).write_text(text, encoding='utf-8')
    return text

# 示例用法
if __name__ == "__main__":
    src = "datasets/BL16/RUNdataFiles/RUN0023568/output/guestuser@gmail.com23_guestuser@gmail.com/gsas_output_f70153bb-6da6-468c-9531-b8c8ea343552/neutron_refinement_2.lst"
    out = prune_lst_keep_main(src)
    print(out)  # 显示前2000字符预览