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

站点由 `web/build.py` 从 `Packages` / `Release` 生成，输出到仓库根目录（Pages 直接服务 `main` 根目录）。

```sh
python3 web/build.py          # 生成
python3 web/build.py --check  # 只校验，不写盘
```

- 源码：`web/templates/*.html`（模板）、`web/assets/style.css`（Token 与布局）、`web/assets/app.js`（搜索/筛选/复制/主题）
- 设计规范与令牌：`spec/交付B-设计方向与方案.md`
- 构建脚本只会写白名单路径（`index.html` `404.html` `browse/` `add/` `p/` `assets/` `data/`），并在结束时校验 `Packages`/`Packages.gz`/`Release` 的 SHA256 未变；一旦变化即报错退出
- 目录名用 `p/` 而非 `packages/`，避免与 APT 的 `Packages` 文件在大小写不敏感的环境下冲突
