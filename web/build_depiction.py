"""为站点生成 SileoDepiction JSON（含「详情」「更新日志」两个页签）。

只读取已存在的 markdown/描述，不产生任何虚构内容：
- 描述来自 APT 索引里的 Description 字段
- 更新日志来自 depictions/changelogs/<package>.md（人工整理，缺失则该页签显示"暂无"）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "depictions"
CHANGELOGS = OUT / "changelogs"

UNAVAILABLE = "暂无更新日志。"
DEFAULT_TAB = "详情"
CHANGELOG_TAB = "更新日志"


def markdown_for(pkg_id: str) -> str | None:
    """按包 ID 找日志；同一插件的不同变体（.roothide/.rootless）共用一份。"""
    base = pkg_id
    for suffix in (".roothide", ".rootless", ".rootful"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    for cand in (pkg_id, base):
        p = CHANGELOGS / f"{cand}.md"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    return None


def describe(pkg: dict) -> str:
    desc = pkg.get("Description", "").strip()
    if not desc:
        return "暂无描述。"
    first, *rest = desc.split("\n")
    body = "\n".join(line.strip() for line in rest).strip()
    return (first + "\n\n" + body).strip()


def build(pkg: dict) -> dict:
    pkg_id = pkg["Package"]
    log = markdown_for(pkg_id)
    tabs = [{
        "tabname": DEFAULT_TAB,
        "class": "DepictionStackView",
        "views": [{
            "class": "DepictionMarkdownView",
            "markdown": describe(pkg),
            "useSpacing": True,
        }],
    }]
    tabs.append({
        "tabname": CHANGELOG_TAB,
        "class": "DepictionStackView",
        "views": [{
            "class": "DepictionMarkdownView",
            "markdown": log if log else UNAVAILABLE,
            "useSpacing": True,
        }],
    })
    return {"class": "DepictionTabView", "tabs": tabs}


def main() -> None:
    index = json.loads((ROOT / "data" / "packages.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    count = 0
    for pkg in index["packages"]:
        pkg_id = pkg["package"]
        # 必须用「首行 + 续行」的完整描述：data 里的 description 只有续行
        full = "\n".join(x for x in (pkg.get("summary", "").strip(),
                                     pkg.get("description", "").strip()) if x)
        data = build({"Package": pkg_id, "Description": full})
        (OUT / f"{pkg_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count += 1
    print(f"✅ 生成 {count} 个 SileoDepiction JSON")


if __name__ == "__main__":
    main()
