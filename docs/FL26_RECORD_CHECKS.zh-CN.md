# 六份手动记录的离线完整性检查

`check-host-records` 只读取明确指定的本地文件，核对哈希和填写规则并生成汇总。
它不操作 FL Studio、不调用后端、不修复记录、不写 FLP，也不认证宿主或音频行为。
裁剪、非零片段标记及其他写入门槛保持原样；所有报告固定为
`writer_eligibility: blocked`、`execution_allowed: false`、`host_compatibility: unverified`。

## 本地使用

原有六份 Markdown 表不变。新增的 JSON 是给检查器读取的伴随记录，不从 Markdown
自由文本推断“通过”。本地准备目录：
`.tools/fl26-clip-write-validation-v1/manual-validation-v1/offline-check-v1/`。
该目录保存六份待执行 JSON、`manifest.json` 和本轮汇总。工程、已填表、清单、哈希、
截图和报告均留在忽略目录，不上传 GitHub。公开的只有代码、合成测试、文档和
[未填 JSON 模板](../examples/fl26_host_record.template.json)。

在仓库根目录执行（报告名必须是新的）：

```powershell
uv run suno2flp check-host-records .tools/fl26-clip-write-validation-v1/manual-validation-v1/offline-check-v1/manifest.json --root . --output .tools/fl26-clip-write-validation-v1/manual-validation-v1/offline-check-v1/check-new.json
uv run suno2flp check-host-records .tools/fl26-clip-write-validation-v1/manual-validation-v1/offline-check-v1/manifest.json --root . --markdown --output .tools/fl26-clip-write-validation-v1/manual-validation-v1/offline-check-v1/summary-new.md
```

省略 `--output` 时输出到终端，不写任何文件。JSON 默认使用 `.json`；`--markdown` 使用
`.md`。已有输出、格式不匹配及后端目录内的输出均拒绝，不覆盖、清理或自动创建目录。
输出还必须与清单及所有已发现的输入引用不同，即使某个输入已缺失也不能用报告填占。
JSON 包含逐文件预期/实际身份、诊断及每份记录的后续证据槽；Markdown 提供概览。
`--root` 必须明确指定，所有输入引用相对此根目录；清单也必须位于此根目录内。

退出码 **0 只表示所选文件与填写规则一致**：完整的未执行记录，或如实记载的失败/阻断，
都可以返回 0。缺失/变化的文件、错误 schema、互相矛盾或缺证据的成功声明返回 1；仍可
输出新的诊断报告。不存在的根目录等入口错误返回 1，不能当成宿主检查已经执行。

## 清单与记录契约

清单 `schema_version: 1`、`profile: fl26-26.1.7.5654-manual-v1`，包含：

| 字段 | 内容 |
| --- | --- |
| `protected_files` | 原始/基准等需要保护的文件身份；至少一项，本地清单还固定两套后端文件身份 |
| `provenance_files` | 原始来源、准备清单等身份，至少一项，保留旧记录 |
| `records` | 六个不同副本各一项，不能缺少或重复 |
| 每项 `probe` | 手动清单中的六个固定副本名称之一 |
| 每项 `record` / `form` / `candidate` | 分别为伴随 JSON、原有 Markdown 表、实验输入文件的身份；路径不能重复 |

文件身份为 `path`（根目录内、使用 `/` 的相对路径）、`sha256`（64 位小写十六进制）、
`size_bytes`；可选 `mtime_ns` 固定修改时间。读取前后再次核对，检查期间变化也判无效。
路径越界、符号链接/Windows reparse 路径、歧义路径、非普通文件均拒绝；A/B 也不能通过
硬链接别名占用输入或其他输出。重复 JSON 键、未知字段/状态不被静默接受。

JSON 记录的 `probe` 必须与清单项相同。`stages` 必须明确列出全部九阶段，不能省略未执行项。
每阶段包括 `status`，以及需要时的 `performed_at`（含时区）、`details`、`reason`、
`evidence`（证据槽名到文件身份的映射）。实际文件 A/B 另填 `outputs.A`/`outputs.B`；
试听另填 `listening.A`/`listening.B`，默认 `not_listened`。

