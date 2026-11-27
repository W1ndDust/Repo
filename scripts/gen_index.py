#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描 debs/ 下的 .deb，生成 APT 源索引：
  Packages / Packages.gz / Release / packages.json (给网页用)

分组（Section）逻辑，优先级从高到低：
  1. scripts/sections.json 里的显式指定  {"com.foo.bar": "RootHide"}
  2. .deb 的 control 里 Section 恰好等于配置里的分组名
  3. package id / 文件名 / Name / Depends / Description 里出现 roothide → RootHide
  4. 出现 rootless → RootLess
  5. 兜底 default_section（RootLess）

用法: python3 scripts/gen_index.py [仓库根目录]
依赖: python3 + dpkg-deb (Alpine: apk add dpkg; Ubuntu 自带)
"""
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
DEBS = ROOT / "debs"
CFG = json.loads((ROOT / "scripts" / "config.json").read_text(encoding="utf-8"))
SECTIONS = CFG.get("sections") or ["RootLess"]
DEFAULT_SECTION = CFG.get("default_section") or SECTIONS[0]

OVERRIDE_FILE = ROOT / "scripts" / "sections.json"
OVERRIDE = {}
if OVERRIDE_FILE.exists():
    try:
        OVERRIDE = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as e:
        sys.exit(f"sections.json 格式错误: {e}")

FIELDS = [
    "Package", "Name", "Version", "Architecture", "Section", "Priority",
    "Maintainer", "Author", "Depends", "Pre-Depends", "Conflicts", "Replaces",
    "Provides", "Homepage", "Tag",
]


def classify(deb: Path, c: dict) -> str:
    pid = c.get("Package", "")
    if pid in OVERRIDE:
        want = OVERRIDE[pid]
        return want if want in SECTIONS else DEFAULT_SECTION
    if c.get("Section") in SECTIONS:
        return c["Section"]
    blob = " ".join([
        pid, deb.name, c.get("Name", ""), c.get("Depends", ""),
        c.get("Description", ""),
    ]).lower()
    if "roothide" in blob or "root hide" in blob or "root-hide" in blob:
        return "RootHide" if "RootHide" in SECTIONS else DEFAULT_SECTION
    if "rootless" in blob:
        return "RootLess" if "RootLess" in SECTIONS else DEFAULT_SECTION
    return DEFAULT_SECTION


def control_of(deb: Path) -> dict:
    out = subprocess.run(["dpkg-deb", "-f", str(deb)],
                         capture_output=True, text=True, check=True).stdout
    fields, key = {}, None
    for line in out.splitlines():
        if line[:1] in (" ", "\t") and key:      # 多行 Description 续行
            fields[key] += "\n" + line
        elif ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            fields[key] = val
    return fields


def hashes(deb: Path) -> dict:
    data = deb.read_bytes()
    return {"Size": len(data),
            "MD5sum": hashlib.md5(data).hexdigest(),
            "SHA1": hashlib.sha1(data).hexdigest(),
            "SHA256": hashlib.sha256(data).hexdigest()}


def main():
    if not DEBS.is_dir():
        sys.exit(f"找不到目录: {DEBS}")
    debs = sorted(DEBS.glob("*.deb"))
    if not debs:
        print("⚠️  debs/ 里没有 .deb，生成空索引（源仍可正常添加）")

    items = []
    for deb in debs:
        c = control_of(deb)
        c["Section"] = classify(deb, c)
        items.append((SECTIONS.index(c["Section"]), deb, c))
    items.sort(key=lambda x: (x[0], x[2].get("Name", x[2].get("Package", ""))))

    stanzas, web = [], []
    cur_section = None
    for _, deb, c in items:
        if c["Section"] != cur_section:
            cur_section = c["Section"]
            print(f"\n[{cur_section}]")
        rel = f"./debs/{deb.name}"
        h = hashes(deb)
        lines = []
        for f in FIELDS:
            if c.get(f):
                lines.append(f"{f}: {c[f]}")
        lines.append(f"Filename: {rel}")
        lines.append(f"Size: {h['Size']}")
        if c.get("Installed-Size"):
            lines.append(f"Installed-Size: {c['Installed-Size']}")
        lines.append(f"MD5sum: {h['MD5sum']}")
        lines.append(f"SHA1: {h['SHA1']}")
        lines.append(f"SHA256: {h['SHA256']}")
        # SileoDepiction：Sileo 读取小写 key `sileodepiction`（PackageListManager.swift:160）
        dep_json = ROOT / "depictions" / f"{c['Package']}.json"
        has_dep = dep_json.exists()
        depiction = f"{CFG['base_url']}depictions/{c['Package']}.json"
        if has_dep:
            lines.append(f"SileoDepiction: {depiction}")
        if c.get("Description"):
            lines.append(f"Description: {c['Description']}")
        stanzas.append("\n".join(lines) + "\n")

        web.append({
            "package": c.get("Package", ""),
            "name": c.get("Name") or c.get("Package", ""),
            "version": c.get("Version", ""),
            "arch": c.get("Architecture", ""),
            "section": c["Section"],
            "author": c.get("Author") or c.get("Maintainer", ""),
            "description": c.get("Description", "").replace("\n ", "\n").strip(),
            "size": h["Size"],
            "file": deb.name,
            "filename": rel,
            "depiction": depiction if has_dep else "",
        })
        print(f"  + {c.get('Package')} {c.get('Version','')} [{c.get('Architecture','')}]")

    pkg_text = "\n".join(stanzas)
    (ROOT / "Packages").write_text(pkg_text, encoding="utf-8")
    with open(ROOT / "Packages.gz", "wb") as fh:
        # mtime=0 → 输出确定，内容不变时不会产生无意义的 commit
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as f:
            f.write(pkg_text.encode("utf-8"))

    release = "\n".join([
        f"Origin: {CFG['origin']}",
        f"Label: {CFG['label']}",
        f"Suite: {CFG['suite']}",
        f"Version: {CFG['version']}",
        f"Codename: {CFG['codename']}",
        "Components: main",
        "Architectures: " + " ".join(CFG["architectures"]),
        "Sections: " + " ".join(SECTIONS),
        f"Icon: {CFG['icon']}",
        f"Description: {CFG['description']}",
    ]) + "\n"
    (ROOT / "Release").write_text(release, encoding="utf-8")

    # 网页数据由 web/build.py 直接从 Packages 生成，这里不再另写一份
    counts = {s: sum(1 for p in web if p["section"] == s) for s in SECTIONS}
    print("\n✅ 索引已生成：" + "，".join(f"{s} {n} 个" for s, n in counts.items()))


if __name__ == "__main__":
    main()
