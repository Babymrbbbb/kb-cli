# kb-cli

**Zero-dependency local knowledge base with multi-sub-repo × multi-layer retrieval.**

一个从零起手的本地知识库工具链：**构建器**（`build_kb.py`）把散落的 markdown/txt 文档重组为「多子库 × 多层」结构，**检索器**（`kb.py`）在上面做召回优先的全文检索。**核心两个文件 200 多行，另附聊天记录同步脚本 sync_chat.py，零依赖，Python 3.8+ 直接跑。**

```
你的原始文档                     build_kb.py                    kb-cli 检索
~/notes/                           │                              │
~/docs/                            │  扫描 → 分类 → 复制           │  kb.py query
~/research/                        │                              │
       │                           ▼                              │
       │             多子库 × 三层结构                              │
       │             ─────────────────                            │
       │             会员体系/                                     │
       │               ├── L1_速查与结论.md   ◄─ 蒸馏层            │
       │               ├── L2_主题索引.md     ◄─ 导航层            │
       │               └── L3_原始资料/       ◄─ 原始层            │
       │             私域运营/                                       │
       │               └── ...                                      │
       │             产品研发/                                       │
       │               └── ...                                      │
       │             _meta/catalog.json                             │
       │                          ▲                                 │
       └── 重跑 build_kb.py ───────┘      python kb.py query ... ──┘
```

## 为什么做这个

日常工作里，文档越攒越多，问题不是"存不下"，是**找不到**：

- 一个 `~/notes/` 里塞着几百个 md，`grep -r` 太慢、结果太多
- 想按"子主题"快速定位（"所有关于私域运营的复盘"），单文件 grep 无能为力
- 想把"结论"和"原文"分层：先看结论速读，需要时再下钻到原文
- Windows 上 Python 脚本一 `print` 中文就 GBK 乱码，脚本没法直接跑

**kb-cli 就是为这四件事写的**：分层结构（L1/L2/L3）+ 子库拆分 + 召回优先检索 + UTF-8 强制输出。

## 核心特性

| 特性 | 说明 |
|---|---|
| **零依赖** | 只用 Python 标准库 `os` `json` `re` `shutil` `sys` `argparse` |
| **单文件检索器** | `kb.py` 一个文件 158 行，能独立跑 |
| **多子库** | 源目录按第 1 段路径自动归类到独立子库，可 `-b` 只查某个 |
| **三层结构** | L1 蒸馏 / L2 导航 / L3 原始，不同用途不同层 |
| **召回优先** | 多词 AND 匹配，任一缺失即跳过；命中按出现次数排序 |
| **UTF-8 强制** | `sys.stdout.buffer.write(text.encode('utf-8'))`，Windows 不炸 |
| **双写输出** | 控制台 + `_meta/last_result.txt`，便于程序化消费 |
| **CLI 友好** | argparse + `-b` / `--top` / `-f` 三个开关，够用且不冗余 |
| **构建即重构** | `build_kb.py` 幂等重跑，分类映射和描述集中在字典里，改一处即全局生效 |

## 快速开始

```bash
# 1. 准备源文档（放到 ./sources/ 或者改 build_kb.py 顶部的 SRC）
mkdir -p sources/私域运营 sources/会员体系
echo -e "# 我的第一份文档\n这是内容。" > sources/私域运营/first.md

# 2. 构建知识库
python build_kb.py

# 3. 检索
python kb.py list                          # 列出子库
python kb.py query "第一份文档"              # 全库检索
python kb.py query "第一份文档" -b 私域运营  # 只查某个子库
python kb.py query "关键词" --top 5         # 限制展示条数
```

## 三层结构的设计意图

**L1（速查与结论）**：蒸馏层。每篇文档一段——标题、路径、结论要点、关键小节。用途是**速读拿结论**。

**L2（主题索引）**：导航层。按子主题归类。用途是**定位某主题下有哪些文档**。

**L3（原始资料）**：原文层。从源库复制进来的完整 `.md/.txt`，保留子路径。用途是**看细节**。

三层各司其职，不互相替代。用户按需下钻：想速读就 L1，想导航就 L2，想细看就 L3。

