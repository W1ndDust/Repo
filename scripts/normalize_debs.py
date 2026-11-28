#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deb 架构规范化（幂等，可放进 CI 前置步骤）

背景
----
Sileo 只识别 `iphoneos-arm` 与 `iphoneos-arm64` 两种架构。把包声明成
`iphoneos-arm64e` 时，客户端会判定为「本机不可安装」，并把该包单独放进
`<分组名> Packages` 这个自动分组里 —— 这正是 RootHide Packages 反复出现的
唯一原因。

规则
----
1. 架构已在白名单内 → 跳过（不改文件，不产生 diff）
2. 声明为 iphoneos-arm64e，且包内二进制确实含 arm64 切片
   → 改写 control 为 iphoneos-arm64，并重命名文件（data.tar 逐字节保留）
3. 声明为 iphoneos-arm64e，但二进制只有 arm64e
   → 保持原样，打印警告：这类包在非 arm64e 机型上装了也不会生效，
     因此客户端仍会把它放进 `<分组> Packages`；需要作者重新提供通用版

用法
----
    python3 scripts/normalize_debs.py            # 规范化 debs/
    python3 scripts/normalize_debs.py --check    # 只报告，不改文件
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEBS = ROOT / "debs"
ALLOWED = {"iphoneos-arm", "iphoneos-arm64"}
TARGET = "iphoneos-arm64"


def control_of(deb: Path) -> dict:
    out = subprocess.run(["dpkg-deb", "-f", str(deb)],
                         capture_output=True, text=True, check=True).stdout
    fields, key = {}, None
    for line in out.splitlines():
        if line[:1] in (" ", "\t") and key:
            fields[key] += "\n" + line
        elif ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            fields[key] = val
    return fields


def binary_archs(deb: Path) -> set[str]:
    """读取包内 Mach-O 的真实架构集合。只抽样前若干个二进制，够判断即可。"""
    archs: set[str] = set()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["dpkg-deb", "-x", str(deb), tmp], check=True,
                       capture_output=True)
        found = 0
        for f in Path(tmp).rglob("*"):
            if not f.is_file():
                continue
            info = subprocess.run(["file", "-b", str(f)], capture_output=True,
                                  text=True).stdout
            if "Mach-O" not in info:
                continue
            found += 1
            if re.search(r"\barm64e\b", info):
                archs.add("arm64e")
            if re.search(r"\barm64\b(?!e)", info):
                archs.add("arm64")
            if "armv7" in info:
                archs.add("armv7")
            if found >= 5:
                break
    return archs


def repack(deb: Path, arch: str) -> None:
    """只重写 control 里的 Architecture，data.tar 原样保留。"""
    subprocess.run([sys.executable, str(ROOT / "scripts" / "repack_deb.py"),
                    str(deb), str(deb) + ".tmp", f"Architecture={arch}"],
                   check=True, capture_output=True)
    fields = control_of(Path(str(deb) + ".tmp"))
    pkg, ver = fields.get("Package", ""), fields.get("Version", "")
    dest = DEBS / f"{pkg}_{ver}_{arch}.deb"
    Path(str(deb) + ".tmp").replace(dest)
    if dest != deb:
        deb.unlink()
    print(f"   改写 → {dest.name}")


def main() -> None:
    check = "--check" in sys.argv
    if not DEBS.is_dir():
        sys.exit("找不到 debs/ 目录")

    changed = skipped = warned = 0
    for deb in sorted(DEBS.glob("*.deb")):
        arch = control_of(deb).get("Architecture", "")
        if arch in ALLOWED:
            continue
        name = f"{control_of(deb).get('Package')} {control_of(deb).get('Version')}"
        real = binary_archs(deb)
        detail = "+".join(sorted(real)) or "未知"
        if "arm64" in real:
            # 不再自动改写：架构声明归作者，客户端兼容性靠分组与说明处理
            print(f"[提示] {name}: 声明 {arch}（二进制含 {detail}）—— 保持原样")
            changed += 1
        else:
            print(f"[警告] {name}: 声明 {arch}，二进制仅 {detail}。"
                  f"保持原样 —— 该包在非 arm64e 机型上无法加载，"
                  f"客户端仍会把它列入「<分组> Packages」。")
            warned += 1
            skipped += 1

    print(f"完成：{changed} 个非白名单架构（仅提示，不改写），仅 arm64e {warned} 个")
    print("说明：本脚本只做检查。架构声明由 deb 作者决定，流水线不擅自修改。")


if __name__ == "__main__":
    main()
