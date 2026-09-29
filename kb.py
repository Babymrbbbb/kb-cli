# -*- coding: utf-8 -*-
"""
知识库检索器 — 多子库 × 多层

用法:
  python kb.py list                                列出所有子知识库与文档数
  python kb.py query "关键词"                      全库检索(原始资料全文)
  python kb.py query "关键词" -b 子库名            只查指定子库
  python kb.py query "关键词 A 关键词 B" --top 8   多词检索 + 限制展示条数
  python kb.py query -f query.txt                  从文件读取查询词(每行或空格分隔)

设计要点:
  - 检索直接打 L3 原始资料全文(保证召回)
  - 命中返回精炼标题(L1 里解析的 H1) + 原文相对路径 + 摘要行
  - 输出一律以 UTF-8 字节写入 stdout.buffer, 避免 Windows 控制台 GBK 乱码
  - 同时落盘 _meta/last_result.txt, 便于程序化消费

设计哲学: 召回优先 > 精确率。宁多召一条让人扫一眼, 也别漏。
"""
import os, sys, argparse, re

KB = os.path.dirname(os.path.abspath(__file__))
_buf = []

def out(s=""):
    _buf.append(s + "\n")

def flush():
    text = "".join(_buf)
    sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    # 同时落 UTF-8 结果文件, 规避控制台编码问题, 便于直接读取
    try:
        os.makedirs(os.path.join(KB, "_meta"), exist_ok=True)
        with open(os.path.join(KB, "_meta", "last_result.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

def list_subs():
    subs = []
    for name in sorted(os.listdir(KB)):
        p = os.path.join(KB, name)
        if not os.path.isdir(p) or name.startswith("_"):
            continue
        l1 = os.path.join(p, "L1_速查与结论.md")
        n = 0
        if os.path.exists(l1):
            with open(l1, "r", encoding="utf-8", errors="ignore") as f:
                n = sum(1 for ln in f if ln.startswith("## "))
        subs.append((name, n))
    out(f"知识库根: {KB}")
    out(f"子知识库({len(subs)}个):\n")
    for name, n in subs:
        out(f"  {name:<10} {n} 篇  (query: kb.py query <词> -b {name})")
    return subs

def _title_of(text, fallback):
    for ln in text.splitlines():
        m = re.match(r"^#\s+(.*)", ln.strip())
        if m:
            return m.group(1).strip()
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()[:60]
    return fallback

def search_in_sub(sub, terms, top):
    p = os.path.join(KB, sub)
    l3 = os.path.join(p, "L3_原始资料")
    l1 = os.path.join(p, "L1_速查与结论.md")
    l1_titles = {}
    if os.path.exists(l1):
        cur_rel = None; cur_title = None
        for ln in open(l1, "r", encoding="utf-8", errors="ignore"):
            if ln.startswith("## "):
                cur_title = ln[3:].strip()
            elif ln.startswith("- 路径:"):
                cur_rel = ln.split("`", 1)[1].rstrip("`") if "`" in ln else None
                if cur_rel and cur_title:
                    l1_titles[cur_rel] = cur_title
    hits = []
    if os.path.isdir(l3):
        for root, _, files in os.walk(l3):
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in (".md", ".txt", ".markdown"):
                    continue
                fp = os.path.join(root, fn)
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except Exception:
                    continue
                low = text.lower()
                sc = 0; ok = True
                for t in terms:
                    c = low.count(t.lower())
                    if c == 0:
                        ok = False; break
                    sc += c
                if not ok or sc == 0:
                    continue
                rel = os.path.relpath(fp, p).replace("L3_原始资料" + os.sep, "")
                title = l1_titles.get(rel) or _title_of(text, fn)
                snip = ""
                for ln in text.splitlines():
                    if any(t.lower() in ln.lower() for t in terms):
                        snip = re.sub(r"\s+", " ", ln).strip()[:140]; break
                hits.append((sc, title, rel, snip))
    hits.sort(key=lambda x: -x[0])
    return hits[:top * 3]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="query")
    ap.add_argument("query", nargs="*")
    ap.add_argument("-b", "--base")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("-f", "--file", help="从 UTF-8 文件读取查询词(每行/空格分隔), 规避控制台编码问题")
    args = ap.parse_args()

    if args.cmd == "list":
        list_subs(); flush(); return

    terms = [t for t in args.query if t]
    if args.file and os.path.exists(args.file):
        raw = open(args.file, "r", encoding="utf-8", errors="ignore").read()
        terms = [t for t in re.split(r"\s+", raw) if t]
    if not terms:
        out("用法: kb.py query <词> [-b 子库]  |  或  kb.py query -f query.txt")
        flush(); return

    if args.base:
        subs = [args.base] if os.path.isdir(os.path.join(KB, args.base)) else []
        if not subs:
            out(f"未找到子库: {args.base}\n可用子库:"); list_subs(); flush(); return
    else:
        subs = [n for n in sorted(os.listdir(KB))
                if os.path.isdir(os.path.join(KB, n)) and not n.startswith("_")]

    all_hits = []
    for sub in subs:
        all_hits.extend((sub, h) for h in search_in_sub(sub, terms, args.top))

    all_hits.sort(key=lambda x: -x[1][0])
    show = all_hits[:args.top]

    out(f"检索: {' '.join(terms)}" + (f"  [子库={args.base}]" if args.base else "") +
        f"  ->  命中 {len(all_hits)} 篇, 展示 {len(show)} 条\n")
    if not show:
        out("未找到匹配。可换词或去掉 -b 限定做全库检索。")
        flush(); return
    for i, (sub, (sc, title, rel, snip)) in enumerate(show, 1):
        out(f"{i}. 【{sub}】{title}")
        if rel:
            out(f"   原文: {rel}")
        if snip:
            out(f"   {snip[:110]}")
        out(f"   相关度: {sc}")
        out("")
    flush()

if __name__ == "__main__":
    main()
