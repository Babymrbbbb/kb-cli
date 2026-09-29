#!/usr/bin/env python3
"""
sync_chat.py - 自动同步聊天记录到知识库

功能：
1. 从指定目录抓取聊天记录（.txt/.md 文件）
2. 智能分类到不同子库（基于关键词匹配）
3. 定时运行（配合 Windows 任务计划或 cron）

使用：
    python sync_chat.py                          # 使用默认配置
    python sync_chat.py --source ~/chat_exports   # 指定源目录
    python sync_chat.py --kb ~/kb                 # 指定知识库目录
    python sync_chat.py --dry-run                 # 只扫描，不写入

配置：
    编辑本文件底部的 SYNC_CONFIG 字典，或直接修改 --source/--kb 参数
"""

import os
import sys
import shutil
import json
from datetime import datetime
from pathlib import Path

# ============ 配置区（按需修改）============

SYNC_CONFIG = {
    # 源目录：聊天记录导出目录（微信/企微导出的 txt/md 文件）
    "source_dir": "./chat_exports",
    
    # 知识库目录：kb-cli 构建的知识库
    "kb_dir": "./kb",
    
    # 分类规则：关键词 -> 子库名
    "classification_rules": {
        "会员体系": ["会员", "积分", "储值", "等级", "VIP", "权益", "生日"],
        "私域运营": ["社群", "朋友圈", "私域", "裂变", "打卡", "群运营", "互动"],
        "产品研发": ["新品", "研发", "配方", "口味", "供应链", "原料", "测试"],
        "竞品分析": ["竞品", "对比", "市场", "价格", "竞品A", "竞品B", "竞品C"],
        "营销文案": ["文案", "海报", "物料", "宣传", "活动", "促销", "节日"],
        "门店管理": ["门店", "店长", "员工", "排班", "培训", "巡检", "卫生"],
    },
    
    # 默认子库（未匹配到关键词时）
    "default_subkb": "聊天记录",
    
    # 文件扩展名
    "file_extensions": [".txt", ".md", ".json"],
    
    # 最大文件大小（MB）
    "max_file_size_mb": 50,
    
    # 是否覆盖已存在的文件
    "overwrite": False,
}

# ============ 核心逻辑 ============

def load_config(args):
    """加载配置，命令行参数优先"""
    config = dict(SYNC_CONFIG)
    
    if args.get("source"):
        config["source_dir"] = args["source"]
    if args.get("kb"):
        config["kb_dir"] = args["kb"]
    if args.get("dry_run"):
        config["dry_run"] = True
    
    return config


def classify_file(content, rules):
    """根据内容关键词分类到子库"""
    content_lower = content.lower()
    scores = {}
    
    for subkb, keywords in rules.items():
        score = sum(1 for kw in keywords if kw.lower() in content_lower)
        if score > 0:
            scores[subkb] = score
    
    if scores:
        # 返回得分最高的子库
        return max(scores, key=scores.get)
    
    return None


def extract_chat_metadata(filepath):
    """提取聊天记录元数据（时间、群名等）"""
    metadata = {
        "source_file": str(filepath),
        "size": os.path.getsize(filepath),
        "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat(),
        "extension": filepath.suffix.lower(),
    }
    
    # 尝试从文件名提取群名/日期
    name_parts = filepath.stem.split("_")
    if len(name_parts) >= 2:
        metadata["group_name"] = name_parts[0]
        if name_parts[-1].isdigit() and len(name_parts[-1]) == 8:
            metadata["date"] = name_parts[-1]
    
    return metadata


def process_chat_file(filepath, config, dry_run=False):
    """处理单个聊天记录文件"""
    filepath = Path(filepath)
    
    # 检查文件大小
    if filepath.stat().st_size > config["max_file_size_mb"] * 1024 * 1024:
        print(f"  ⚠️  跳过（文件过大）: {filepath.name}")
        return None
    
    # 读取内容
    try:
        content = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = filepath.read_text(encoding="gbk")
        except:
            print(f"  ⚠️  跳过（编码错误）: {filepath.name}")
            return None
    
    # 分类
    subkb = classify_file(content, config["classification_rules"])
    if not subkb:
        subkb = config["default_subkb"]
    
    # 提取元数据
    metadata = extract_chat_metadata(filepath)
    metadata["subkb"] = subkb
    
    # 构建目标路径
    kb_dir = Path(config["kb_dir"])
    subkb_dir = kb_dir / subkb
    target_path = subkb_dir / filepath.name
    
    if dry_run:
        print(f"  🔍 [DRY RUN] {filepath.name} -> {subkb}/")
        return metadata
    
    # 检查是否已存在
    if target_path.exists() and not config["overwrite"]:
        print(f"  ⏭️  跳过（已存在）: {filepath.name}")
        return None
    
    # 创建子库目录
    subkb_dir.mkdir(parents=True, exist_ok=True)
    
    # 写入文件（加元数据头）
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(f"# {filepath.stem}\n")
        f.write(f"来源: {metadata['source_file']}\n")
        f.write(f"时间: {metadata['modified']}\n")
        if metadata.get("group_name"):
            f.write(f"群组: {metadata['group_name']}\n")
        if metadata.get("date"):
            f.write(f"日期: {metadata['date']}\n")
        f.write("\n---\n\n")
        f.write(content)
    
    print(f"  ✅ {filepath.name} -> {subkb}/")
    return metadata


