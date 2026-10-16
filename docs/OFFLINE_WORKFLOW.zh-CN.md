# 离线准备与结构验收

这些命令不打开 FL Studio、不加载插件、不调用 DAW，不改变现有写入门槛。
结构验收通过仅说明记录与当前原始输入一致；宿主打开、声音与完整 FLP 兼容性仍未验证。

## 一键离线准备

```powershell
uv run suno2flp init-project demo
# 将自己的 .mid/.midi 和可选 .wav 放到 demo/input。
uv run suno2flp prepare-project demo --output-dir demo/intermediate/prepare-001
uv run suno2flp verify-preparation demo/intermediate/prepare-001/run.json
```

`prepare-project` 读取项目 YAML，发现并固定输入身份，导入全部 MIDI，应用**配置中显式
启用**的清理，再生成忠实编排和当前源回放质量报告。默认清理全部关闭，保留原始事件与
时间。WAV 只作发现/元数据和身份记录，不推断其音符、配器或声音相似性。
多 MIDI 按配置目录及文件排序编号，所有轨道在零拍对齐；冲突的时间图默认拒绝。

可用 `--target-ppq N` 指定精确目标 PPQ，`--timing-source N` 显式选择时间图权威，
`--instruments roles.yaml` 应用明确来源索引/通道的角色映射。先查看输入/编排并核对选择器；
没有插件自动加载、乐器识别或源通道重写。配置清理使用 active 视图，完整记录选择。
此命令不允许 PPQ 近似取整，也不静默忽略已选后端或 reinterpretation：配置必须 faithful
且 integrations 全为 none。需要原有模板检查/受限构建时，使用各自独立命令和资格门槛。

输出必须是项目 `intermediate_directory` 下尚不存在的新目录，父目录须存在；不得是
输入目录、原 intermediate 本身、最终输出目录、链接或后端安装内目录。每次运行换新名。
典型内容：

```text
prepare-001/
  assets.json          各输入目录的发现记录
  midi-0000.json       原始或已声明清理的完整 MIDI 表示；多份依次编号
  arrangement.json    忠实编排、PPQ/时间图选择、角色和原始来源快照
  quality.json        从原始导入回放后的结构验收
  run.json            配置/输入/可选模板和角色文件身份、产物身份及参数
```

所有计算与初始检查在建输出目录前完成，文件独占创建，`run.json` 最后写入；随后再次
从磁盘做完整验证才返回成功。失败留下的新目录用于排查，不能覆盖重用；没有有效且可
验证的 `run.json` 不算完成。可信本地文件系统范围内工作，不提供敌对并发修改或断电事务
保证；保存完成后仍应使用 `verify-preparation`，不能只看标志文件存在。

验证器核对当前输入/配置、整个产物集合、路径及身份，然后重新发现、导入、清理、编排，
比较每个规范化产物的全部字节。即使人为重算了被改产物的哈希，也不能绕过当前源回放。
新增、消失或过期的文件均失败；不修复证据或启动任何后端。未变输入与参数下，音乐、
导入、发现和质量产物可重复；`run.json` 保留各次输出路径与文件时间，不承诺逐次相同。

成功状态 `offline_ready` 只说明这些离线中间产物就绪，不是 FLP 已生成或宿主验收通过。
`run.json` 固定宿主 unverified、写入 blocked、执行 false，不被写入器作为许可读取。
私有输入、角色文件、输出和运行清单均应保留在本地忽略工作目录。

## 对编排做当前源文件回放验收

```powershell
uv run suno2flp verify-arrangement arrangement.json --output quality-new.json
```

命令重新读取每份原始 MIDI，核对完整导入快照和源哈希；有清理记录时，从原始导入重新
执行声明的清理，再按记录的 PPQ、时间图策略、音符视图和角色规则重建编排。
输出比较覆盖全部轨道/音符/原始事件、来源索引、原始时间、有效时间图、角色及诊断。
外部角色配置若有记录的文件路径，也核对当前配置与原有文档。

缺失、变化、伪造或无法回放的证据返回 1，报告具体诊断；成功返回 0。省略 `--output`
时输出 JSON；报告只能新建，不能占用任何已知输入位置，包括已缺失的输入。
源文件和报告都不允许链接/reparse 歧义路径。检查前后保留身份并再次核对。

报告中的 `valid` 是结构和回放结果，指纹是当前快照一致性依据，不是签名或声音质量。
题名等声明元数据不能从 MIDI 认证；内联角色文档也只验证其回放一致性。
`host_compatibility` 永远为 `unverified`，`writer_eligibility` 为 `blocked`，
`execution_allowed` 为 false。本报告不被生产写入器作为资格授权读取。

原始事件与时间始终保留；显式清理或此前显式取整不等于“未改变演奏”。结构回放只确认
与记录的选择相符，不能把曾有取整的编排提升为原始时间精确保真或 FLP 写入资格。
