#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DustDrift 数据层：把 APT 索引解析为经过校验的网页数据。

输入：仓库根目录的 `Packages`（唯一真源）+ `Release` + `scripts/config.json`
输出：`data/packages.json`

校验失败即中止（非零退出），绝不产出半成品数据。校验项见 validate()。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APT_PACKAGES = ROOT / "Packages"
APT_RELEASE = ROOT / "Release"
CONFIG = ROOT / "scripts" / "config.json"
OUT = ROOT / "data" / "packages.json"

# 环境 → 展示名（分类规则见 scripts/gen_index.py classify()：按包内安装路径判定）
ENV_LABEL = {"RootLess": "Rootless", "RootLess Packages": "Rootless",
             "RootHide": "RootHide", "System": "System", "TrollStore": "TrollStore"}


def parse_deb822(text: str) -> list[dict]:
    out, cur, key = [], {}, None
    for line in text.splitlines():
        if not line.strip():
            if cur:
                out.append(cur)
                cur, key = {}, None
            continue
        if line[0] in " \t" and key:
            cur[key] += "\n" + line
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            cur[key.strip()] = val.strip()
    if cur:
        out.append(cur)
    return out


def human_size(n) -> str:
    try:
        n = int(str(n))
    except (TypeError, ValueError):
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1048576:.1f} MB"


def slug(pkg_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", lambda m: "-%02x" % ord(m.group(0)), pkg_id)


def load():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    release = {}
    for line in APT_RELEASE.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            release[k.strip()] = v.strip()
    stanzas = parse_deb822(APT_PACKAGES.read_text(encoding="utf-8"))
    return cfg, release, stanzas


def validate(stanzas: list[dict], sections: list[str]) -> None:
    """硬校验：任何一条不通过都退出，并给出可定位的错误。"""
    errors = []
    arm64e: set[str] = set()
    seen = set()
    for s in stanzas:
        pid = s.get("Package", "")
        for field in ("Package", "Version", "Architecture", "Filename", "Size"):
            if not s.get(field):
                errors.append(f"{pid or '(无 ID)'}: 缺少必需字段 {field}")
        if pid in seen:
            errors.append(f"{pid}: Package ID 重复")
        seen.add(pid)

        fn = s.get("Filename", "").lstrip("./")
        deb = ROOT / fn
        if not deb.is_file():
            errors.append(f"{pid}: Filename 指向的文件不存在 → {fn}")
        else:
            if deb.stat().st_size != int(s.get("Size", -1)):
                errors.append(f"{pid}: Size 与文件实际大小不一致")
            if s.get("SHA256"):
                import hashlib
                actual = hashlib.sha256(deb.read_bytes()).hexdigest()
                if actual != s["SHA256"]:
                    errors.append(f"{pid}: SHA256 不一致")

        if s.get("Section") and s["Section"] not in sections:
            errors.append(f"{pid}: Section「{s['Section']}」不在配置分组 {sections} 内")

        arch = s.get("Architecture", "")
        if arch not in ("iphoneos-arm", "iphoneos-arm64"):
            arm64e.add(pid)

    if arm64e:
        print(f"ℹ️  {len(arm64e)} 个包声明 iphoneos-arm64e")

    if errors:
        print("❌ 数据校验失败：", file=sys.stderr)
        for e in errors:
            print("   -", e, file=sys.stderr)
        sys.exit(1)


def build() -> dict:
    cfg, release, stanzas = load()
    sections = cfg.get("sections") or ["RootLess"]
    labels = cfg.get("section_labels") or {}
    validate(stanzas, sections)

    packages = []
    for s in sorted(stanzas, key=lambda x: x.get("Name", "")):
        desc = s.get("Description", "")
        lines = desc.split("\n")
        summary = lines[0].strip()
        body = "\n".join(l.strip() for l in lines[1:]).strip()
        # 索引中省略 Section 的 arm64e 包，网页侧按约定显示为 RootHide Packages
        sec = s.get("Section") or ("RootHide Packages" if s.get("Architecture") == "iphoneos-arm64e" else "未分类")
        packages.append({
            "package": s["Package"],
            "slug": slug(s["Package"]),
            "name": s.get("Name") or s["Package"],
            "version": s.get("Version", ""),
            "architecture": s.get("Architecture", ""),
            "section": sec,
            "env": ENV_LABEL.get(sec, sec),
            "section_label": labels.get(sec, sec),
            "summary": summary,
            "description": body,
            "maintainer": s.get("Maintainer", ""),
            "author": s.get("Author", ""),
            "depends": [d.strip() for d in s.get("Depends", "").split(",") if d.strip()],
            "filename": s.get("Filename", "").lstrip("./"),
            "size": int(s.get("Size", 0)),
            "size_label": human_size(s.get("Size")),
            "sha256": s.get("SHA256", ""),
            "homepage": s.get("Homepage", ""),
            "changelog": f"depictions/changelogs/{s['Package']}.md",
        })

    counts = {sec: sum(1 for p in packages if p["section"] == sec) for sec in sections}
    return {
        "repo": {
            "label": release.get("Label") or cfg.get("label"),
            "description": release.get("Description") or cfg.get("description", ""),
            "url": cfg.get("base_url", ""),
            "sections": sections,
            "labels": labels,
        },
        "stats": {
            "total": len(packages),
            "by_section": counts,
        },
        "packages": packages,
    }


def main() -> None:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c = data["stats"]
    detail = "，".join(f"{k} {v}" for k, v in c["by_section"].items())
    print(f"✅ 数据层：{c['total']} 个包（{detail}）→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
