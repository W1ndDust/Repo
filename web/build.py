#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DustDrift 站点构建器（无第三方依赖）。

数据来源：web/build_data.py 产出的 data/packages.json（其上游唯一真源是 APT 索引）。
输出白名单：index.html 404.html packages/ add/ about/ assets/ data/
任何情况下不写 Packages / Packages.gz / Release / debs/，构建结束校验其 SHA256。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
TPL = WEB / "templates"
ASSETS = WEB / "assets"
DATA = ROOT / "data" / "packages.json"
FEATURED = WEB / "config" / "featured.json"
APT_FILES = ["Packages", "Packages.gz", "Release"]

WRITABLE = re.compile(r"^(index\.html|404\.html|(packages|add|about|assets|data)/)")


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def render(tpl_name: str, /, **ctx) -> str:
    src = (TPL / tpl_name).read_text(encoding="utf-8")
    for k, v in ctx.items():
        src = src.replace("{{%s}}" % k, str(v))
    left = re.findall(r"\{\{[a-z_]+\}\}", src)
    if left:
        sys.exit(f"构建失败：{tpl_name} 有未替换占位符 {sorted(set(left))}")
    return src


def asset_version() -> str:
    h = hashlib.sha256()
    for f in sorted(ASSETS.rglob("*")):
        if f.is_file():
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:8]


def load() -> dict:
    if not DATA.exists():
        sys.exit("构建失败：data/packages.json 不存在，先运行 python3 web/build_data.py")
    return json.loads(DATA.read_text(encoding="utf-8"))


def load_featured(data: dict) -> list[dict]:
    """精选位来自配置文件，但每个 ID 必须真实存在，否则构建失败。"""
    if not FEATURED.exists():
        return []
    cfg = json.loads(FEATURED.read_text(encoding="utf-8"))
    by_id = {p["package"]: p for p in data["packages"]}
    out = []
    for pid in cfg.get("packages", []):
        if pid not in by_id:
            sys.exit(f"构建失败：featured.json 里的 {pid} 不在索引中")
        out.append(by_id[pid])
    return out


_ASSET_V = None


def shell(title: str, desc: str, body: str, root: str, page: str, data: dict, v: str = "") -> str:
    global _ASSET_V
    if _ASSET_V is None:
        _ASSET_V = asset_version()
    marks = {p: (' aria-current="page"' if p == page else "")
             for p in ("home", "packages", "about")}
    return render(
        "base.html", title=title, desc=desc, root=root, body=body, page=page,
        label=esc(data["repo"]["label"]),
        package_count=data["stats"]["total"],
        nav_home=marks["home"], nav_packages=marks["packages"], nav_about=marks["about"],
        asset_v=_ASSET_V,
    )


def row(p: dict, root: str, index=None) -> str:
    tag_class = {"RootHide": "rh", "System": "sys", "TrollStore": "ts"}.get(p["section"], "rl")
    num = f'<span class="row__num" aria-hidden="true">{index:02d}</span>' if index else ""
    return (
        f'<li class="row{" row--num" if index else ""}" data-section="{esc(p["section"])}" data-name="{esc(p["name"])}" '
        f'data-version="{esc(p["version"])}" data-search="{esc((p["name"] + " " + p["package"] + " " + p["summary"] + " " + p["maintainer"] + " " + p["env"]).lower())}">'
        f'<a class="row__link" href="{root}packages/{esc(p["slug"])}/">'
        + num +
        f'<span class="row__icon" aria-hidden="true">{esc(p["name"][0].upper())}</span>'
        f'<span class="row__body">'
        f'<span class="row__name">{esc(p["name"])}</span>'
        f'<span class="row__desc">{esc(p["summary"])}</span>'
        f'<span class="row__meta"><span class="tag tag--{tag_class}">{esc(p["env"])}</span>'
        f'<span>v{esc(p["version"])}</span><span>{esc(p["size_label"])}</span></span>'
        f'</span>'
        f'</a></li>'
    )