## 检索算法（158 行实现）

```python
for t in terms:
    c = low.count(t.lower())
    if c == 0:
        ok = False  # 任一缺失即跳过（AND 逻辑）
        break
    sc += c  # 按总出现次数排序
```

**为什么不用 TF-IDF / BM25 / embedding？**

> 注：本开源版为最小实现（AND 匹配 + 词频排序）；生产环境版本在此基础上增加了 IDF 加权，用于修正泛词淹没导致 59.8% 文档被压到同一主题的问题。

- 场景是**本地、小库（几十到几千篇）、精确查找**，不是搜索引擎
- BM25 会做词频归一化和文档长度惩罚，对本场景是过度设计
- Embedding 要装 faiss / sentence-transformers，违背"零依赖"
- AND 匹配 + 出现次数排序，够快（`os.walk` 一遍 + 字符串 `count`）、够准、够稳

**召回优先原则**：多词检索时任一缺失即跳过（而不是"缺一个也返回"），但**不做去重和相似合并**——同一份文档命中多个关键词会累计分数，让"更相关"的排前面。宁可多召一条让人扫一眼，也别漏。

## UTF-8 强制输出（跨平台陷阱）

```python
def out(s=""):
    _buf.append(s + "\n")

def flush():
    text = "".join(_buf)
    sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    # 同时落盘 UTF-8 结果文件
    try:
        with open(os.path.join(KB, "_meta", "last_result.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
```

**为什么这么做？**

- Windows PowerShell / cmd 默认 GBK 编码，`print("中文")` 直接报错或乱码
- 用 `sys.stdout.buffer` 绕过编码层，直接写 UTF-8 字节
- 但**部分终端还是显示不出来**——所以额外落一份 `_meta/last_result.txt`，程序化消费时用 `open(..., encoding='utf-8')` 就能拿到原始结果
- 这个"双写"策略是本仓库最重要的工程细节，不是玄学

## 配置

`build_kb.py` 顶部两个字典决定你的知识库长什么样：

```python
CAT_MAP = {
    "会员体系": "会员体系",
    "私域运营": "私域运营",
    # 源目录第 1 段路径 → 子库名
    "(root)": "元数据库",   # 根级文件归到元数据库
}
DEFAULT_SUBKB = "其他"     # 未匹配的分类默认归这里

SUBKB_DESC = {
    "会员体系": "会员分层、储值、积分、会员日活动方案与复盘",
    # 子库一句话说明，写进 _meta/README.md
}
```

**改这两个字典就能适配任何领域**：换成"代码规范 / 需求文档 / 事故复盘"、"论文 / 综述 / 数据集"、"用户故事 / PRD / 技术选型"…… 结构完全一样。

## 目录结构

```
kb-cli/
├── kb.py              # 检索器（单文件 158 行）
├── build_kb.py        # 构建器（从源库重组为三层结构）
├── kb/                # 构建产物目录
│   └── _meta/
│       ├── README.md      # 结构说明
│       └── catalog.json   # 机器可读子库清单
├── examples/          # 示例源文档（跑一遍 build_kb.py 试试）
├── .gitignore
├── LICENSE
└── README.md
```

## 示例：从零跑起来

```bash
# 1. 准备示例源文档（仓库自带）
ls examples/
# └── 私域运营/
# │     └── 首次搭建.md
# └── 会员体系/
#       └── 会员分层.md

# 2. 复制示例到 sources/
cp -r examples/* sources/

# 3. 构建
python build_kb.py
# 知识库构建完成: 2 篇, 0.00 MB, 2 个子库
#   - 会员体系: 1 篇
#   - 私域运营: 1 篇

# 4. 检索
python kb.py list
# 子知识库(2个):
#   会员体系     1 篇  (query: kb.py query <词> -b 会员体系)
#   私域运营     1 篇  (query: kb.py query <词> -b 私域运营)

python kb.py query "分层"
# 检索: 分层  ->  命中 1 篇, 展示 1 条
# 1. 【会员体系】会员分层方案
#    原文: 会员体系/会员分层.md
#    会员分三层: 普通会员 / 银卡 / 金卡, 对应不同折扣和权益。
#    相关度: 3
```

