#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DustDrift-Repo 站点构建器（无第三方依赖）

数据来源：仓库根目录的 APT 索引 `Packages` + `Release`（不为网页单独维护一份数据）。
输出：仓库根目录下的白名单文件（Pages 直接服务 main 分支根目录）：
    index.html  404.html  browse/index.html  add/index.html
    p/<package>/index.html  assets/*  data/*

安全性：本脚本只会写上述白名单路径；任何情况下都不会触碰
Packages / Packages.gz / Release / debs/。

用法：
    python3 web/build.py            # 生成到仓库根目录
    python3 web/build.py --check    # 只校验 APT 文件未变，不写盘
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
TPL = WEB / "templates"
ASSETS = WEB / "assets"

APT_FILES = ["Packages", "Packages.gz", "Release"]

ARCH_LABEL = {
    "iphoneos-arm64": "rootless",
    "iphoneos-arm": "rootful",
}


# ────────────────────────── 读取 APT 索引 ──────────────────────────
def parse_deb822(text: str) -> list[dict]:
    """解析 Packages（RFC822 风格），多行字段按续行拼接。"""
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


def load_release() -> dict:
    p = ROOT / "Release"
    if not p.exists():
        sys.exit("构建失败：找不到 Release —— 这不是 APT 源目录？")
    meta = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def load_config() -> dict:
    p = ROOT / "scripts" / "config.json"
    if not p.exists():
        sys.exit("构建失败：找不到 scripts/config.json")
    return json.loads(p.read_text(encoding="utf-8"))


def load_packages() -> list[dict]:
    p = ROOT / "Packages"
    if not p.exists():
        sys.exit("构建失败：找不到 Packages 索引；先运行 python3 scripts/gen_index.py .")
    pkgs = parse_deb822(p.read_text(encoding="utf-8"))
    if not pkgs:
        # 空源是合法状态，但必须是"真的空"，不能悄悄生成假数据
        return []
    for pkg in pkgs:
        for required in ("Package", "Version", "Architecture"):
            if not pkg.get(required):
                sys.exit(f"构建失败：{pkg.get('Filename','?')} 缺少 {required} 字段")
    return pkgs


def human_size(n: str | int | None) -> str:
    try:
        n = int(str(n))
    except (TypeError, ValueError):
        return "未提供"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1048576:.1f} MB"


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def slug(pkg_id: str) -> str:
    """包标识符 → 目录名；只允许安全字符，其余转义，防止路径穿越。"""
    return re.sub(r"[^A-Za-z0-9._-]", lambda m: "-%02x" % ord(m.group(0)), pkg_id)


# ────────────────────────── 渲染 ──────────────────────────
def render(tpl_name: str, /, **ctx) -> str:
    tpl = (TPL / tpl_name).read_text(encoding="utf-8")
    out = tpl
    for k, v in ctx.items():
        out = out.replace("{{%s}}" % k, str(v))
    # 未替换的占位符说明是模板 bug，直接失败而不是发出半成品
    left = re.findall(r"\{\{[a-z_]+\}\}", out)
    if left:
        sys.exit(f"构建失败：模板 {tpl_name} 存在未替换的占位符 {sorted(set(left))}")
    return out


def asset_version() -> str:
    h = hashlib.sha256()
    for f in sorted(ASSETS.iterdir()):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


def page_shell(title: str, desc: str, body: str, root: str, active: str, repo: dict) -> str:
    nav = {
        "home": root,
        "browse": root + "browse/",
        "add": root + "add/",
    }
    marks = {k: (' aria-current="page"' if k == active else "") for k in nav}
    return render(
        "base.html",
        title=title,
        desc=desc,
        label=esc(repo["label"]),
        root=root,
        body=body,
        asset_v=repo.get("asset_v", ""),
        package_count=repo["package_count"],
        nav_home=marks["home"],
        nav_browse=marks["browse"],
        nav_add=marks["add"],
        foot_extra="",
    )


def row_html(p: dict, root: str) -> str:
    initial = (p.get("Name") or p.get("Package") or "?")[0].upper()
    tag = f'<span class="tag">{esc(p.get("Section"))}</span>' if p.get("Section") == "RootHide" else ""
    desc = (p.get("Description") or "").split("\n")[0]
    meta = " · ".join(x for x in [
        ARCH_LABEL.get(p.get("Architecture", ""), p.get("Architecture", "")),
        "v" + p.get("Version", ""),
        human_size(p.get("Size")),
    ] if x)
    search = " ".join([p.get("Name", ""), p.get("Package", ""), desc, p.get("Section", "")]).lower()
    return (
        f'<li data-section="{esc(p.get("Section"))}" data-name="{esc(p.get("Name"))}" '
        f'data-version="{esc(p.get("Version"))}" data-search="{esc(search)}">'
        f'<a class="row" href="{root}p/{slug(p["Package"])}/">'
        f'<span class="row__mark" aria-hidden="true">{esc(initial)}</span>'
        f'<span class="row__body">'
        f'<span class="row__name">{esc(p.get("Name") or p.get("Package"))}{tag}</span>'
        f'<span class="row__id">{esc(p.get("Package"))}</span>'
        + (f'<span class="row__desc">{esc(desc)}</span>' if desc else "")
        + f'<span class="row__meta">{esc(meta)}</span>'
        f'</span></a></li>'
    )


def build_home(repo: dict, pkgs: list[dict]) -> str:
    root = ""
    counts = []
    for sec in repo["sections"]:
        n = sum(1 for p in pkgs if p.get("Section") == sec)
        counts.append(f"<span>{esc(sec)} <b>{n}</b></span>")
    section_list = ""
    if repo["sections"]:
        items = []
        for sec in repo["sections"]:
            n = sum(1 for p in pkgs if p.get("Section") == sec)
            note = f"{n}" if n else "暂无"
            items.append(
                f'<li><a class="row" href="{root}browse/#{esc(sec)}">'
                f'<span class="row__body"><span class="row__name">{esc(sec)}</span></span>'
                f'<span class="row__meta">{note}</span>'
                f'<span class="row__chev" aria-hidden="true">›</span></a></li>'
            )
        section_list = (
            '<section class="block" aria-labelledby="sec-h">'
            '<div class="block__head"><h2 id="sec-h">分组</h2></div>'
            '<ul class="rows">' + "".join(items) + "</ul></section>"
        )
    rows = "".join(row_html(p, root) for p in pkgs)
    if not rows:
        rows = '<li><span class="row"><span class="row__body">'
        rows += '<span class="row__name">源已就绪，还没有软件包</span>'
        rows += '<span class="row__desc">把 .deb 放进 debs/ 并推送，索引会自动更新。</span>'
        rows += "</span></span></li>"
    body = render(
        "home.html",
        label=esc(repo["label"]),
        description=esc(repo["description"]),
        source_url=esc(repo["source_url"]),
        package_count=repo["package_count"],
        section_counts="".join(counts),
        section_list=section_list,
        rows=rows,
        root=root,
    )
    return page_shell(
        f'{repo["label"]} · 越狱插件源',
        f'{repo["description"]}，共 {repo["package_count"]} 个软件包。',
        body, root, "home", repo,
    )


def build_browse(repo: dict, pkgs: list[dict]) -> str:
    root = "../"
    segs = []
    for sec in repo["sections"]:
        n = sum(1 for p in pkgs if p.get("Section") == sec)
        dis = " disabled" if n == 0 else ""
        segs.append(
            f'<button role="tab" type="button" data-section="{esc(sec)}" '
            f'aria-selected="false"{dis}>{esc(sec)} <span aria-hidden="true">{n}</span></button>'
        )
    rows = "".join(row_html(p, root) for p in pkgs)
    body = render(
        "browse.html",
        package_count=repo["package_count"],
        seg_buttons="".join(segs),
        rows=rows,
        root=root,
    )
    return page_shell(
        f'软件包 · {repo["label"]}',
        f'{repo["label"]} 的全部软件包，可按名称搜索、按 RootLess / RootHide 分组筛选。',
        body, root, "browse", repo,
    )


def build_package(repo: dict, p: dict) -> str:
    root = "../../"
    ident = p["Package"]
    deps = p.get("Depends", "").strip()
    dep_items = [d.strip() for d in deps.split(",") if d.strip()]
    depends_block = ""
    if dep_items:
        depends_block = (
            '<section class="block"><h2>依赖</h2><ul class="deps">'
            + "".join(f"<li><span class=\"mono\">{esc(d)}</span></li>" for d in dep_items)
            + "</ul></section>"
        )
    maint = p.get("Maintainer") or p.get("Author")
    maintainer_fact = (
        f"<div><dt>维护者</dt><dd>{esc(maint)}</dd></div>" if maint else ""
    )
    open_actions = (
        '<section class="block">'
        "<h2>在客户端打开</h2>"
        f'<p><a class="btn btn--quiet" href="sileo://package/{esc(ident)}">用 Sileo 打开</a></p>'
        f'<p style="margin-top:8px"><a class="btn btn--quiet" href="irisin://package/{esc(ident)}">用 Irisin 打开</a></p>'
        '<p class="note">需要先在客户端里添加本源，否则会提示找不到软件包。</p>'
        "</section>"
    )
    sha = p.get("SHA256", "")
    body = render(
        "package.html",
        root=root,
        name=esc(p.get("Name") or ident),
        package=esc(ident),
        section=esc(p.get("Section") or "未分类"),
        initial=esc((p.get("Name") or ident)[0].upper()),
        version=esc(p.get("Version")),
        arch=esc(ARCH_LABEL.get(p.get("Architecture", ""), p.get("Architecture", ""))),
        size=human_size(p.get("Size")),
        maintainer_fact=maintainer_fact,
        description=esc(p.get("Description") or "未提供"),
        depends_block=depends_block,
        open_actions=open_actions,
        filename=esc(p.get("Filename", "").lstrip("./")),
        file=esc(Path(p.get("Filename", "")).name),
        sha256=esc(sha),
        sha256_short=esc(sha[:16] + "…" if sha else "未提供"),
    )
    return page_shell(
        f'{p.get("Name") or ident} · {repo["label"]}',
        (p.get("Description") or "").split("\n")[0][:150],
        body, root, "browse", repo,
    )


def build_add(repo: dict) -> str:
    root = "../"
    body = render("add.html", label=esc(repo["label"]), source_url=esc(repo["source_url"]), root=root)
    return page_shell(
        f'添加源 · {repo["label"]}', f'把 {repo["label"]} 添加到 Sileo、Irisin 或 Zebra 的步骤。',
        body, root, "add", repo,
    )


def build_404(repo: dict) -> str:
    body = render("404.html", root="")
    return page_shell(f'页面不存在 · {repo["label"]}', "这个页面不存在。", body, "", "none", repo)


# ────────────────────────── 写盘（白名单） ──────────────────────────
WRITABLE = re.compile(r"^(index\.html|404\.html|(browse|add|p|assets|data)/)")

def prune_package_pages(keep: set[str]) -> list[str]:
    """删除已不在索引里的包详情页目录。

    只处理 p/ 的一级子目录，且目录名必须等于 slug() 的结果，
    避免误删 `Packages` 等同级 APT 文件。
    """
    pdir = ROOT / "p"
    if not pdir.is_dir():
        return []
    removed = []
    for child in sorted(pdir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in keep:
            continue
        if slug(child.name) != child.name:   # 不是本脚本生成的目录名，跳过
            continue
        shutil.rmtree(child)
        removed.append(child.name)
    return removed


def write(rel: str, content: str) -> None:
    if not WRITABLE.match(rel):
        sys.exit(f"构建被拒绝：{rel} 不在白名单内（APT 文件只读）")
    dest = ROOT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写盘")
    args = ap.parse_args()

    before = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
              for f in APT_FILES if (ROOT / f).exists()}

    cfg = load_config()
    release = load_release()
    pkgs = load_packages()

    sections = cfg.get("sections") or ["RootLess"]
    # 兜底：索引里出现了配置外的 Section，也要如实呈现，不能吞掉
    extra = sorted({p.get("Section", "") for p in pkgs} - set(sections) - {""})
    if extra:
        print("提示：索引中出现未配置的分组，已追加显示：", ", ".join(extra))
        sections = sections + extra

    pkgs.sort(key=lambda p: (sections.index(p.get("Section", sections[0])), p.get("Name", "")))

    label = release.get("Label") or cfg.get("label") or "Repo"
    repo = {
        "asset_v": asset_version(),
        "label": label,
        "description": release.get("Description") or cfg.get("description", ""),
        "source_url": cfg.get("base_url", ""),
        "sections": sections,
        "package_count": len(pkgs),
    }
    if not repo["source_url"].startswith("https://") or "USERNAME" in repo["source_url"]:
        sys.exit("构建失败：scripts/config.json 的 base_url 还不是真实地址")

    files = {
        "index.html": build_home(repo, pkgs),
        "404.html": build_404(repo),
        "browse/index.html": build_browse(repo, pkgs),
        "add/index.html": build_add(repo),
    }
    for p in pkgs:
        files[f"p/{slug(p['Package'])}/index.html"] = build_package(repo, p)

    data = {
        "repo": {k: repo[k] for k in ("label", "description", "source_url", "sections")},
        "generated_from": "Packages",
        "package_count": len(pkgs),
        "packages": [
            {
                "package": p.get("Package"), "name": p.get("Name") or p.get("Package"),
                "version": p.get("Version"), "arch": p.get("Architecture"),
                "section": p.get("Section"), "size": p.get("Size"),
                "filename": p.get("Filename"), "sha256": p.get("SHA256"),
                "description": (p.get("Description") or "").split("\n")[0],
                "url": f"p/{slug(p['Package'])}/",
            }
            for p in pkgs
        ],
    }
    files["data/packages.json"] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        print(f"校验通过：{len(files)} 个页面/数据文件可生成，APT 文件未改动。")
        return

    for rel, content in files.items():
        write(rel, content)
    # 清理已下架包的详情页，避免出现索引里没有、URL 却还能打开的孤儿页
    removed = prune_package_pages({slug(p["Package"]) for p in pkgs})
    if removed:
        print("已清理过期详情页：", ", ".join(removed))
    # 静态资源原样复制
    for src in ASSETS.iterdir():
        if src.is_file():
            dest = ROOT / "assets" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)

    after = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
             for f in APT_FILES if (ROOT / f).exists()}
    if before != after:
        sys.exit("严重错误：APT 文件在构建过程中被改动！请用 git checkout 还原。")

    print(f"✅ 站点已生成：{len(files)} 个文件，{len(pkgs)} 个包，分组 {'/'.join(sections)}")
    print("   APT 文件 SHA256 校验：未改动")


if __name__ == "__main__":
    main()
