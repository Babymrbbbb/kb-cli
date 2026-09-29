# -*- coding: utf-8 -*-
r"""
知识库构建器 — 把散落的 .md/.txt 源文档重组为「多子库 × 多层」结构。

设计目标：
  1. **零依赖**：只用 Python 3.8+ 标准库
  2. **可移植**：脚本所在目录即库根，放到任何位置都能跑
  3. **可重建**：每次运行清空重建（幂等）
  4. **可维护**：分类映射和子库描述全部集中在两个字典里，改一处即全局生效

产物结构：
  <脚本目录>/
    _meta/
      README.md            总说明（有哪些子库、如何单独查询、分层含义）
      catalog.json         机器可读的子库清单
    <子知识库>/
      L1_速查与结论.md    第 1 层：蒸馏视图（标题 + 结论要点 + 关键小节）
      L2_主题索引.md      第 2 层：按子主题归类的导航地图
      L3_原始资料/        第 3 层：从源库复制进来的原始 .md/.txt（保留子路径）
"""
import os
import json
import re
import shutil
import sys

# 强制 stdout 用 UTF-8，规避 Windows 控制台 GBK 乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------- 配置区
# 只需改这里两个字典即可适配你自己的知识领域

# 源库路径：把你的原始文档放这里
SRC = r"./sources"

# 目标库根：脚本所在目录即库根，放到哪都能跑
DST = os.path.dirname(os.path.abspath(__file__))

TEXT_EXTS = {".md", ".txt", ".markdown"}

# 源分类 -> 独立子知识库（第 1 段路径决定子库归属）
CAT_MAP = {
    "会员体系": "会员体系",
    "私域运营": "私域运营",
    "门店管理": "门店管理",
    "产品研发": "产品研发",
    "竞品动态": "竞品动态",
    "品牌营销": "品牌营销",
    "行业趋势": "行业趋势",
    "daily-logs": "日志沉淀",
    "logs": "日志沉淀",
    "notes": "日志沉淀",
    "misc": "补充来源",
    "archive": "历史归档",
    "(root)": "元数据库",
}
DEFAULT_SUBKB = "其他"

# 子库一句话说明（写进 _meta/README.md）
SUBKB_DESC = {
    "会员体系": "会员分层、储值、积分、会员日活动方案与复盘",
    "私域运营": "私域 SOP、社群/企微运营、朋友圈与内容策略",
    "门店管理": "门店日常运营、排班、SOP、损耗与巡检",
    "产品研发": "SKU 策略、新品方案、配方/合规资料",
    "竞品动态": "竞品品牌监测与研究结论（含竞品地图周更）",
    "品牌营销": "品牌定位、传播 campaign、素材与投放方案",
    "行业趋势": "行业趋势、行业日报、市场分析",
    "日志沉淀": "每日知识沉淀与工作日志 + 复盘周更",
    "补充来源": "外部补充来源并入的非重复内容",
    "历史归档": "历史旧体系去重后保留内容",
    "元数据库": "源库根级索引、合并剔除清单与方案框架文件",
    "其他": "未归入上述分类的零散文档",
}


# ---------------------------------------------------------------- 工具函数

def clean(s):
    """压缩空白字符。"""
    return re.sub(r"\s+", " ", s).strip()


def parse_doc(text, fallback):
    """
    解析一份 markdown/txt 文档，提取：
      - title:    第一个 H1（# 开头）；没有就用第一段非空行截断
      - headings: 所有 H2/H3 标题，最多保留 12 个
      - gist:     第一段非空正文，截断到 160 字

    这个函数是「蒸馏」的核心 —— 把一份长文档压缩成 L1 视图里的一行。
    """
    lines = text.splitlines()
    title = None
    headings = []
    body = []
    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*)", ln.strip())
        if m:
            h = m.group(1)
            t = m.group(2).strip()
            if h == "#" and title is None:
                title = t
            elif h in ("##", "###"):
                headings.append(t)
            continue
        if ln.strip().startswith("---"):
            continue  # 跳过 YAML frontmatter 分隔线
        body.append(ln)

    if not title:
        for ln in lines:
            if ln.strip():
                title = ln.strip()[:60]
                break
    title = title or fallback

    # gist: 第一段非空正文（遇到空行截断）
    gist = ""
    buf = []
    for ln in body:
        if ln.strip():
            buf.append(ln.strip())
            if len(" ".join(buf)) > 90:
                break
        elif buf:
            break
    gist = clean(" ".join(buf))[:160]
    return title, headings[:12], gist


# ---------------------------------------------------------------- 主流程