## 🔄 自动同步聊天记录

从微信/企微/社群导出的聊天记录（.txt/.md），自动分类到不同子库，定时同步。

### 快速开始

```bash
# 1. 准备聊天记录导出目录
mkdir -p chat_exports
# 把导出的聊天记录放到这里，文件名格式建议：群名_日期.txt
# 例：会员群_20260929.txt  运营讨论_20260928.md

# 2. 同步到知识库
python sync_chat.py                          # 使用默认配置
python sync_chat.py --source ~/chat_exports   # 指定源目录
python sync_chat.py --dry-run                 # 只扫描，不写入

# 3. 重新构建知识库索引
python build_kb.py

# 4. 检索
python kb.py query "会员" -b 会员体系
```

### 分类规则

`sync_chat.py` 底部内置分类规则，按关键词自动归类：

| 子库 | 关键词 |
|---|---|
| 会员体系 | 会员、积分、储值、等级、VIP、权益、生日 |
| 私域运营 | 社群、朋友圈、私域、裂变、打卡、群运营、互动 |
| 产品研发 | 新品、研发、配方、口味、供应链、原料、测试 |
| 竞品分析 | 竞品、对比、市场、价格、金粒门、玛芝莲、法大吉 |
| 营销文案 | 文案、海报、物料、宣传、活动、促销、节日 |
| 门店管理 | 门店、店长、员工、排班、培训、巡检、卫生 |
| 聊天记录（默认） | 未匹配到以上关键词 |

**自定义规则**：编辑 `sync_chat.py` 底部的 `SYNC_CONFIG["classification_rules"]` 字典。

### 定时同步（每日自动）

**Windows 任务计划**：

```powershell
# 创建每日 9:00 自动同步任务
schtasks /create /tn "KB Chat Sync" /tr "python C:\path\to\kb-cli\sync_chat.py" /sc daily /st 09:00
```

**cron（Linux/Mac）**：

```bash
# 每日 9:00 同步
0 9 * * * cd /path/to/kb-cli && python sync_chat.py >> sync.log 2>&1
```

### 文件格式建议

微信/企微导出的聊天记录通常是 .txt 文件，格式示例：

```
[2026-09-29 09:15] 张三：新品上市了，大家看看
[2026-09-29 09:16] 李四：好，我转发到社群
[2026-09-29 09:17] 王五：海报做好了，发到朋友圈吧
```

文件名建议包含群名和日期：`会员群_20260929.txt`，方便自动提取元数据。

### 同步流程

```
chat_exports/                    sync_chat.py                    kb/
├── 会员群_20260929.txt  ──→  扫描 → 分类 → 写入  ──→  会员体系/
├── 运营讨论_20260928.md  ──→                    ──→  私域运营/
└── 产品测试_20260927.txt  ──→                    ──→  产品研发/

                              ↓
                    python build_kb.py  (重新构建索引)
```

## Trade-offs & Known Limitations

- **不做增量更新**：每次 `build_kb.py` 都全量重建，几百到几千篇文档时秒级完成；上万篇要考虑增量
- **不做权限**：所有子库对所有调用方开放，适合个人/本地；团队场景要包一层权限
- **AND 匹配严格**：多词检索时任一缺失即跳过。搜索"星巴克 蜜雪冰城"要求两个词都在同一份文档里；如果要"或"逻辑，请一次只查一个词，或用外部工具（`grep -E 'A|B'`）
- **不处理大文件**：`f.read()` 一次读完，单文件 > 100MB 会 OOM。真实知识库里单文件通常 < 10MB，够
- **中文分词**：不做。字符串 `count` 是子串匹配，天然支持中文；但"AI"和"人工智能"不会被认为同义词
- **跨平台**：`os.sep` 和路径处理都做了 Windows/Linux 兼容，但没在 macOS 上实测过

## 相关项目

- [`sensenova-gateway`](https://github.com/Babymrbbbb/my-sensenova-gateway) — 姊妹项目：本地 OpenAI 兼容网关，多 key 池 + 配额管理，同样零依赖

## License

MIT © Babymrbbbb
