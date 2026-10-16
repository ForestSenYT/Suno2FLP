# FL Studio MCP 隔离接入审计（2026-10-16）

两个真实上游服务已完成隔离安装/构建、初始化、完整工具清单、刷新及协议 ping。
**服务连通不证明 FL Studio 或 MIDI 桥接连通。** 全程未调用工具、读取资源、启动
FL Studio、打开/保存工程、播放或修改 FLP。默认集成仍为 `none`。两个服务已正常退出，
未注册全局 Codex 配置、设置常驻服务或安装宿主控制脚本。

## 固定身份、运行时与许可

| 后端 | 固定提交和真实自报 | 实际配置 | 许可 |
| --- | --- | --- | --- |
| Music2DAW | `6def9463d6fa8636bbc81010581318a39c47d3c4`；`Music2Daw.Mcp` / `1.0.0.0` | SDK 10.0.401；指定 runtime 10.0.12；MCP SDK 1.4.1；Hosting 10.0.10；DryWetMidi 8.0.3 | GPL-3.0-or-later，保留 Monad.FLParser GPL 通知 |
| rosasynthesiz/flstudio-mcp | `e6eff37e45a076098ed81ee4e50fb7bf08aef11a`；`fl-studio-mcp` / `0.3.0` | CPython 3.11.16；FastMCP **2.14.5**；Python MCP SDK 1.30.0；独立 uv 锁 | MIT |

Music2DAW 使用原版提交的新副本，未改变既有原版/适配后端，未移植 FL26 解析适配。
实时候选的安装包版本为 **1.0.0**，模块和握手却报 **0.3.0**。保留差异；后续应核对
完整提交、依赖锁和安装身份，不能只凭版本字符串。

源码依据：[Music2DAW 入口](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Mcp/Program.cs)、
[工具](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Mcp/FlStudioTools.cs)、
[许可](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/LICENSE)；
[实时入口](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/src/fl_studio_mcp/server.py)、
[依赖](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/pyproject.toml)、
[许可](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/LICENSE)。

