#!/usr/bin/env python3
"""
Log Splitter Script - Split log files by character

This script reads log files in the log folder and distributes them into different
character files based on the [Character Name] identifier in the logs, making debugging easier.

Usage:
    python split_logs_by_character.py [--log-dir LOG_DIR] [--output-dir OUTPUT_DIR]

Arguments:
    --log-dir: Log folder path (default is the log folder in the current directory)
    --output-dir: Output folder path (default is the character folder inside the log folder)

Example:
    python split_logs_by_character.py --log-dir ./log --output-dir ./log/character
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Regular expression to match [Character Name]
CHARACTER_PATTERN = re.compile(r'【([^】]+)】')

# Component sorting order (smaller number means higher priority)
COMPONENT_ORDER = {
    "perceive": 0,
    "plan": 1,
    "invoke": 2,
    "reflect": 3,
    "state": 4,
    "profile": 5,
}

# Default component priority (unknown components go last)
DEFAULT_COMPONENT_PRIORITY = 999


def extract_character_name(line: str) -> Optional[str]:
    """
    Extract character name from a log line.

    Args:
        line: Log line

    Returns:
        Character name, or None if not found
    """
    match = CHARACTER_PATTERN.search(line)
    if match:
        return match.group(1)
    return None


def extract_tick(line: str) -> Tuple[int, bool]:
    """
    Extract tick information from a log line.

    Args:
        line: Log line

    Returns:
        A tuple of (tick value, is valid number)
        If tick is N/A or cannot be parsed, returns (-1, False)
    """
    # Match the content in the second 【】, format: 【Character Name】【tick】
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
    Clean filename, remove or replace illegal characters.

    Args:
        name: Original filename

    Returns:
        Cleaned filename
    """
    # Replace characters not allowed in Windows filenames
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, '_', name)


def collect_logs_from_file(
    log_file_path: Path,
    component_name: str,
    character_logs: Dict[str, List[Tuple[int, int, int, str]]],
    system_logs: List[str]
) -> int:
    """
    Collect logs from a single log file into memory.

    Args:
        log_file_path: Log file path
        component_name: Component name (used for sorting)
        character_logs: Character logs dictionary (will be modified)
        system_logs: System logs list (will be modified)

    Returns:
        Number of processed log lines
    """
    print(f"Processing log file: {log_file_path}")

    # Get component priority
    component_priority = COMPONENT_ORDER.get(component_name, DEFAULT_COMPONENT_PRIORITY)

    line_count = 0
    # Use utf-8 encoding, ignore characters that cannot be decoded
    with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line_count += 1
            character_name = extract_character_name(line)

            if character_name:
                tick, _ = extract_tick(line)
                # Use -1 for invalid tick, it will be placed first when sorting
                if character_name not in character_logs:
                    character_logs[character_name] = []
                character_logs[character_name].append((
                    tick,
                    component_priority,
                    len(character_logs[character_name]),
                    line
                ))
            else:
                # Logs without character identifiers fall into System
                system_logs.append(line)

    return line_count


def write_sorted_logs(
    output_dir: Path,
    character_logs: Dict[str, List[Tuple[int, int, int, str]]],
    system_logs: List[str]
) -> Dict[str, int]:
    """
    Sort the collected logs and write to files.

    Args:
        output_dir: Output directory path
        character_logs: Character logs dictionary
        system_logs: System logs list

    Returns:
        Dictionary, keys are character names, values are log line counts for that character
    """
    counts: Dict[str, int] = {}

    # Write character log files
    for character_name, logs in character_logs.items():
        # Sort: first by tick ascending (-1 at the front), then by component priority, finally by original order
        sorted_logs = sorted(logs, key=lambda x: (x[0], x[1], x[2]))

        safe_name = sanitize_filename(character_name)
        output_file = output_dir / f"{safe_name}.log"

        with open(output_file, 'w', encoding='utf-8') as f:
            for _, _, _, line in sorted_logs:
                f.write(line)

        counts[character_name] = len(logs)

    # Write System log
    if system_logs:
        system_file = output_dir / "System.log"
        with open(system_file, 'w', encoding='utf-8') as f:
            f.writelines(system_logs)
        counts["System"] = len(system_logs)

    return counts


def process_log_directory(log_dir: Path, output_dir: Path, keep_original: bool = True) -> None:
    """
    Process agent log files in the log directory.

    Args:
        log_dir: Log directory path
        output_dir: Output directory path
        keep_original: Whether to keep the original log files
    """
    if not log_dir.exists():
        print(f"Error: Log directory does not exist: {log_dir}")
        return

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Only process app/agent directory, in specified order
    agent_dir = log_dir / "app" / "agent"
    if not agent_dir.exists():
        print(f"Warning: agent directory does not exist: {agent_dir}")
        return

    # Process log files in specified order (this determines file processing order, but final output will be sorted by tick and component order)
    component_order = ["perceive", "plan", "invoke", "reflect", "state", "profile"]
    log_files = []
    for component in component_order:
        log_file = agent_dir / f"{component}.log"
        if log_file.exists():
            log_files.append((log_file, component))

    if not log_files:
        print(f"Warning: No log files found in {agent_dir}")
        return

    print(f"Found {len(log_files)} log files")
    print(f"Processing order: {[c for _, c in log_files]}")
    print(f"Output directory: {output_dir}")
    print("-" * 50)

    # Collect all logs into memory
    character_logs: Dict[str, List[Tuple[int, int, int, str]]] = {}
    system_logs: List[str] = []
    total_lines = 0

    for log_file, component_name in log_files:
        print(f"Processing: {log_file.name}")
        lines = collect_logs_from_file(log_file, component_name, character_logs, system_logs)
        total_lines += lines

    print("-" * 50)
    print("Sorting and writing to files...")

    # Sort and write to files
    counts = write_sorted_logs(output_dir, character_logs, system_logs)

    # Print statistics
    print("-" * 50)
    print("Splitting complete! Statistics:")
    print(f"Total processed {total_lines} log lines")
    print(f"Total generated {len(counts)} character/system log files")

    # Sort by log count
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    for character, count in sorted_counts:
        print(f"  {character}: {count} lines")

    print("-" * 50)
    print(f"Split log files saved at: {output_dir}")

    if keep_original:
        print("Original log files have been kept")


def main():
    parser = argparse.ArgumentParser(
        description="Split log files by character",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python split_logs_by_character.py
    python split_logs_by_character.py --log-dir ./log --output-dir ./log/character
        """
    )

    parser.add_argument(
        '--log-dir',
        type=str,
        default=None,
        help='Log folder path (default is the logs folder in the current directory)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output folder path (default is the character folder inside the logs folder)'
    )

    parser.add_argument(
        '--no-keep-original',
        action='store_true',
        help='Do not keep original log files (default is to keep)'
    )

    args = parser.parse_args()

    # Determine log directory
    if args.log_dir:
        log_dir = Path(args.log_dir)
    else:
        # Default is logs folder under parent directory
        log_dir = Path(__file__).parent.parent / "logs"

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = log_dir / "character"

    # Process logs
    process_log_directory(
        log_dir=log_dir,
        output_dir=output_dir,
        keep_original=not args.no_keep_original
    )


if __name__ == "__main__":
    main()
