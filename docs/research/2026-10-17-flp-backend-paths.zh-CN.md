# FLP 后端路径复核：完整写入器与宿主桥接

2026-10-17。**只读研究完成；没有替换后端或新增兼容性资格。** 本轮重读固定源码、
元数据和许可；没有安装／执行上游、生成 FLP、启动宿主或上传私有素材。
Firecrawl 搜索／读取后遇共享速率限制，其余公开源通过 GitHub 连接器读取。
以下最小实验均为建议，未执行。

沿用[完整产品设计](../superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
与[交付路线](../DELIVERY_ROADMAP.zh-CN.md)：先取得明确标注的未获资格候选，再完成
音源、重开、渲染、音乐质量、GUI 与分发验收。已有 MIDI 的精确事件／通道／时钟
要求不能因为选择其他写入器而降低。

## 判断

尚无证据表明下面任何完整后端能直接替代现有 **26.1.7.5654 受限参考**并减少总工作量。
最值得保留的分工是：现有原创窄写入器承担已证实字段，Music2DAW 适配版作独立只读
交叉检查，DawVert 作有限格式规则参考。完整 DawVert 是真正的另一路新工程生成器，
但它增加格式转换和运行时工作；PyFLP 与 demixer 也没有补上 FL26 证据。
这是源码和现有本地证据上的工程判断，不是新的运行结果。

本地既有对照已验证采样器作用域规则和九路原创音源调度；该结论只覆盖固定参考，
不覆盖实际鼓音色、完整歌曲或发布。重复证明这两个点的实验收益有限；下一实验应
回答尚未解决的可移植路径、完整歌曲编排或宿主重开问题。
[现有写入边界](../FL26_WRITER.md)、[独立输出检查](../FL26_BUNDLE_VERIFICATION.md)。

## 固定身份、运行时与采用条件

本轮 GitHub HEAD 查询均与以下 pin 相同；这是查询时状态，不是未来更新保证。
[DawVert][d-head]、[PyFLP][p-head]、[Music2DAW][m-head]、[demixer][x-head]、[额外桥接][g-head]。

| 路径 | 固定提交 | 运行时／许可与采用约束 |
| --- | --- | --- |
| DawVert 完整转换器 | `c6c8be9e0660d9e75a3acecce43a13b0dbe0029c` | Python 3；审查的 requirements 未锁版本，含 numpy／av／mido 和 Git URL 依赖；源码 GPL-3.0-or-later。全转换器还需要数据／插件转换模块，不能只安装一个 FLP 文件。[依赖][d-deps]、[许可][d-license] |
| PyFLP | `f937126b888ce94271bfea631b89166c74056530` | Python >=3.8；construct-typing 等仅设下界；元数据 GPL-3.0，源码允许 later。demixer 的测试有 CPython 3.11.15 枚举私有补丁，不能把声明版本范围当作已验证运行环境。[元数据][p-meta]、[许可][p-license]、[补丁证据][x-tests] |
| Music2DAW / jihadkhawaja/flstudio-mcp | `6def9463d6fa8636bbc81010581318a39c47d3c4` | net10.0、DryWetMidi 8.0.3；GPL-3.0-or-later。已有隔离 SDK 10.0.401／runtime 10.0.12 的本地只读证据；不等于编辑器资格。[项目][m-project]、[许可][m-license]、[适配范围](../FL26_BACKEND_ADAPTATION.md) |
| demixer | `7865ce616d4f8d3755078bbc30d4bd2da5b0a70a` | Python >=3.11,<3.12；正式依赖为空，writer 实际导入 pretty_midi，开发依赖含 PyFLP；AGPL-3.0-or-later。完整音频／模型流程另有未闭合依赖，不能从仓库现成推导可安装产品。[元数据][x-meta]、[许可][x-license] |
| geezoria/FLStudioMCP | `3aa5f39c7321a00976c4a8b5c75c71365f439d53` | MIT、Python >=3.10，mcp／anyio／pydantic 仅设下界；宿主内 controller 与 Piano roll 脚本另需安装／激活。[元数据][g-meta]、[许可][g-license] |

GPL／AGPL 实现不能直接作为本项目 MIT 源码复制或打包；若选用，需按实际分发形式
处理通知、修改与对应源码义务。独立进程不自动免除许可条件。MIT 桥接也仍有运行和
验收成本；不随研究分发 FL Studio、插件状态或未经许可的音源。

## 实际代码入口与限制

| 路径 | 可调用入口与确实实现的能力 | 时钟、音符、音源／路径限制 |
| --- | --- | --- |
| **完整 DawVert** | `dawvert_cmd.py -it midi -i input.mid -ot flp -o new.flp`；MIDI reader → 中间工程 → `plugins/output/flp.py:output_cvpjs.parse` → `flp_project.make`；能新建通道、Pattern、playlist、Sampler／部分插件。[MIDI 输入][d-midi]、[命令入口][d-cli]、[出口][d-output] | 出口强制 `ppq=96`、重算时间后 `int()` 写音符／片段；底层写 `int(tempo)*1000`，不是保留小数 BPM。音符排序且未设置 `midich`，其默认 0；不能假定源通道、事件顺序或全部 CC／速度图精确保留。Sampler 从样本引用取 Windows 路径，插件转换／样本可用性与可移植包仍要验证。底层 `make` 用 `wb`；CLI 的覆盖询问不能替代独占发布。[低层写入][d-project] |
| **PyFLP** | `pyflp.parse(existing)` → 修改模型 → `pyflp.save(project,new)`；有 24-byte 音符、现有 Sampler 路径／参数编辑；审查的公共 API 无完整空白工程／新通道／新 Pattern 工厂。[入口][p-io]、[通道][p-channel] | PPQ setter 不重算时间；只接受限定 PPQ 集合。路径字段存在不代表复制／定位音源；新结构仍需手工组装事件和 ID。save 用 `wb`，没有本项目的源身份与不覆盖保护。[PPQ][p-project] |
| **Music2DAW** | `music2daw edit source.flp output.flp request.json`；改现有通道／Pattern 的音符、playlist、单一 tempo 和插件状态复制。[模型][m-models]、[编辑器][m-editor] | 需要现有结构；无 PPQ setter、速度／拍号图、源 MIDI-channel／任意 CC 事件字段，也不是新建任意 Sampler／样本路径 API。tempo 0.001 BPM 分辨率，源标量仍需可表示性检查。playlist crop 写 float；不能用它覆盖已验证的整数 Pattern crop 语义。最终 `File.Move(...overwrite:true)` 不符合独占输出。 |
| **demixer** | `demixer.core.project.flstudio.write_flp`；无需模板，写 stem Sampler、对应音符 Pattern 和 playlist。[写入器][x-writer] | 固定 PPQ96；pretty_midi 秒数按一个 BPM 舍入，长度至少 1 tick；一个 MIDI 的全部 instruments 合入一个 rack 通道，note MIDI-channel=0。音符进入没有 sample 的静音 Sampler，参考 WAV 另发声，不能作为“可编辑重建”试听。样本引用 `.resolve()` 绝对路径，输出 `wb`；不保留模板状态／源事件流。 |
| **geezoria MCP** | `file_bridge.stage_and_run` 经 JSON 文件请求 Piano roll 脚本；controller TCP 桥提供部分实时操作。[请求桥][g-file]、[实际 handlers][g-device] | 实际 `keystroke.py` 恢复并前置宿主窗口，用 Win32 SendInput 发送 Ctrl+Alt+Y。[按键实现][g-keys] `playlist.placePattern` 返回未支持；new/open 需 UI，save-as 会弹文件名，render 返回需手动对话框。不是离线 FLP writer；工具注册数量不等于端到端能力。 |

## FL26 的关键反证

我们的精确构建证据是 **先读版本，再按 event172=3 字节、event233=88 字节**处理；
保留完整 88-byte 记录，不从长度能否整除猜格式。[FL26 字段边界](../FL26_READ_ONLY.md)。

- **DawVert**：`format_flp_tlv` 对 128..191 全读 uint32，没有 172 例外。
  clip reader 在新版本读 60 字节，writer 只写 32 字节，`make` 声明 FL20.7.2.1852。
  没有审到 88-byte 分支。[TLV][d-tlv]、[clip][d-clip]、[make][d-project]。
- **PyFLP**：通用 DWORD 分支读 4 字节；playlist sizes 仅 `[32,60]`，且按 `%60`
  选择新格式，没有精确 FL26 profile。[parse][p-io]、[playlist][p-arr]。
- **Music2DAW**：原 parser 与 editor **各有自己的事件读取器**，两者均把该范围读成
  4 字节；两者 playlist 均仅 80/60/32。现有本地适配只改 parser 的 inspect 路径，
  editor `ReadEvents`、`GetPlaylistRecordSize` 仍未改；“适配 inspect 成功”不能推出
  edit 成功。[parser][m-parser]、[editor][m-editor]、[本地适配](../FL26_BACKEND_ADAPTATION.md)。
- **demixer**：新文件声明 FL21.0.3.3517，emit 32-byte playlist，未处理既有 FL26。
  上游测试主要经 PyFLP 重读，没有真实 FL26 宿主验收。[writer][x-writer]、[tests][x-tests]。

**写旧版本新文件与读写 FL26 原生文件是两件事。** FL26 可能导入旧格式；上述缺少
172／88 支持并不单独证明其新建旧格式文件必失败。但当前没有这条导入、另存、重开、
完整试听链的本地证据，也不能仅修改版本字符串取得支持。

## 最小可证伪的后续离线实验

仅在另行实施时使用原创极小 fixture、全新目录和独立读回；不触碰原件。
共同检查项：完整输入身份、音符／片段 ID、路径、所有未授权字节和禁止覆盖行为。

| 候选 | 最小实验与明确停止条件 | 相比现有参考能省什么 |
| --- | --- | --- |
| DawVert 全路径 | PPQ960 的两个音符（含 tick1）、120.125 BPM、不同源通道；经完整 MIDI→FLP 路径，用独立 reader 比较。任一 tick／BPM／通道变化即拒作严格 MIDI 后端；源码已预示会失败，不必先跑真实歌。另以极小中间工程测试便携 sample 路径和新通道关系。 | 可能省新工程骨架／插件转换编写；修复精度、许可、依赖、路径和宿主验收的成本尚未证明更小。底层 `make` 虽可设其他 PPQ，仍有整数 BPM 和旧格式，不能替完整出口背书。 |
| PyFLP | 原创 FL26：172 后紧跟已知 tempo／note；分别 1、4、10、15 个 88-byte clips，parse/save 后逐字节比较。任何错位／丢记录即停止；这些数量同时检查旧 stride 整除误判。 | 能提供第二解析器框架，但先要补 framing、88-byte 和结构构造，收益偏小。 |
| Music2DAW | 同一 corpus 分别经过 adapted inspect 和 **独立 editor** 的空请求／单音符修改；检查完整记录和非修改 bytes。inspect 通过而 edit 错位即停止，不启动宿主。 | 现有只读进程最易复用；要采用 editor 需独立适配、源码身份和新资格，不能复用旧 inspection 结论。 |
| demixer | 一个 PPQ960、tick1 音符及两个源 instrument；生成后核对 tick／rack／midich／音源绑定和相对路径。舍入、合并或静音音符通道任一项即拒作正式重建。 | 小型 writer 易读，但已验证窄参考具备更强的音源／调度证据，直接迁入收益低。 |
| geezoria | 不启动宿主；以假的 FL API／按键函数检查 stage_and_run 必须调用 hotkey、placePattern／render 返回失败、save-as 无完成文件证据。 | 可研究手动辅助交互；不能省当前要求的后台新工程生成／完整验收。 |

优先级判断：保留现有窄参考，先离线核对可移植音源路径与完整候选字段，再决定新的
受限宿主实验。若需要真正不同的全 writer 对照，DawVert 优于重复采样器试探，但只作为
独立旧格式候选，不能承接严格 MIDI 或 FL26 模板编辑。是否能少写代码、运行更稳及
音乐更好仍未知；现有参考也仍未取得完整产品资格。

[d-head]: https://api.github.com/repos/DawVert/DawVert/commits/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c
[p-head]: https://api.github.com/repos/demberto/PyFLP/commits/f937126b888ce94271bfea631b89166c74056530
[m-head]: https://api.github.com/repos/jihadkhawaja/flstudio-mcp/commits/6def9463d6fa8636bbc81010581318a39c47d3c4
[x-head]: https://api.github.com/repos/revoydotdev/demixer/commits/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a
[g-head]: https://api.github.com/repos/geezoria/FLStudioMCP/commits/3aa5f39c7321a00976c4a8b5c75c71365f439d53
[d-deps]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/requirements.txt
[d-license]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/LICENSE
[d-midi]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/plugins/input/rm_midi.py
[d-cli]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/dawvert_cmd.py
[d-output]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/plugins/output/flp.py
[d-project]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/objects/file_proj/proj_flp.py
[d-tlv]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/functions_plugin/format_flp_tlv.py
[d-clip]: https://github.com/DawVert/DawVert/blob/c6c8be9e0660d9e75a3acecce43a13b0dbe0029c/objects/file_proj/_flp/arrangement.py
[p-meta]: https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyproject.toml
[p-license]: https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/LICENSE
[p-io]: https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/__init__.py
[p-channel]: https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/channel.py
[p-project]: https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/project.py
[p-arr]: https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/arrangement.py
[m-project]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/Music2Daw.Core.csproj
[m-license]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/LICENSE
[m-parser]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Monad.FLParser/ProjectParser.cs
[m-editor]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/FlpProjectEditor.cs
[m-models]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/FlpEditModels.cs
[x-meta]: https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/pyproject.toml
[x-license]: https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/LICENSE
[x-writer]: https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/src/demixer/core/project/flstudio.py
[x-tests]: https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/tests/test_project_flstudio.py
[g-meta]: https://github.com/geezoria/FLStudioMCP/blob/3aa5f39c7321a00976c4a8b5c75c71365f439d53/pyproject.toml
[g-license]: https://github.com/geezoria/FLStudioMCP/blob/3aa5f39c7321a00976c4a8b5c75c71365f439d53/LICENSE
[g-file]: https://github.com/geezoria/FLStudioMCP/blob/3aa5f39c7321a00976c4a8b5c75c71365f439d53/src/fl_studio_mcp/file_bridge.py
[g-device]: https://github.com/geezoria/FLStudioMCP/blob/3aa5f39c7321a00976c4a8b5c75c71365f439d53/fl_bridge/device_FLStudioMCP.py
[g-keys]: https://github.com/geezoria/FLStudioMCP/blob/3aa5f39c7321a00976c4a8b5c75c71365f439d53/src/fl_studio_mcp/keystroke.py