def main():
    if not os.path.isdir(SRC):
        print(f"ERROR 源库不存在: {SRC}")
        print("提示: 修改 build_kb.py 顶部的 SRC 常量，或者把源文档放到 ./sources/ 下")
        sys.exit(1)

    # 第一遍：扫描源库，按子库分类收集文档元数据
    store = {}
    copy_count = 0
    total_bytes = 0

    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, SRC)
            parts = rel.split(os.sep)

            # 第 1 段路径决定子库归属
            cat = parts[0] if len(parts) > 1 else "(root)"
            subkb = CAT_MAP.get(cat, DEFAULT_SUBKB)

            # 第 2 段路径作为子主题（L2 索引按此归类）
            subtopic = parts[1] if len(parts) > 2 else "(根)"

            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue

            size = len(text.encode("utf-8"))
            total_bytes += size
            title, headings, gist = parse_doc(text, fn)

            # 复制原始资料到 L3，保留子路径（parts[1:-1] 去掉文件名）
            dest_dir = os.path.join(DST, subkb, "L3_原始资料", *parts[1:-1])
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(full, os.path.join(dest_dir, fn))
            copy_count += 1

            store.setdefault(subkb, []).append({
                "rel": rel, "name": fn, "title": title,
                "headings": headings, "gist": gist, "size": size,
                "subtopic": subtopic,
            })

    if not store:
        print("ERROR 没有采集到任何 .md/.txt 文件。检查 SRC 路径与扩展名。")
        sys.exit(1)

    # 第二遍：为每个子库生成 L1（速查）和 L2（主题索引）
    for subkb, docs in store.items():
        docs.sort(key=lambda d: d["rel"])

        # ---- L1：蒸馏层，每篇一段（标题 + 路径 + 结论要点 + 关键小节）
        l1 = [f"# 【{subkb}】知识库 · 第 1 层 速查与结论", ""]
        l1.append(f"> 文档数: **{len(docs)}** ｜ 本层为蒸馏视图, 详情见 `L3_原始资料/` 同名文件")
        l1.append("")
        for d in docs:
            l1.append(f"## {d['title']}")
            l1.append(f"- 路径: `{d['rel']}`")
            if d["gist"]:
                l1.append(f"- 结论/要点: {d['gist']}")
            if d["headings"]:
                l1.append(f"- 关键小节: {' / '.join(d['headings'][:8])}")
            l1.append("")
        with open(os.path.join(DST, subkb, "L1_速查与结论.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(l1))

        # ---- L2：导航层，按子主题归类
        topics = {}
        for d in docs:
            topics.setdefault(d["subtopic"], []).append(d)
        l2 = [f"# 【{subkb}】知识库 · 第 2 层 主题索引", ""]
        l2.append(f"> 按子主题归类, 共 **{len(topics)}** 个主题, **{len(docs)}** 篇")
        l2.append("")
        for tp, ds in sorted(topics.items(), key=lambda x: -len(x[1])):
            l2.append(f"## {tp}  ({len(ds)} 篇)")
            for d in ds:
                l2.append(f"- {d['title']} → `{d['rel']}`")
            l2.append("")
        with open(os.path.join(DST, subkb, "L2_主题索引.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(l2))

    # ---- _meta：机器可读的目录 + 人类可读的说明
    os.makedirs(os.path.join(DST, "_meta"), exist_ok=True)

    catalog = {
        "kb_root": DST,
        "source": SRC,
        "sub_kbs": {
            k: {
                "desc": SUBKB_DESC.get(k, ""),
                "docs": len(v),
                "layers": ["L1_速查与结论.md", "L2_主题索引.md", "L3_原始资料/"]
            }
            for k, v in sorted(store.items(), key=lambda x: -len(x[1]))
        },
        "total_docs": copy_count,
        "total_bytes": total_bytes,
    }
    with open(os.path.join(DST, "_meta", "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    readme = ["# 知识库 · 结构说明", ""]
    readme.append(f"> 源: `{SRC}` ｜ 已摄取 **{copy_count}** 篇 / **{total_bytes/1024/1024:.2f} MB**")
    readme.append("> 结构: 每个**子知识库**独立可查; 库内分 **L1 速查 / L2 主题 / L3 原始** 三层。")
    readme.append("")
    readme.append("## 子知识库清单（可单独查询）")
    readme.append("")
    readme.append("| 子库 | 文档数 | 内容方向 | 单独查询命令 |")
    readme.append("|---|---:|---|---|")
    for k, v in sorted(store.items(), key=lambda x: -len(x[1])):
        readme.append(f"| `{k}` | {len(v)} | {SUBKB_DESC.get(k,'')} | `python kb.py query <词> -b {k}` |")
    readme.append("")
    readme.append("## 分层含义")
    readme.append("- **L1_速查与结论.md**：蒸馏层 — 每篇的标题、结论要点、关键小节，速读拿结论。")
    readme.append("- **L2_主题索引.md**：导航层 — 按子主题归类的地图，定位某主题下有哪些文档。")
    readme.append("- **L3_原始资料/**：原始层 — 从源库复制进来的完整原文，按原路径存放。")
    readme.append("")
    readme.append("## 查询方式")
    readme.append("```bash")
    kb_py = os.path.join(os.path.dirname(DST), "kb.py").replace("\\", "/")
    readme.append(f'python "{kb_py}" list                      # 列出子库')
    readme.append(f'python "{kb_py}" query "关键词"             # 全库检索')
    readme.append(f'python "{kb_py}" query "关键词" -b 子库名   # 只查某个子库')
    readme.append(f'python "{kb_py}" query "关键词" --top 8     # 限制展示条数')
    readme.append("```")
    readme.append("")
    readme.append(f"> 需要原文时按结果里的 `原文:` 路径, 到 `{DST.replace(chr(92),'/')}/<子库>/L3_原始资料/<rel>` 用编辑器打开。")
    readme.append("")
    readme.append("*本知识库由 `build_kb.py` 从源库摄取并重组, 内容随脚本重跑而更新。*")
    with open(os.path.join(DST, "_meta", "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(readme))

    # ---- 打印摘要
    print(f"知识库构建完成: {copy_count} 篇, {total_bytes/1024/1024:.2f} MB, {len(store)} 个子库")
    for k, v in sorted(store.items(), key=lambda x: -len(x[1])):
        print(f"  - {k}: {len(v)} 篇")


if __name__ == "__main__":
    main()