def build_home(data: dict, featured: list[dict], root: str) -> str:
    ordered = featured + [p for p in data["packages"] if p not in featured]
    rail = "".join(
        f'<li><a href="{root}packages/{esc(p["slug"])}/">'
        f'<span class="rail__num">{i:02d}</span>'
        f'<span class="rail__name">{esc(p["name"])}</span>'
        f'<span class="rail__env">{esc(p["env"])}</span></a></li>'
        for i, p in enumerate(data["packages"], 1)
    ) or '<li class="rail__empty">暂无插件</li>'

    SEC_DESC = {
        "RootLess": "安装到 /var/jb/…，用于无根越狱",
        "RootHide": "安装到 /Library/…，用于隐根环境",
        "System": "注入器与系统级组件",
        "TrollStore": "TrollStore 环境的应用",
    }
    stats = f'<div class="stat"><span class="stat__n">{data["stats"]["total"]}</span><span class="stat__l">插件总数</span></div>'
    for sec in data["repo"]["sections"]:
        stats += (f'<div class="stat"><span class="stat__n">{data["stats"]["by_section"].get(sec, 0)}</span>'
                  f'<span class="stat__l">{esc(sec)}</span></div>')

    env_cards = ""
    for sec in data["repo"]["sections"]:
        n = data["stats"]["by_section"].get(sec, 0)
        cls = {"RootHide": "rh", "System": "sys", "TrollStore": "ts"}.get(sec, "rl")
        env_cards += (
            f'<a class="envcard" href="{root}packages/#{esc(sec)}">'
            f'<span class="tag tag--{cls}">{esc(sec)}</span>'
            f'<span class="envcard__n">{n}</span>'
            f'<span class="envcard__d">{esc(SEC_DESC.get(sec, ""))}</span>'
            "</a>"
        )

    body = render("home.html", root=root, description=esc(data["repo"]["description"]),
                  package_count=data["stats"]["total"], rail_items=rail, stats=stats,
                  env_cards=env_cards)
    return shell(f'{data["repo"]["label"]} · iOS 越狱插件源',
                 f'{data["repo"]["description"]}，共 {data["stats"]["total"]} 个插件。',
                 body, root, "home", data, "")


def build_catalog(data: dict, root: str) -> str:
    rows = "".join(row(p, root, i) for i, p in enumerate(data["packages"], 1))
    chips = "".join(
        f'<button role="tab" type="button" data-section="{esc(sec)}" aria-selected="false"'
        f'{" disabled" if data["stats"]["by_section"].get(sec, 0) == 0 else ""}>'
        f'{esc(sec)}<em>{data["stats"]["by_section"].get(sec, 0)}</em></button>'
        for sec in data["repo"]["sections"]
    )
    body = render("packages.html", root=root, package_count=data["stats"]["total"],
                  rows=rows, chips=chips)
    return shell(f'Packages · {data["repo"]["label"]}',
                 f'{data["repo"]["label"]} 的全部插件，可按名称、ID、描述搜索并按环境筛选。',
                 body, root, "packages", data, "")


def build_detail(data: dict, p: dict, root: str) -> str:
    initial = esc(p["name"][0].upper())
    tag_class = {"RootHide": "rh", "System": "sys", "TrollStore": "ts"}.get(p["section"], "rl")
    maintainer = (f'<div><dt>维护者</dt><dd>{esc(p["maintainer"])}</dd></div>'
                  if p["maintainer"] else "")
    depends = ""
    if p["depends"]:
        items = "".join(f'<li><span class="mono">{esc(d)}</span></li>' for d in p["depends"])
        depends = ('<section class="block"><h2 class="block__title">依赖</h2>'
                   f'<ul class="deps">{items}</ul></section>')
    changelog = ""
    cl_path = ROOT / p["changelog"]
    if cl_path.exists():
        md = cl_path.read_text(encoding="utf-8")
        changelog = ('<section class="block"><h2 class="block__title">更新记录</h2>'
                     f'<div class="changelog">{changelog_html(md)}</div></section>')
    body = render(
        "package.html", root=root, env=esc(p["env"]), tag_class=tag_class,
        initial=initial, name=esc(p["name"]), package=esc(p["package"]),
        summary=esc(p["summary"]), version=esc(p["version"]),
        architecture=esc(p["architecture"]), size_label=esc(p["size_label"]),
        maintainer=maintainer,
        description=(esc(p["description"]) or "未提供详细描述。").replace("\n", "<br>"),
        depends=depends, filename=esc(p["filename"]),
        file_name=esc(Path(p["filename"]).name),
        sha256=esc(p["sha256"]), sha_short=esc(p["sha256"][:24] + "…" if p["sha256"] else "未提供"),
        changelog=changelog,
    )
    return shell(f'{p["name"]} · {data["repo"]["label"]}', p["summary"] or p["name"],
                 body, root, "packages", data, "")


