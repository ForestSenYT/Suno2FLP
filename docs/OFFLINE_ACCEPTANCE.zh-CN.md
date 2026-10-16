# 隔夜推进验收矩阵

本轮目标是完成既定路线图中可独立验证的离线部分。**当前定位：离线准备、结构验收、
协议发现边界和 PCM 数值比较可用；真实可交付 FLP 和宿主自动化仍待验收。**
不能把测试/CI 通过、合成输出或人工记录完整性等同于整个项目已完成。

| 阶段 | 已实现的离线能力 | 验证入口 | 仍需真实条件的验收 |
| --- | --- | --- | --- |
| 0 基础 | 安装、配置、工作区、发现、CLI、锁定依赖、跨平台检查 | 全套测试、wheel 安装和 `scripts/offline_smoke.py` | 无需 DAW 的基础入口可用 |
| 1 MIDI | Type 0/1 PPQ 多轨导入、事件/节拍来源、可选清理与完整审计 | 导入/清理合成测试、当前原始文件重导入 | Type 2/SMPTE 明确不支持，AI 转写不是本轮必需功能 |
| 2 编排/角色 | faithful、精确 PPQ、时间图冲突策略、显式角色、完整来源回放 | `verify-arrangement`、`prepare-project` / `verify-preparation` | 音色可用性和听感；reinterpretation/自动配器保留未来可选范围 |
| 3 FLP | 固定隔离后端只读检查、库存/绑定/资格、受限新 bundle、独立结构验证、手动记录检查 | 原创合成 writer/verifier、`check-host-records` | 六副本真实打开/缩放/另存/重开/试听；裁剪/标记、未知事件、依赖和乐器意图仍阻断 |
| 4 MCP | 原创发现客户端及两份固定上游服务的真实握手/工具清单，仍无 tools/call | [隔离接入审计](FLSTUDIO_MCP_AUDIT.zh-CN.md)：5/67 工具、刷新、协议 ping 与正常退出 | 实际 FL26 桥接、宿主读回和可恢复变更；服务连通不授予工具执行 |
| 5 质量/自动化 | 一键离线 JSON 准备及重放、流式整数 PCM 比较、显式数值阈值、安装产物集成检查 | `compare-renders`、独立准备验证、CI wheel smoke | 真正宿主渲染、人工试听、乐器/混音及最终音乐验收 |

## 可以实际使用的离线路径

按[离线工作流](OFFLINE_WORKFLOW.zh-CN.md)，把明确有权使用的 MIDI 和可选 WAV 放进
新项目输入，配置可选清理，生成新的 intermediate bundle，再做当前源回放验收。
这条路径不需要 .NET、FL Studio、FFmpeg、MCP、GPU 或专有插件，不下载模型。
编排和来源 JSON 可供检查/后续绑定，不能直接宣称生成了可交付 FLP。

独立的 [MCP 发现 API](MCP_DISCOVERY.md) 只提供协议生命周期和元数据；默认不会启用或
启动任何实际后端。实际执行 DAW 操作既没有授权，也没有由当前实现提供。
[PCM 数值比较](RENDER_COMPARISON.zh-CN.md) 只比较明确选择、已经对齐且格式相同的现有
整数 WAV，不能据此推断音色重建或可听结果。

## 安装包级复现

`scripts/offline_smoke.py` 创建全新的原创合成 MIDI/WAV，实际调用 CLI 完成初始化、
准备、重放验收、数值比较和失败案例。它检查原始输入不变、拒绝覆盖、拒绝损坏的已存
产物以及无 FLP 产生。故意损坏的仅是另一个新建合成测试输出，正常 ready bundle 保留。

```powershell
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
uv export --locked --no-dev --no-hashes --no-emit-project --output-file runtime-smoke-requirements.tmp
uv run --no-project --python 3.11 --with ./dist/suno2flp-0.1.0-py3-none-any.whl --with-requirements runtime-smoke-requirements.tmp python scripts/offline_smoke.py --require-installed --workspace .tools/my-new-wheel-smoke
```

工作目录必须是新的；重复执行换新名，不能覆盖。CI 在 Windows/Ubuntu × Python 3.11/3.14
上运行同样的安装包检查；`--require-installed` 拒绝从本仓库 src 加载的可编辑安装，避免
把源码测试当成 wheel 已验证。运行依赖由现有 uv.lock 导出固定，不用未锁定的最新依赖。
正常源码模式 smoke 仅是测试工具；报告会明确 `installed_wheel=false`。

## 本轮已取得的离线证据（2026-10-16）

- Python 3.11 与 3.14 各为 **742 通过、19 跳过**；其中 16 项需要另行启用实际后端，
  3 项因本机链接权限跳过。Ruff、格式检查及严格 mypy（69 个运行模块）通过。
- 两个版本均从新构建 wheel 和锁定运行依赖完成隔离安装、实际 CLI 正反例验证，
  发行包元数据确认加载安装包；原始合成输入不变，无 FLP 产生。
- wheel/source 包检查未包含私有工程、音频、已填记录、后端代码/二进制或缓存；
  全部 160 条相对文档链接有效。本地保护清单 73 项全部一致，54 个宿主阶段仍未执行。
- 一次独立审查发现的三个重要问题均以先失败后通过的回归修复：提前保护全部缺失
  输入路径、拒绝残缺 PCM 帧、为无工具会话核对 ping 并清除失效状态。无遗留重要或
  次要审查项。真实宿主、试听及实际后端互通未评定；敌对并发文件系统、进程树隔离和
  断电原子性不在已说明的可信本地范围内。

最新提交的跨平台结果以 [PR #1 的自动检查](https://github.com/ForestSenYT/Suno2FLP/pull/1/checks)
为准；未执行的宿主项目始终不计为通过。

## 本轮保护与证据

原始 FLP、基准与 GUI 对照、六个实验副本、六份原有人工表及既有后端安装保持只读。
新增本地日志、合成 smoke 工作区和复核回执位于忽略的 `.tools/overnight-offline-v1/`。
手动记录清单持续核对 73 项文件身份与 54 个未执行阶段，不替换旧记录或重写预期哈希。
未引用的宿主文件不被自动推断，任何缺失证据保持未知/待执行。

公开 PR 只包含原创代码、合成测试、空白模板与文档；不上传私有 FLP、音频、截图、
填写记录、原始工程字段、后端源文件/二进制或缓存。现有 writer 的全部资格门槛保留，
离线 run、quality、MCP 和 PCM 报告都不能充当生产写入许可。

## 最少的后续人工输入

1. 暂停电脑操控期间，按[六份手动清单](FL26_MANUAL_VALIDATION.zh-CN.md)逐份操作新另存
   文件，记录真实打开、视图/右边缘变化、重开和试听；只把本地路径提供给后续只读检查。
2. 确认实际模板/乐器意图、依赖版本及可用性；未解决的原始字段需要独立宿主对照证据，
   不能通过清零、猜测或勾选声明替代。
3. 需要 MCP/宿主自动化时，再明确授权实际后端/桥接配置、握手和允许的操作范围；当前
   不会替你启动或操控。最终输出仍需真实 FL Studio 打开、重开、渲染与试听验收。

只有这些真实条件满足且所有独立门槛解决后，才能将阶段 3–5 以及整个项目标为完成。