def sync_chat_records(config):
    """同步聊天记录到知识库"""
    source_dir = Path(config["source_dir"])
    kb_dir = Path(config["kb_dir"])
    
    print(f"\n{'='*60}")
    print(f"📋 聊天记录同步")
    print(f"{'='*60}")
    print(f"源目录: {source_dir}")
    print(f"知识库: {kb_dir}")
    print(f"模式: {'DRY RUN' if config.get('dry_run') else '正常同步'}")
    print(f"{'='*60}\n")
    
    # 检查源目录
    if not source_dir.exists():
        print(f"❌ 源目录不存在: {source_dir}")
        print(f"   请先创建目录并放入聊天记录文件（.txt/.md）")
        print(f"   示例: mkdir {source_dir}")
        return {"synced": 0, "skipped": 0, "errors": 0}
    
    # 扫描文件
    files = []
    for ext in config["file_extensions"]:
        files.extend(source_dir.glob(f"*{ext}"))
    
    if not files:
        print(f"⚠️  源目录没有可同步的文件: {source_dir}")
        print(f"   支持的文件格式: {', '.join(config['file_extensions'])}")
        return {"synced": 0, "skipped": 0, "errors": 0}
    
    print(f"📁 发现 {len(files)} 个文件\n")
    
    # 处理文件
    stats = {"synced": 0, "skipped": 0, "errors": 0}
    
    for filepath in sorted(files):
        try:
            result = process_chat_file(filepath, config, config.get("dry_run", False))
            if result:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            print(f"  ❌ 错误: {filepath.name} - {e}")
            stats["errors"] += 1
    
    # 打印统计
    print(f"\n{'='*60}")
    print(f"📊 同步完成")
    print(f"   ✅ 成功: {stats['synced']}")
    print(f"   ⏭️  跳过: {stats['skipped']}")
    print(f"   ❌ 错误: {stats['errors']}")
    print(f"{'='*60}\n")
    
    # 如果是正常模式，提示重新构建知识库
    if stats["synced"] > 0 and not config.get("dry_run"):
        print("💡 提示: 运行 `python build_kb.py` 重新构建知识库索引")
    
    return stats


def print_classification_rules(rules):
    """打印分类规则"""
    print("\n📋 分类规则:")
    print("-" * 40)
    for subkb, keywords in rules.items():
        print(f"  {subkb}: {', '.join(keywords)}")
    print("-" * 40)


def parse_args():
    """解析命令行参数"""
    args = {}
    
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--source" and i < len(sys.argv) - 1:
            args["source"] = sys.argv[i + 1]
        elif arg == "--kb" and i < len(sys.argv) - 1:
            args["kb"] = sys.argv[i + 1]
        elif arg == "--dry-run":
            args["dry_run"] = True
        elif arg == "--help" or arg == "-h":
            args["help"] = True
        elif arg == "--rules":
            args["rules"] = True
    
    return args


def main():
    """主入口"""
    args = parse_args()
    
    if args.get("help"):
        print(__doc__)
        sys.exit(0)
    
    if args.get("rules"):
        print_classification_rules(SYNC_CONFIG["classification_rules"])
        sys.exit(0)
    
    config = load_config(args)
    
    # 打印配置
    print(f"\n🔧 配置:")
    print(f"   源目录: {config['source_dir']}")
    print(f"   知识库: {config['kb_dir']}")
    print(f"   默认子库: {config['default_subkb']}")
    print(f"   覆盖模式: {'是' if config['overwrite'] else '否'}\n")
    
    # 执行同步
    stats = sync_chat_records(config)
    
    # 返回退出码
    if stats["errors"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