def changelog_html(md: str) -> str:
    """把日志 markdown 的极小语法（**粗体** + - 列表）转成 HTML，不引入库。"""
    out, in_list = [], False
    for line in md.splitlines():
        s = line.strip()
        if not s:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(s))
        if line.startswith("- ") or line.strip().startswith("- "):
            if not in_list:
                out.append('<ul class="clist">')
                in_list = True
            out.append(f'<li>{s[2:] if s.startswith("- ") else s}</li>')
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<p class="cver">{s}</p>')
    if in_list:
        out.append("</ul>")
    return "".join(out)


def build_add(data: dict, root: str) -> str:
    body = render("add.html", root=root, repo_url=esc(data["repo"]["url"]))
    return shell(f'Add Repository · {data["repo"]["label"]}',
                 "把 DustDrift 添加到 Sileo、Irisin 或 Zebra 的步骤。",
                 body, root, "add", data, "")


def build_about(data: dict, root: str) -> str:
    sec_rows = "".join(
        f'<div><dt>{esc(sec)}</dt><dd>{esc({"RootLess": "无根越狱", "RootHide": "隐根环境", "System": "系统级组件", "TrollStore": "TrollStore 环境"}.get(sec, sec))}</dd></div>'
        for sec in data["repo"]["sections"]
    )
    body = render("about.html", root=root, sec_rows=sec_rows, repo_url=esc(data["repo"]["url"]),
                  package_count=data["stats"]["total"],
                  count_rootless=data["stats"]["by_section"].get("RootLess", 0),
                  count_roothide=data["stats"]["by_section"].get("RootHide", 0))
    return shell(f'About · {data["repo"]["label"]}', "关于 DustDrift 软件源。",
                 body, root, "about", data, "")


def build_404(data: dict, root: str) -> str:
    body = render("404.html", root=root)
    return shell(f'页面不存在 · {data["repo"]["label"]}', "页面不存在。", body, root, "404", data, "")


def write(rel: str, content: str) -> None:
    if not WRITABLE.match(rel):
        sys.exit(f"构建被拒绝：{rel} 不在白名单内")
    dest = ROOT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def prune(keep_slugs: set[str]) -> list[str]:
    removed = []
    pdir = ROOT / "packages"
    if not pdir.is_dir():
        return removed
    for child in sorted(pdir.iterdir()):
        if child.is_dir() and child.name not in keep_slugs and re.fullmatch(r"[A-Za-z0-9._-]+", child.name):
            shutil.rmtree(child)
            removed.append(child.name)
    # 旧版 /p/ 与 /browse/ 路由清理
    for legacy in ("p", "browse"):
        d = ROOT / legacy
        if d.is_dir():
            shutil.rmtree(d)
            removed.append(legacy + "/")
    return removed


def main() -> None:
    before = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
              for f in APT_FILES if (ROOT / f).exists()}
    data = load()
    featured = load_featured(data)
    v = asset_version()

    files = {
        "index.html": build_home(data, featured, ""),
        "404.html": build_404(data, ""),
        "packages/index.html": build_catalog(data, "../"),
        "add/index.html": build_add(data, "../"),
        "about/index.html": build_about(data, "../"),
    }
    for p in data["packages"]:
        files[f'packages/{p["slug"]}/index.html'] = build_detail(data, p, "../../")

    for rel, content in files.items():
        write(rel, content)

    for f in ASSETS.iterdir():
        if f.is_file():
            dest = ROOT / "assets" / f.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)

    removed = prune({p["slug"] for p in data["packages"]})
    if removed:
        print("已清理过期页面：", ", ".join(removed))

    after = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
             for f in APT_FILES if (ROOT / f).exists()}
    if before != after:
        sys.exit("严重错误：APT 文件在构建过程中被改动，请 git checkout 还原")

    print(f'✅ 站点：{len(files)} 页 · {data["stats"]["total"]} 个插件 · APT 文件未改动')


if __name__ == "__main__":
    main()
