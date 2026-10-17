# 音频来源绑定的估计编排候选

本开发入口把完整 vocals／bass／other 音符候选、四份分轨、未分配残差和可选节拍，
组合为独立的 `source-clock-estimated-arrangement-v1`。它提供后续转换所需的统一
中间结果，尚不生成 MIDI、FLP 或试听，也不完成共享作业或授予音乐／宿主资格。
既有 MIDI 的保真契约、精确变速、控制路由及旧裁剪／标记限制保持原状。

后续独立的[可编辑 MIDI 候选导出](ESTIMATED_MIDI.zh-CN.md)从完整 pitched／drum
生产者重建本候选，增加明确的技术时钟和误差审计。原 v1/v2 JSON 的状态、时钟和
阻塞不改变；不能把候选导出解释为原编排已经具有音乐速度、音源或 FLP 写入资格。

## 使用

已有当前完整分轨转写批次（不是单个声部）及可选当前节拍报告后：

```powershell
uv run suno2flp compose-estimated-arrangement D:\private\batch\stem-transcription.json --beats D:\private\rhythm\beats.json --output D:\private\new-arrangement
uv run suno2flp verify-estimated-arrangement D:\private\new-arrangement\estimated-arrangement.json
```

`--beats` 可以省略；此时明确保留 `rhythm-not-provided`。输入缺失、旧代码／模型
身份、来源不符或不完整批次均失败，不会下载模型、启动 DAW 或触发推理。两条
命令都消费当前完整数值与来源验证器；复核重新从当前文件构造全部派生字段，
不是新的原生模型重放，更不代表逐音符真值或音乐质量达标。

## 时间和完整性

原曲身份、解码报告、PCM、采样率、帧数和声道为共同音频时钟。每份音符输入保留
完整原生帧区间、音高、未经校准的激活、原有顺序及弯音文件／偏移。重叠音符和
弯音独立保留，不推断 MIDI 通道、程序或力度，也不把激活当作置信度。

音符边界使用现有模型 owned-row 的真实地址，转换为原曲采样和微秒的精确有理数。
窗口交界处并非均匀 256 采样，不能用拼接后行号乘固定步长。排他结束行等于完整
行数时，使用完整重采样帧数作为边界。重采样向上取整可使最后边界超过原曲不足
一个模型采样；保留精确坐标并标记 `padding`，不裁剪、舍入或移动原有估计。
这些是适配器坐标规则，不能证明神经网络起止时间准确。

可选节拍必须属于同一份原曲和解码，完整保留 beats、raw_downbeats、对齐映射、
downbeats、半帧坐标和信号观察。节拍不是拍号分母或可靠速度图，因此 tempo、
meter、structure 仍为 unavailable；本切片不进行 PPQ 或目标 MIDI 坐标转换。

## 角色与参考

| 分轨 | 角色含义 | 保留限制 |
| --- | --- | --- |
| vocals | 人声音高近似 | 不证明单声部、主旋律识别或歌声重建 |
| drums | 打击乐参考音频 | 尚未分类或转写鼓点，不套用旋律模型 |
| bass | 分离器标注的低音候选 | 不证明具体乐器或音色 |
| other | 混合 pitched 声部 | 不冒称已分出独立和声乐器 |

四份参考和未分配残差都保留从 0 到原 N 帧的独立引用，参考播放意图静音。
四份分轨是双声道 float32 WAV，残差是双声道小端 float64 原始数值流，
不是 WAV 或已可播放的轨道；候选显式记录各自编码，不改变格式或验证实际路由。
原曲也通过完整输入身份保留。默认可编辑重建、互斥参考试听
和可发声音源仍需后续实现及宿主验收，不能用参考音频掩盖缺失的 MIDI 重建。

## 发布与剩余工作

仅在新目录发布 JSON；拒绝既有目录、路径链接及与源批次／模型／受保护文件的
重叠。16MiB 上限和完整列表预算超过时明确拒绝，不截断。发布前复核当前完整
来源／依赖及冻结的代码配方，并重建候选；取消或来源变化不留下完成名。
报告保留自己的目录，复制到另一目录不能冒充原完成报告。原文件保持不变。

默认测试使用原创微小文件和真实来源验证，仅模拟已有原生进程边界；独立时钟
断言覆盖窗口间隙、重叠、尾部和分数采样。候选始终显示 unqualified_candidate，
model_qualification=not_assessed、ground_truth_metrics=unavailable、
writer_eligibility=blocked、execution_allowed=false；全无 pitched 音符时另列明确
阻塞。鼓音源映射／角色独立识别、24片段／6曲质量及校准、推断速度／结构、可播放序列化、
共享作业接入和完整 GUI／安装仍未完成。真实宿主继续等待可用音频输出及独立验收。

## 含鼓候选的独立 v2

```powershell
uv run suno2flp compose-percussion-arrangement D:\private\batch\stem-transcription.json --drums D:\private\drums\drum-transcription.json --output D:\private\new-percussion-arrangement
uv run suno2flp verify-percussion-arrangement D:\private\new-percussion-arrangement\percussion-arrangement.json
```

可选 `--beats` 沿用同一来源的节拍报告。v1 及其文件保持原有行为。新报告使用
`source-clock-estimated-arrangement-v2`，要求完整三声部批次和当前完整鼓候选，
原音频、解码、PCM、分离报告、分离重放凭据、帧数、采样率、声道及鼓参考文件的
身份逐项相同；同名、同长度不能代替共同来源。消费原有完整数值验证器，复核时从
当前生产者重新构造全部字段，不运行新的模型，也不凭完成收据跳过数值验证。

音高声部继续使用原 owned-row 坐标；鼓使用44100Hz图的几何中心 `(row-6)*256`，
转换为原采样坐标 `model_sample*original_rate/44100` 及精确微秒分数。鼓位置只含
源 event/peak 索引、原采样和微秒，没有推断 note-off、MIDI velocity、音高或通道。
保留生产者原有类别／顺序、全部 logit/velocity 浮点位和负／尾部填充排除记录；
排除峰留在输入快照中，不移入源区域。音高尾部的不足一采样 padding 也不裁剪。
这些坐标不是音乐 onset 延迟校准，九类标签不是经验证的 GM／音源路由。

报告引用完整不可变鼓生产者及全部原生见证文件身份，并保留全部峰／事件／排除
快照，不重复嵌入生产者较大的分离／后端快照。重新读取生产者时仍完整验证这些
上游内容。发布前复查全部生产者、配方、负载和原生目录成员；变更、额外成员、
取消、移动／伪造报告及与生产者目录重叠均拒绝。完成 JSON 和 pending 名称均独占。
分离、重放分离和全部三个音高声部的原生目录，均以生产者声明的见证文件集合为
期望成员；读取前已经存在的额外文件也会拒绝，不能将当前目录扫描结果当作新基准。
完整16MiB／列表预算超限时失败，不截掉峰或来源。

四份参考继续静音。v2 仅移除它新解决的 `drums-not-transcribed`，另列鼓延迟未校准、
GM 路由不可用及空鼓候选等阻塞；原模型质量、可发声路由、速度／结构、宿主与写入
限制继续保留。`status=unqualified_candidate`、`execution_allowed=false`；CLI 退出0
只表示候选 JSON 已完整发布／重建。原生重放、真实音乐质量、共享作业与 FLP 交付
仍是独立门槛，不能用这份编排将旧阻断计划升级为可写。