| 阶段 key | `pass_observed` 必填证据槽 |
| --- | --- |
| `identity` | `identity_check` |
| `open` | `observation` |
| `view_zoom` | `before`, `after` |
| `save_a` | `save_observation`，另有 `outputs.A` |
| `reopen_a` | `reopen_observation`, `listening_note` |
| `resize_b` | `before`, `after`, `save_observation`，另有 `outputs.B` |
| `reopen_b` | `reopen_observation`, `listening_note` |
| `readback` | `input_readback`, `a_readback`, `b_readback`, `comparison` |
| `protection` | `identity_check` |

所有引用证据都检查实际文件哈希，包括失败或阻断记录中已附的证据。
`pass_observed` 或 `fail_observed` 必须有操作者、实测完整版本 `26.1.7.5654`、含时区的
执行时间和非空观察。成功阶段必须具备前序成功阶段，执行时间不能倒序；最后的
`protection` 独立于音乐实验成败，先前失败后仍可如实完成最终文件保护核对。
成功重开 A/B 还要求对应已保存 FLP 身份及 `heard_as_recorded` 的试听记录；没听取时
不能声明该完整阶段通过，可保留观察文字，阶段标 `blocked` 并说明未试听。

`fail_observed` 至少附一项实际证据，不强求失败时根本没有生成的输出；后续阶段可以
如实标为 `blocked`。`blocked`、`skipped` 必须说明原因。
这些阶段若记录了部分观察，也需要操作者、含时区的时间和非空观察文字；可以保存已确认
的本构建版本，不会被误判为“未执行带结果”。暂时无法确认宿主版本时保持空白。
`pending_not_performed` 阶段不能带执行时间、观察、理由或证据；未执行另存/重开时
也不能出现对应的输出身份/试听结果。计划值继续写在人工表的“计划/声明”部分，不填入
实际结果字段。整个阶段尚未完成且已经观察到部分内容时，用 `blocked` 说明进度和原因，
不能一边保留“未执行”一边填写结果。

## 汇总含义与边界

- `pending_not_performed`：六份记录的全部 54 阶段都明确未执行，且检查有效。
- `reported_complete`：全部阶段的成功声明满足填写规则和所引文件身份；**仍是操作者声明**。
- `incomplete`：执行进度混合、存在失败/阻断/跳过，或完整性检查无效。
- `unknown_stages`：JSON 无法读取/解析等导致不能判断的阶段数；不算作未执行或通过。

哈希证明与所给清单一致，不证明清单签名、截图真实性、操作者确实打开了指定工程、
实际听到了声音、数值几何符合目标或回读报告的音乐字段正确。本检查器不解析证据文件
内部语义、不重新调用后端、不递归追踪旧报告中的依赖，也不自动发现未引用的宿主文件。
旧准备报告中的文档身份是当时快照；更新文档不意味着可以修改那个旧报告。

执行人工验证时，每次从原表派生**新的运行目录**，保留旧表、JSON 和清单。同步填写
人工观察及伴随 JSON，记录真实输出/证据的身份，再审查并保存一个新版本清单。检查器
不会自动重算并替换清单中的预期哈希，不能用“重新固定哈希”掩盖未知变化。即使六份
均 `reported_complete`，也不能改写策略、运行生产写入器或解除任何兼容性阻断。
实际步骤仍以[手动宿主清单](FL26_MANUAL_VALIDATION.zh-CN.md)为准。

## 合成验证

测试只创建原创小文本/JSON 和合成占位文件，不读取私有工程或安装后端。
覆盖六份未执行汇总、全部成功证据槽、缺失/变更文件、大小/mtime、重复键、未知或
矛盾状态、声明完成仍不可执行、阶段顺序、输出别名、读取期间变化和独占报告输出。
外部宿主验证仍未执行。

```powershell
uv run pytest tests/unit/test_manual_records.py tests/integration/test_manual_records_cli.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

本次新增 **66 个合成用例**，本机 64 通过、2 个链接权限用例跳过；完整套件在 Python
3.11 和 3.14 均为 **634 通过、19 跳过**（16 个外部验证、3 个链接权限用例）。
Ruff、格式和严格 mypy（59 个运行模块）通过，独立复核问题均已修复并补回归。
本地实际检查为 **73/73 文件身份有效、54/54 阶段未执行、0 阶段未知**；两套后端文件
仅核对身份，没有启动进程。这些数字描述离线记录状态，不是宿主通过结果。