上游 Python 依赖仅设下界，本次另用审计项目固定 FastMCP 2.14.5 并锁定所有依赖；
这是本项目选择，未改上游或核心依赖。[版本元数据](https://pypi.org/pypi/fastmcp/2.14.5/json)
记录 v2 边界。安装 92 个发行包，未装 librosa/numpy/scipy/torch 等可选音频/模型栈。
CPython 基础解释器由 uv 管理，具体路径/身份只留本地，运行包在新的隔离环境。
NuGet 新缓存含 36 个包，三个项目的锁及发布产物保留。

NuGet MCP SDK、FastMCP 为 Apache-2.0；Hosting、Python MCP SDK 为 MIT；
PyAutoGUI/PyGetWindow 声明 BSD，python-rtmidi/RtMidi 通知保留。完整依赖声明和通知
位置另存本地。PyGetWindow 安装包无单独通知文件；元数据不是完整分发合规证明，
重新分发前仍须补齐审查。本轮不分发、重新许可或捆绑这些后端。

## 启动行为

- Music2DAW 入口只创建通用 host、将日志送至 stderr 并注册 stdio/工具。构造无工程
  路径输入，FL Studio 启动只在工具执行时发生。使用新发布 DLL 和指定 runtime，
  不使用启动时还会构建的 `dotnet run`。
- 实时候选只导入/注册工具和资源，`get_bridge()` 在工具/资源执行时才打开 MIDI 或
  连接 daemon。导入会读取用户目录的变更日志，因此子进程 profile、应用数据、临时
  和 FastMCP 目录都指向新的运行目录。禁用更新检查，Docket 用进程内 `memory://`。
  没有启动 MIDI daemon；PyAutoGUI 虽为必需依赖，未被调用。
- 原创启动器拒绝网络 connect/bind、子进程、shell/GUI 启动及 FLP 访问的相关 Python
  审计事件。仅允许已核对标准库 `socket.py:_fallback_socketpair` 自身的环回 socket，
  用于 Windows asyncio 自唤醒；不放行任意 localhost、桥接端口或 HTTP 服务。
- 初次过严限制阻止 socketpair，保留失败回执。回归先复现失败，再修正 uv 解释器
  路径别名归一化；真实 socketpair 成功，五类禁止事件仍被拒绝。成功握手只记录内部
  bind/connect 和退出，没有桥接尝试；没有模拟或替换服务器响应。
- 这是可信固定源码的启动约束，**不是操作系统沙箱**。Python 钩子不覆盖所有原生
  MIDI/FFI，不将结果外推为恶意代码隔离或宿主内部状态认证。

## 真实协议证据

使用现有发现客户端，每个成功会话仅发送：

```text
initialize(protocolVersion=2025-06-18, capabilities={})
notifications/initialized
tools/list
tools/list                  # 刷新并核对完整定义一致
ping                        # 协议 ping，不是 fl_ping 工具
EOF / disconnect
```

两者均接受 **2025-06-18**，完整清单刷新一致、ping 成功，退出码均为 0，读线程停止、
连接关闭、缓存清除。26 项既有合成契约测试通过。双向原始 JSON-RPC、初始化结果、
完整 schema/annotations、stderr 及身份仅留本地。无 `tools/call`、资源读取、MIDI
枚举或宿主 `fl_ping`；没有更改产品执行策略。

Music2DAW 实际 **5** 项：`fl_studio_capabilities`、`inspect_flp`、`edit_flp`、
`export_music_bundle`、`launch_fl_studio_project`。编辑/导出会写磁盘，启动不等于
宿主编辑、保存或新会话验证；原版 FL26 解析限制、覆盖输出风险均未解决。

实时候选实际 **67** 项，annotations 声明 28 项 read-only、39 项非只读，均不是授权。
`fl_get_project_state`、`fl_get_tempo`、`fl_get_channel_state`、`fl_get_routing_all`、
`fl_plugin_get_params` 可作为未来只读探测候选；播放、调参、路由和音符工具均未执行。
音符工具还可能写 .pyscript、切焦点并触发快捷键，不能当作纯 API。音频工具虽能发现，
可选依赖未装；67 项可发现不等于全部功能可用。

## 六份手动验收的覆盖

| 步骤 | 本轮可确认 | 仍阻断 |
| --- | --- | --- |
| 身份/最终保护 | 原有离线哈希、大小、mtime 和引用检查 | 不认证实际版本画面/宿主行为 |
| 打开输入 | 发现 Music2DAW 启动工具，未执行 | 实际打开、警告、当前工程；实时候选无专用打开工具 |
| 视图缩放 | 无对应工具 | Playlist/Piano roll 倍率及画面，不以量化代替 |
| 无音乐编辑另存 A | 无宿主另存工具 | 真正 Save as、独占路径及序列化 |
| 关闭并新会话重开 A/B | 无完整流程工具 | 启动不证明已关闭或重开磁盘文件 |
| 固定左边缘 L→2L | 无专用片段几何/裁剪工具 | 文件编辑、重画音符不能冒充宿主边缘实验 |
| 速度/通道/混音状态 | 存在读取候选 | 未调用，桥接和 FL26 返回值/单位未验 |
| 两音符、flags/crops 回读 | 原有离线读取可另行执行 | 当前清单不足以完整读回宿主片段/音符 |
| SONG 播放、渲染、试听 | 发现播放/停止工具 | 未实测，无已确认完整渲染接口；电平不代替听感 |

后续需单独授权核对/配置虚拟 MIDI 端口及控制器脚本，先验证宿主版本和只读桥接，
再审查允许调用的具体工具。本轮未探测这些现有配置是否可用，也未安装或改变它们。
桥接成功后缺少工具的步骤仍需人工或另行设计受控适配，不能承诺六份全自动验收。

## 溯源与保护

私有根目录 `.tools/flstudio-mcp-audit-v1/` 保存固定源码、依赖锁、许可清单、源文件/
发布产物/环境身份、原始协议、失败尝试及保护回执。公开只提交原创说明，不上传上述
后端文件、安装锁、原始协议、私有工程或填写记录；复验另建目录。
前后 **73/73** 引用有效、清单身份一致，**54 个宿主阶段仍未执行**；原始 FLP、基准、
六份副本、旧记录及两套原有后端保持不变。FL/FL64 进程快照前后一致，仅作辅助观察。
报告继续 host unverified、writer blocked、execution false。
