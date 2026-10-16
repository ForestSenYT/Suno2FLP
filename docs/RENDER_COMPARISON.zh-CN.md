# 离线 PCM 渲染比较

```powershell
uv run suno2flp compare-renders reference.wav candidate.wav --output measurements-new.json
uv run suno2flp compare-renders reference.wav candidate.wav --max-rms-error 0.001 --output tolerance-new.json
```

明确选择两份**已经存在**且应在同一时间轴对齐的 WAV。命令不操作 FL Studio、不渲染、
不推断对齐、不转换格式、不重采样、不调整增益、不识别乐器或重建音频。它使用标准库
流式读取与哈希，不依赖 FFmpeg、模型或额外音频库，输入始终只读。

当前支持未压缩整数 PCM：8 位无符号、16/24/32 位有符号小端。两份文件必须有相同的
采样率、通道数、位深和帧数，且非空；压缩、浮点、损坏、截断、缺失或格式不一致时
明确失败，不截取共同部分来掩盖长度差异。通道按原始交错顺序逐样本比较。

支持范围限定为小端 RIFF/WAVE、经典 PCM 格式码 1，且只有一个 `fmt ` 和 `data`。
独立核对 RIFF 总长度、所有块的声明范围与填充、格式字段和完整帧边界，不能只依赖
标准库向下取整的帧数；半个样本、缺少通道数据或超出文件的声明一律失败。可跳过
合法附属块；允许标准库输出的末尾奇数长度 PCM8 数据省略最后填充字节，不能隐藏
后续块。块长度/填充规则参考 [Microsoft RIFF 说明](https://learn.microsoft.com/en-us/windows/win32/xaudio2/resource-interchange-file-format--riff-)。

报告保留原始文件路径/SHA-256/大小/修改时间、采样率、通道、位深、帧数与比较样本数。
数值按 `2^(bits-1)` 归一化，记录两份 RMS、差值 RMS、最大绝对差值和满量程样本数量。
“满量程”只表示样本位于整数最小/最大值，**不证明已经发生可听削波**。
`samples_identical` 比较 PCM 样本，不要求 WAV 元数据/文件总哈希相同。

没有 `--max-rms-error` 时只给测量，`within_tolerance=null`；有效测量返回 0，并不表示
质量验收。指定有限非负阈值时，仅按差值 RMS 是否不大于该数值判断；超限保留测量和
诊断，返回 1。阈值是使用者选择，不是通用音乐质量标准，也不能将音色不同的 Suno
参考 stem 与 FL Studio 乐器渲染直接要求逐样本一致。

所有报告固定 `audible_acceptance=unverified`、`host_compatibility=unverified`、
`writer_eligibility=blocked`、`execution_allowed=false`。数值相同不代替人工试听或真实
宿主打开/重开、乐器、裁剪及片段标记验收。报告只能独占新建 `.json`，不能覆盖或占用
已知输入位置，包括已缺失的输入；原始 WAV、私有渲染和报告只留本地。

数据按约 64 KiB 帧块处理，身份核对也流式进行；文件和参数不变时结果可重复。读取前后
再次核对身份，变化会使结果无效。这是可信本地文件的结构/数值检查，不是敌对并发文件
系统隔离或主观听感模型。真实 FL Studio 渲染和试听仍待独立宿主证据。
