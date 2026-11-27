# DustDrift-Repo

个人越狱插件源（APT repo），可导入 **Sileo / Zebra / Irisin**。

- GitHub 仓库名：`Repo`
- Sileo 内显示名：**DustDrift-Repo**
- 分组：`RootLess`、`RootHide`

## 添加源

```
https://<你的用户名>.github.io/Repo/
```

Sileo → 源 → 右上角 `+` → 粘贴地址；或在 Sileo 里直接打开 `sileo://source/<你的用户名>/ghpages...`

## 加一个插件

1. 把编译好的 `.deb` 放进 `debs/`（rootless 包名一般是 `iphoneos-arm64`）
2. 重新生成索引：
   ```sh
   python3 scripts/gen_index.py .
   ```
3. 提交推送。push 之后 GitHub Actions 也会自动重建索引。

## 分组规则

索引脚本按这个优先级决定包属于 `RootLess` 还是 `RootHide`：

1. `scripts/sections.json` 里显式指定（最可靠）：
   ```json
   { "com.dustdrift.myTweak": "RootHide" }
   ```
2. `.deb` control 里的 `Section:` 恰好等于分组名
3. package id / 文件名 / Name / Depends / Description 里出现 `roothide` → RootHide
4. 出现 `rootless` → RootLess
5. 都没有 → 默认 `RootLess`

> Sileo 只会显示「有包」的分组；想让某个分组先空着也出现在列表里，需要至少放一个占位包。仓库自带两个演示包，各占一个分组，确认无误后可 `rm debs/*.deb` 再重新生成索引。

## 本地编译

```sh
ios-build -n MyTweak -s Tweak.xm -p com.dustdrift.mytweak -v 1.0.0 \
          -b com.apple.springboard -o out
```

rootful 包加 `-r rootful`；产物在 `out/<id>_<ver>_<arch>.deb`。

## 文件说明

| 文件 | 作用 |
|---|---|
| `Packages` / `Packages.gz` | 包列表（APT 读取的核心索引） |
| `Release` | 源元信息，`Label` 就是 Sileo 里显示的名字 |
| `packages.json` | 给网页用的数据 |
| `CydiaIcon.png` | 源图标（512×512） |
| `index.html` | 源的网页首页（GitHub Pages 根目录） |
| `.nojekyll` | 关掉 Jekyll，避免 `_` 开头的文件被忽略 |
| `scripts/gen_index.py` | 索引生成器 |
| `scripts/config.json` | 源名 / 分组 / base_url 配置 |
| `.github/workflows/update-index.yml` | push 后自动重建索引 |

## 网站

站点由三个脚本分三层生成，数据只有一条链：**debs → Packages → data/packages.json → 页面**。

```sh
python3 scripts/gen_index.py .   # 1) APT 索引：Packages / Packages.gz / Release
python3 web/build_data.py        # 2) 网页数据：校验后输出 data/packages.json
python3 web/build.py             # 3) 页面：首页 / packages / 详情 / add / about / 404
python3 web/build_depiction.py   # 4) SileoDepiction（详情 + 更新日志页签）
```

**数据校验**（`web/build_data.py`，失败即中止）：Package ID 唯一、必需字段齐全、
`Filename` 指向的文件真实存在、`Size` 与 `SHA256` 对得上、`Section` 属于配置分组、
架构属于已知 iOS 架构。

**安全边界**：`web/build.py` 只写白名单路径（`index.html` `404.html` `packages/` `add/`
`about/` `assets/` `data/`），构建前后对 `Packages` / `Packages.gz` / `Release` 做 SHA256
比对，不一致立即报错退出。

**目录约定**：详情页是 `/packages/<package-id>/`。注意它与 APT 的 `Packages` 文件仅差大小写——
在 Linux / GitHub Pages 上共存无碍，但**不要在 macOS / Windows 上克隆后直接构建**，
大小写不敏感的文件系统会让两者冲突。

**精选位**：`web/config/featured.json`。里面写的 Package ID 必须真实存在，否则构建失败；
首页索引栏按这个顺序排序。

**路由**：`/`、`/packages/`、`/packages/<id>/`、`/add/`、`/about/`、`/404.html`，全部目录式静态页，
刷新不会 404。

- 设计规范与令牌：`spec2/交付AB-审计与设计规范.md`
