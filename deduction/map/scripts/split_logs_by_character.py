#!/usr/bin/env python3
"""
Log Splitter Script - 按角色拆分日志文件

此脚本读取日志文件夹中的日志文件，根据日志中的【角色名】标识，
将日志分散到不同的角色文件中，便于调试。

使用方法:
    python split_logs_by_character.py [--log-dir LOG_DIR] [--output-dir OUTPUT_DIR]

参数:
    --log-dir: 日志文件夹路径（默认为当前目录下的 log 文件夹）
    --output-dir: 输出文件夹路径（默认为 log 文件夹下的 character 文件夹）

示例:
    python split_logs_by_character.py --log-dir ./log --output-dir ./log/character
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# 用于匹配【角色名】的正则表达式
CHARACTER_PATTERN = re.compile(r'【([^】]+)】')

# 组件排序顺序（数字越小优先级越高）
COMPONENT_ORDER = {
    "perceive": 0,
    "plan": 1,
    "invoke": 2,
    "reflect": 3,
    "state": 4,
    "profile": 5,
}

# 默认组件优先级（未知组件放最后）
DEFAULT_COMPONENT_PRIORITY = 999


def extract_character_name(line: str) -> Optional[str]:
    """
    从日志行中提取角色名。

    Args:
        line: 日志行

    Returns:
        角色名，如果没有找到则返回 None
    """
    match = CHARACTER_PATTERN.search(line)
    if match:
        return match.group(1)
    return None


def extract_tick(line: str) -> Tuple[int, bool]:
    """
    从日志行中提取 tick 信息。

    Args:
        line: 日志行

    Returns:
        (tick值, 是否为有效数字) 的元组
        如果 tick 是 N/A 或无法解析，返回 (-1, False)
    """
    # 匹配第二个【】中的内容，格式：【角色名】【tick】
    matches = CHARACTER_PATTERN.findall(line)
    if len(matches) >= 2:
        tick_str = matches[1]
        if tick_str == "N/A":
            return (-1, False)
        try:
            return (int(tick_str), True)
        except ValueError:
            return (-1, False)
    return (-1, False)


def sanitize_filename(name: str) -> str:
    """
    清理文件名，移除或替换不合法的字符。

    Args:
        name: 原始文件名

    Returns:
        清理后的文件名
    """
    # 替换 Windows 文件名中不允许的字符
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, '_', name)


def collect_logs_from_file(
    log_file_path: Path,
    component_name: str,
    character_logs: Dict[str, List[Tuple[int, int, int, str]]],
    system_logs: List[str]
) -> int:
    """
    从单个日志文件收集日志到内存中。

    Args:
        log_file_path: 日志文件路径
        component_name: 组件名称（用于排序）
        character_logs: 角色日志字典（会被修改）
        system_logs: 系统日志列表（会被修改）

    Returns:
        处理的日志行数
    """
    print(f"处理日志文件: {log_file_path}")

    # 获取组件优先级
    component_priority = COMPONENT_ORDER.get(component_name, DEFAULT_COMPONENT_PRIORITY)

    line_count = 0
    # 使用 utf-8 编码，忽略无法解码的字符
    with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line_count += 1
            character_name = extract_character_name(line)

            if character_name:
                tick, _ = extract_tick(line)
                # 对于无效 tick，使用 -1，排序时会放在最前面
                if character_name not in character_logs:
                    character_logs[character_name] = []
                character_logs[character_name].append((
                    tick,
                    component_priority,
                    len(character_logs[character_name]),
                    line
                ))
            else:
                # 没有角色标识的日志归入 System
                system_logs.append(line)

    return line_count


def write_sorted_logs(
    output_dir: Path,
    character_logs: Dict[str, List[Tuple[int, int, int, str]]],
    system_logs: List[str]
) -> Dict[str, int]:
    """
    将收集的日志排序后写入文件。

    Args:
        output_dir: 输出目录路径
        character_logs: 角色日志字典
        system_logs: 系统日志列表

    Returns:
        字典，键为角色名，值为该角色的日志行数
    """
    counts: Dict[str, int] = {}

    # 写入角色日志文件
    for character_name, logs in character_logs.items():
        # 排序：先按 tick 升序（-1 排在最前），再按组件优先级，最后按原始顺序
        sorted_logs = sorted(logs, key=lambda x: (x[0], x[1], x[2]))

        safe_name = sanitize_filename(character_name)
        output_file = output_dir / f"{safe_name}.log"

        with open(output_file, 'w', encoding='utf-8') as f:
            for _, _, _, line in sorted_logs:
                f.write(line)

        counts[character_name] = len(logs)

    # 写入 System 日志
    if system_logs:
        system_file = output_dir / "System.log"
        with open(system_file, 'w', encoding='utf-8') as f:
            f.writelines(system_logs)
        counts["System"] = len(system_logs)

    return counts


def process_log_directory(log_dir: Path, output_dir: Path, keep_original: bool = True) -> None:
    """
    处理日志目录中的 agent 日志文件。

    Args:
        log_dir: 日志目录路径
        output_dir: 输出目录路径
        keep_original: 是否保留原始日志文件
    """
    if not log_dir.exists():
        print(f"错误: 日志目录不存在: {log_dir}")
        return

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)

    # 只处理 app/agent 目录，按指定顺序
    agent_dir = log_dir / "app" / "agent"
    if not agent_dir.exists():
        print(f"警告: agent 目录不存在: {agent_dir}")
        return

    # 按指定顺序处理日志文件（这个顺序决定文件处理顺序，但最终输出会按 tick 和组件顺序排序）
    component_order = ["perceive", "plan", "invoke", "reflect", "state", "profile"]
    log_files = []
    for component in component_order:
        log_file = agent_dir / f"{component}.log"
        if log_file.exists():
            log_files.append((log_file, component))

    if not log_files:
        print(f"警告: 在 {agent_dir} 中没有找到日志文件")
        return

    print(f"找到 {len(log_files)} 个日志文件")
    print(f"处理顺序: {[c for _, c in log_files]}")
    print(f"输出目录: {output_dir}")
    print("-" * 50)

    # 收集所有日志到内存
    character_logs: Dict[str, List[Tuple[int, int, int, str]]] = {}
    system_logs: List[str] = []
    total_lines = 0

    for log_file, component_name in log_files:
        print(f"处理: {log_file.name}")
        lines = collect_logs_from_file(log_file, component_name, character_logs, system_logs)
        total_lines += lines

    print("-" * 50)
    print("排序并写入文件...")

    # 排序并写入文件
    counts = write_sorted_logs(output_dir, character_logs, system_logs)

    # 打印统计信息
    print("-" * 50)
    print("拆分完成! 统计信息:")
    print(f"共处理 {total_lines} 行日志")
    print(f"共生成 {len(counts)} 个角色/系统日志文件")

    # 按日志数量排序
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    for character, count in sorted_counts:
        print(f"  {character}: {count} 行")

    print("-" * 50)
    print(f"拆分后的日志文件保存在: {output_dir}")

    if keep_original:
        print("原始日志文件已保留")


def main():
    parser = argparse.ArgumentParser(
        description="按角色拆分日志文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python split_logs_by_character.py
    python split_logs_by_character.py --log-dir ./log --output-dir ./log/character
        """
    )

    parser.add_argument(
        '--log-dir',
        type=str,
        default=None,
        help='日志文件夹路径（默认为当前目录下的 log 文件夹）'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='输出文件夹路径（默认为 log 文件夹下的 character 文件夹）'
    )

    parser.add_argument(
        '--no-keep-original',
        action='store_true',
        help='不保留原始日志文件（默认保留）'
    )

    args = parser.parse_args()

    # 确定日志目录
    if args.log_dir:
        log_dir = Path(args.log_dir)
    else:
        # 默认为当前目录下的 logs 文件夹
        log_dir = Path(__file__).parent.parent / "logs"

    # 确定输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = log_dir / "character"

    # 处理日志
    process_log_directory(
        log_dir=log_dir,
        output_dir=output_dir,
        keep_original=not args.no_keep_original
    )


if __name__ == "__main__":
    main()
