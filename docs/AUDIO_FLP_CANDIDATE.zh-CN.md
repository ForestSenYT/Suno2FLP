# 音频推断 MIDI 的 FL26 工程候选

本命令将完整当前音频推断 MIDI 投影为**未验收的可编辑 FLP 候选**，不处理既有
MIDI 的变速／程序／控制事件，也不改变旧 writer、模板和实验的资格。
选型依据见[先调研再实验的路径对照](research/2026-10-17-noninteractive-delivery-paths.zh-CN.md)。

## 明确入口与前提

```powershell
uv run suno2flp export-audio-flp C:/Candidates/midi/estimated-midi.json --base C:/References/base.flp --sampler C:/References/sampler.flp --output C:/Candidates/new-flp-001
uv run suno2flp verify-audio-flp C:/Candidates/new-flp-001/audio-flp.json
```

必须是原目录中完成的 `estimated-midi.json`，并重新检查完整当前 producer、原数值、
MIDI 字节、模型 payload 成员、源文件及代码身份；不是信任报告的状态／哈希声明。
本调用只建立一次完整数值关系，随后用不可序列化的当前调用守卫复核，避免重复推理。
不会启动模型、插件或 FL Studio。验证命令也不修复、重写或升级资格。

两个参考组件须分别匹配 `audio_profile.py` 中固定的完整 SHA-256：独立宿主序列化的
普通 3x Osc 基础工程，以及经独立小型宿主实验验证的 built-in Sampler 参考。
任意同版模板、自报 attestation 或仅相同插件名都不够；缺失／不一致时明确失败。
这些私有参考、插件状态和宿主不在 Git、wheel 或 sdist 内；当前没有面向普通用户的
参考组件自动准备／分发流程。这是本地研发入口，尚非 GUI 成品转换功能。

## 内容、时钟与近似

- 三个 pitched 声部映射至通道 0／1／2，分别为 vocals 近似、bass、other 混合声部。
  均复制固定 3x Osc 状态，不推断已经识别真实乐器。
- 九类鼓点显式选择通道 3–11；原预览 MIDI 键依次为 49、51、42、46、36、38、43、48、47。
  FLP 内以 root60 触发各自 one-shot 音色。原键、来源 part／occurrence、原时间与
  误差仍保留在完整源审计和派生路由；没有把鼓类索引冒充旋律音高。
- 鼓音色由原创标准库 DSP 生成，固定运行时内可重现，不复制 FL Studio 工厂采样。
  它们是近似预览音色；one-shot 发声尾部独立于预览 MIDI 的声明性 50ms note-off。
- 保留投影后的每个音符开始／结束 tick、次数及顺序。固定 960 PPQ／500000us
  技术时钟，不再次量化，不把 120 BPM 宣称为歌曲速度。源音频坐标和前一投影的
  有理数舍入误差保留；已有 MIDI 不进入此路径。
- 固定 native volume raw1280 降低预览混合电平。宿主对照测得的响应不是简单的
  1280/10000 线性比例，因此报告只声明原始参数策略。它不代表混音／动态质量达标。
- 普通非截断片段覆盖全部源 extent，另加至少 3840 tick 的明确尾部空间并对齐技术小节。
  除开始／长度／整数 Pattern 裁剪端点外，全部 88 字节片段原样保留。
  不支持旧截断边缘、未知 flag／crop、任意新插件或模板编辑。

产物包含 `project.flp`、九个 `audio/drum-*.wav`、未改的 `candidate.mid`、完整
`source-midi.json`、`README.txt` 及候选报告。音频引用使用包内相对路径。
源分轨身份仍在审计中；本切片**尚未把参考分轨放入 FLP playlist**，不能据此完成
最终“可编辑音符＋分轨”的产品验收。

## 写入／输出检查

纯编码器不访问文件或宿主。独立 verifier 不调用 encoder；逐一检查完整 header、
所有全局／通道事件、非修改的 opaque 字节、24-byte 音符和 88-byte 片段及其尾部。
字段修改预算仅含通道 ID／名称／启用、已观察音量、包内样本引用、音符音乐字段、
PPQ／channel count 和 clip 范围。原 cut-group、插件参数及其余信息保留。

输出目录必须不存在，已有父目录必需；路径解析、链接／重叠保护在昂贵重建前及
发布前执行。每份产物独占创建；pending JSON 写入后完整复核当前来源、全部输出
成员／原字节和解释器／代码，最后用独占硬链接提交完成名称。失败保留诊断产物，
不覆盖旧结果，也没有成功标记。独立验证重新生成音色、源审计和路由，不只比自报摘要。

## 本地证据与保留限制

独立小型参考已观察：非截断 960 PPQ 对照；三个 3x Osc 通道；九类 Sampler 路由；
三音和弦与独立单音和的最大一单位 PCM 误差；包内样本相对路径在中文／空格路径
搬移后两次音频完全一致；预览音量参数有实际衰减、参考混合无削波。
这些证据不泛化为任意工程、音色或歌曲的资格。

命令输出始终为 `unqualified_candidate`、`host_compatibility=unverified`、
`listening=not_performed`。真实宿主渲染／ZIP／新目录重开记录是另立的本地证据，
不能重写来源报告，把旧 blocked 改成 ready，或替代人类音乐试听及正式质量曲库。
无真值单曲不能报告音符 F1；节拍／拍号／结构、模型资格、弯音重建、GUI／安装和
完整发布要求继续保留。按当前设计，先提供可试听候选，再分别完成这些门槛。
