# 非交互 MIDI → FLP：逐事件准备与尚未解决的写入条件

本次新增的是**可验证的生成前准备**，尚未实现任意变速、控制事件的可播放 FLP 编码。
后续[速度/控制后台实验](FL26_CONTROL_EVIDENCE.zh-CN.md)取得事件 223 的选定整数字段证据，
并发现变速调度偏差；新增只读检查及编码精度/路由分析，写入仍然阻断。
`plan-midi-performance` 不启动 FL Studio、调用 MCP 或写入 FLP。已有受限写入器
保持原有规则；报告中的 `execution_allowed=false`、`writer_eligibility=blocked`
不能通过修改 JSON 变成写入许可。

## 使用

先用已有 `prepare-project` 获得未改变原始演奏的 arrangement。多个独立 MIDI 中
相同的通道编号不会合并。

```powershell
uv run suno2flp plan-midi-performance my-song/intermediate/prepare-001/arrangement.json --target-ppq 960 --output my-song/intermediate/performance-960.json
uv run suno2flp verify-midi-performance my-song/intermediate/performance-960.json
```

只独占创建新 JSON。返回 0 表示准备/重放成功，**不是工程可写或歌曲交付成功**；
命令始终提示 FLP execution blocked。输入损坏、源文件不符、伪造 arrangement、
既有输出或重放失败返回非零。API 为 `plan_performance_file(path, target_ppq=...)`
及 `verify_performance_file(path)`。省略 PPQ 时取 arrangement PPQ；显式范围
1..65535 来自文件头存储边界，不表示宿主支持全部这些值，也不会改变模板头。

## 精确保留的内容

- 保存完整 arrangement、原始 MIDI 导入快照、源 SHA-256、大小/修改时间、选项、
  角色说明和诊断。当前输入须独立重导入、重建并逐字段一致。
- 保留所有源轨道及事件顺序，包括同 tick 事件、重复速度、控制专用轨道、空轨道及
  end-of-track。地址用 input index、track position、event index；原始 track index
  另存，不能用一个跨文件的 channel 代替来源。
- `tracks[].events[]` 指向同一报告 `arrangement.sources[].midi.tracks[]` 中的完整
  原消息、delta 和 tick。原始 MIDI 通道及数值不变。
- 每个事件、轨道结尾及音符起止都记录目标 tick 和从零开始的微秒；使用约分后的
  `{numerator, denominator}`，不经浮点数或取整。
- 分段积分 `tick差 / PPQ × microseconds_per_beat`，音符跨越速度切换时计算完整
  速度图。有效图用于积分；所有重复原始速度消息仍保留。缺省速度/拍号维持 default 标记。
- 每个有效速度保留精确 `milli_bpm = 60,000,000,000 / microseconds_per_beat`。
  分母为 1 才提供 `exact_milli_bpm`，否则为 null；没有近似替代值。

`target_grid_exact` 仅表示全部检查坐标为整数目标 tick；超出写入器 32 位范围另报。
`tempo_scalar_exact` 仅表示整数毫 BPM 可表示性；值域另报。两者为 true 也不代表
自动化、模板、控制路由或宿主已经验证。

要求原始演奏不变时，先前允许 PPQ 取整的策略、被覆盖的源速度/拍号图、选中且确有
变化的 cleanup 都会被拒绝，应重新使用原始导入。无变化 cleanup 可重放。零长度
音符不会自动延长，重叠警告不会消除；这些情况继续进入阻塞诊断。

`untranslated_events` 列出当前写入器不能翻译的事件及来源/通道，包括 program
change、CC、pitch bend、aftertouch、sysex 等。它们存在于快照并不等于在 FLP 中生效。

如果上游曾创建派生 MIDI，这里只认证声明的当前 MIDI，不会声称认证其更早原件。
原件到派生文件的修改记录、原件哈希和归档仍须随私有交付包保留；本地歌曲评估同时
核对既有源准备链，该链没有上传到仓库。

## 编码证据与阻塞

Image-Line [工具栏说明](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/toolbar_panels.htm)
描述的精细速度单位为 1/1000 BPM，现有写入器使用整数标量。MIDI 的整数微秒/拍
不一定能精确换成它。提高 PPQ 改善的是位置网格，不能修复速度数值误差；不能先
四舍五入再宣称原始时序未变。这只否定**当前标量表示**的精确可行性，不是证明
所有 FLP 自动化表示都不可能；另一种表示及其宿主行为仍需证据。

固定版本 [PyFLP pattern](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/pattern.py)
仍有未知 controller 字段及不确定的位置含义，
[controller](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/controller.py)
也没有完整 MIDI 控制消息编码。这是既有 GPL-3.0-or-later 候选的只读研究，未复制
实现或引入依赖，不能作为本项目 FL26 写入的充分依据。

官方 [MIDI Out](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/MIDI%20Out.htm)
要求明确的目标端口/插件路由，而且自身不发声。不能把 CC7 直接当作 FL 通道音量，
也不能把 program change 的乐器名称当作已经完成音色切换。

## 后台实测范围

一次明确授权的本地操作使用签名有效的 FL Studio 26.1.7.5654，将官方空模板和独立
正向参考复制到新目录，使用官方
[命令行导出选项](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/fformats_save_export.htm)
启动后台进程，没有点击、键盘或鼠标操作。空模板副本生成静音 WAV；有音符参考副本
两次独立进程生成非静音 WAV，176,860 个 PCM 样本一致。合成 MIDI 单次调用 60 秒
无输出，仅终止该次拥有的进程；窗口句柄存在，具体等待原因未核实。Hidden 启动
不保证无窗口。该结果不是所有 MIDI 接口不支持的证明，也不是产品已有宿主控制器。

官方当前文档没有明确的“导入 MIDI 后另存新 FLP”命令。已有 FLP 渲染成功不等于
完成该步骤；参考音频不是歌曲交付，不能解除裁剪、片段标记、缩放、另存和试听的
待验收状态。后台进程授权也不会转换为界面输入授权。

## 下一编码阶段的门槛

1. 验证 FL26 速度自动化的参数地址、精度、时间单位及阶跃/插值行为。源速度不可精确
   表示时继续阻断；误差容限必须另行明确授权。
2. 为每个源事件建立可回读的控制/程序路由，保持不同来源的通道用途独立；核实插件
   和声音依赖，不能忽略末尾 CC 或只保存旁车。
3. 解决零长度/重叠音符及模板阻塞，编码后独立回读全部事件，再用新副本后台渲染。
4. 真实歌曲的新 FLP、重开、音色及人工试听未完成前，不宣布整个项目可用。合成测试
   验证的是准备契约，当前写入器门槛没有改变。

## 本批验证

新增 32 项原始合成用例，覆盖跨速度积分、初始缺省速度、不同 PPQ、同 tick 顺序、
跨文件同通道、控制专用轨道、清理/时序覆盖拒绝、零长度、坐标范围、保存报告篡改、
当前源变化和独占输出。完整本地测试为 774 通过、19 项显式跳过；Ruff、162 文件格式
检查及 71 模块严格类型检查通过。源码包/wheel 构建成功，安装后的 CLI 流程也验证了
变速/控制准备、重放、输出复用拒绝及故意损坏报告的拒绝。

独立审查发现发布大报告期间源文件变化仍可能返回成功；已先用失败测试复现，再在
序列化后、发布后重新核对源身份。失败时仅保留新诊断产物，不返回“source verified”。
源与目标的检查以可信本地工作区为边界，不是对恶意同用户并发文件替换的 OS 隔离。
实际宿主/私有报告未由代码审查者重复运行；它们的来源记录只留本地。
