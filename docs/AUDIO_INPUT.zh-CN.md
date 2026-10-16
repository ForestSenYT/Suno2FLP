# 只读音频输入预检

`importer.audio.inspect_audio` 检查原文件结构并生成 `pcm-wave-preflight-v1` 报告，
不改写、截断、重采样或推断音符。此切片支持普通 RIFF/WAVE 的整数 PCM：1／2 声道、
8／16／24／32 位、8–192 kHz、非空、最多 10 分钟及 1 GiB。

预检契约保持不变。共享作业随后可运行独立的[PCM 解码与逐样本核验](AUDIO_DECODE.zh-CN.md)，
输出新的分析文件；这不会放宽这里的源格式限制。

报告保留原文件 SHA-256／大小／mtime、全部块的原始 ID／偏移／长度、data 偏移及
完整 PCM 数据哈希、帧数和有理数微秒时长。时长由整数帧数及采样率精确计算。
未知元数据块按长度及 WORD 填充跳过，仍保留块清单；不将元数据当作音频。

RIFF 长度必须覆盖整个文件，每个块和填充都不得越界；必须有且只有一个 fmt 和 data，
块对齐／字节率／样本位宽必须一致。拒绝空数据和不完整帧，不能通过向下取整丢弃数据。
处理采用有界流式读取，限制块数和 fmt 大小，读取前后核对完整源身份。
容器／PCM 矛盾返回 `audio_invalid`（failed）。源文件读取中改变则拒绝并保留
`offline_input_changed`；I/O 失败在作业运行中记录为 `audio_io_failed`。

MP3／FLAC、RF64／大端 RIFX 返回 `audio_format_unavailable`（blocked）；浮点、
WAVE_FORMAT_EXTENSIBLE 及其他 codec 返回 `audio_codec_unavailable`（blocked）。
声道／采样率／时长／资源超限返回 `audio_limits_exceeded`（blocked）。这些限制描述
当前预检适配器，后续解码路线须单独集成、固定版本和验证；不能把改扩展名当作转换。

预检只证明结构和当前文件一致，`musical_correctness=not_assessed`、
`host_compatibility=unverified`、`writer_eligibility=blocked`。它不证明非静音、音质、
分轨质量、转写正确或 FL Studio 可用。作业仍在第一个缺失 worker 处阻断。

格式规则依据 Microsoft [RIFF 格式](https://learn.microsoft.com/en-us/windows/win32/xaudio2/resource-interchange-file-format--riff-)
和 [WAVEFORMATEX](https://learn.microsoft.com/en-us/previous-versions/dd757713(v=vs.85))；
测试采用仓库原创小型 PCM／损坏 RIFF 夹具，无真实歌曲或私有工程。

本地真实歌曲只读预检得到 48 kHz、双声道、16 位、8,400,000 帧和精确 175 秒；
任务完成 input 后以 `worker_unavailable` 阻断。原素材、基准、旧实验和运行时文件
身份复核一致。真实预检记录留在忽略目录；未启动宿主、未生成 FLP，结果不构成音乐
或宿主验收。
