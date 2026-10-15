# 双平台发布与维护

`VERSION` 是唯一发布版本来源。macOS 的 Info.plist、构建号、Linux 的 VERSION / release.json，以及所有发行文件名均由它生成。更新 VERSION 时，同时新增 CHANGELOG.md 条目并更新受影响的使用文档。macOS 构建号按 `major * 10000 + minor * 100 + patch` 生成；minor / patch 均须小于 100。

## 持续验证

每个 PR、main 提交和手动 CI 都执行同一套验证：

| 平台 | 必须通过的检查 | 保留的产物 |
| --- | --- | --- |
| macOS 14 | Python 回归、Swift 动画、arm64 + x86_64 通用构建、签名验证、DMG 校验与只读挂载、公开内容检查 | 通用安装 DMG、兼容 ZIP、源码 ZIP |
| Ubuntu 24.04 | Python / Tk 回归、Linux 打包、隔离用户安装、桌面入口验证、Xvfb 演示启动、公开内容检查 | Linux tar.gz |
| 汇总 | 两个平台都成功、包内版本一致、总结功能源码完整、SHA-256 校验 | 两个平台 + 源码 + 校验文件 |

Actions 的 `coindex-release` artifact 保留 14 天，可以在正式发布前下载验收。CI 使用虚构数据，不需要真实 Codex 登录、不调用模型、不发送催办。Tk 和 Swift 的运行验证分别在自己的操作系统上执行。

工作流依赖由 Dependabot 每月提出更新 PR，不自动合并。修改依赖后仍需通过两个平台的 CI；不要通过跳过测试来消除平台差异。

## 本地准备发行包

macOS：

```sh
CODEX_TODO_CODEX=/usr/bin/true python3 -m unittest discover -s tests -v
COINDEX_ARCHS="arm64 x86_64" bash scripts/build.sh
python3 scripts/release.py package macos
python3 scripts/package-source.py
```

Linux：

```sh
CODEX_TODO_CODEX=/usr/bin/true xvfb-run -a python3 -m unittest discover -s tests -v
bash scripts/build-linux.sh
python3 scripts/release.py package linux
```

把两个系统同一提交产出的文件放到同一个 `dist/` 目录后：

```sh
python3 scripts/release.py checksums
python3 scripts/release.py verify
```

预期文件（以 1.10.1 为例）：

- `coindex-1.10.1-macos-universal.dmg`（Mac 首选安装包）
- `coindex-1.10.1-macos-universal.zip`（兼容已有更新功能）
- `coindex-1.10.1-linux.tar.gz`
- `coindex-1.10.1-source.zip`
- `coindex-1.10.1-SHA256SUMS.txt`

构建先在临时目录生成完整应用，再替换已识别的旧构建，防止旧模块残留或失败后破坏前一个构建。

打包器固定文件顺序、归档时间戳与权限，Linux 包还清除本机用户 / 组信息；相同输入内容的归档字节可重复。Swift 二进制仍取决于编译器、SDK 与签名环境，不承诺不同工具链生成相同字节。Linux 包包含 Python 源码，使用目标系统的 Python 与 Tk；它不是自带运行时的 AppImage。macOS 当前仍使用 ad hoc 签名，未做 Developer ID 签名或 Apple 公证。

DMG 使用 macOS 内置 hdiutil 生成只读安装盘，包含应用、指向 `/Applications` 的拖拽入口和安装说明，不自动运行程序或修改系统。打包时校验磁盘并只读挂载，逐文件比对应用内容及签名，确保安装盘与 ZIP 中的应用一致，再卸载。Linux 汇总检查 DMG 容器结构和校验值；DMG 的完整挂载验证只在 macOS 上执行。DMG 文件系统含生成元数据，不承诺字节可重复。

`package` 会拒绝旧版本元数据、不完整的包和非通用的 macOS 程序，并执行公开内容检查。只发布公共素材；`COINDEX_INCLUDE_LOCAL_PETS=1` 构建会被发布检查拒绝。不要上传个人数据库、连接配置、会话或日志。

## 创建与审核 Release

1. 在 PR 中完成代码、测试、VERSION、CHANGELOG 和文档修改，等待两个平台及 `release-check` 通过。
2. 合并后，在确认的发布提交上创建与 VERSION 完全一致的标签，例如 `v1.10.1`。推送标签属于发布操作，应由维护者明确执行。
3. `Release` workflow 在该标签上重新运行整套 CI。任一平台失败都不创建 Release。
4. 全部通过后，工作流创建 **Draft Release**，附两个平台、源码和 SHA-256 文件。失败重跑只更新同名草稿；已公开的 Release 不会被覆盖。
5. 维护者下载草稿中的实际文件，按校验清单验证，在 macOS 与 Linux 各检查演示模式、旧数据升级、总结与自动总结配置，并核对说明后手动发布。

发布说明由 `release.py notes` 自动把两端安装包、兼容 ZIP 和校验文件链接放在顶部，不依赖 GitHub 的 Assets 延迟加载。公开后确认未登录也能下载 DMG 和 Linux 包。

CI 成功、草稿创建和正式发布是三个不同状态。标签触发流程不会自动把草稿公开。已公开版本发现问题时新增补丁版本，不替换旧标签或已发布文件。

## 共享后端与界面的维护边界

总结筛选、模型调用、日程、持久化及任务状态规则放在 backend。macOS / Linux 界面只负责交互、展示和协议调用，避免为同一规则维护两份实现。

新增后端响应字段时兼容旧数据；新增视图或模块时同步检查构建入口和发行包清单。对任务身份、手动完成、归档、固定标题、发送回执、总结历史的改动，提供升级和失败场景回归。总结生成不能改变待办状态。

回归测试使用临时数据库、假模型和虚构目标。人工验收也使用独立数据目录；真实模型验证应单独说明范围和结果；向原会话发送消息需有用户授权。

## 应用内版本检查

macOS 和 Linux 正常启动时各检查一次本仓库最新的公开稳定 Release，也可从界面手动「检查更新」。检查通过后显示版本与 GitHub 更新说明；可选择下载更新、稍后处理或跳过此版本。跳过记录持久保存，只忽略该确切版本；下一次新版本发布后恢复提醒。手动检查仍可查看已跳过的版本。

检查只向固定的 GitHub Releases API 发送公共 GET 请求，不发送待办、总结、会话或凭据。草稿和预发布不会提示；失败时保留上一次成功的信息，并提供重试提示。更新说明作为文字展示，应用不执行其中的内容。

下载按钮在浏览器打开适配当前平台的官方仓库安装包。macOS 优先选择 DMG，旧 Release 仅有 ZIP 时继续兼容；没有匹配安装包时显示「查看发布页」。用户校验下载后手动安装，应用不自行替换正在运行的文件或个人数据。只有正式公开的 Release 才会被应用发现，因此草稿验收完成后再发布。

演示 / 测试模式不自动联网检查；其他自动化 UI 验证可设置 `COINDEX_DISABLE_UPDATE_CHECK=1`。单元测试模拟 API 响应，包含版本比较、跳过、网络错误和下载地址校验。
