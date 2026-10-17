# 音频来源绑定的估计编排候选

本开发入口把完整 vocals／bass／other 音符候选、四份分轨、未分配残差和可选节拍，
组合为独立的 `source-clock-estimated-arrangement-v1`。它提供后续转换所需的统一
中间结果，尚不生成 MIDI、FLP 或试听，也不完成共享作业或授予音乐／宿主资格。
既有 MIDI 的保真契约、精确变速、控制路由及旧裁剪／标记限制保持原状。

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
阻塞。鼓／角色独立识别、24片段／6曲质量及校准、推断速度／结构、可播放序列化、
共享作业接入和完整 GUI／安装仍未完成。真实宿主继续等待可用音频输出及独立验收。
