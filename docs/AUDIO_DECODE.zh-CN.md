# 保留原采样时序的 PCM 解码

M2 首个解码切片已实现：普通整数 PCM WAV 经只读预检后，写入新的分析用浮点 PCM，
再逐样本独立验证；共享作业完成 input／decode，随后在分轨分离处阻断。
完整音频转 FLP 尚未交付。MP3／FLAC 和源浮点／extensible WAV 继续明确阻断。

## 样本与时间

输入沿用[严格预检](AUDIO_INPUT.zh-CN.md)：单／双声道、8／16／24／32 位整数 PCM、
8–192 kHz、非空、最长 600 秒、原文件最多 1 GiB。损坏或超限不能被截短后通过。

`importer.pcm_decode.decode_pcm_wave(source, new_directory, should_cancel=...)`
独占生成 `decoded.wav` 及 `decode.json`。输出为交错声道、小端 IEEE binary64 PCM，
保留采样率、帧数及声道原顺序；不重采样、增删帧、修音、归一化响度或限幅。
这里的数值归一化仅为精确单位换算：8 位无符号样本先减 128，其他宽度按有符号整数
读取，再除以 `2^(位数-1)`。所有支持的整数及该二进制比例都能由 binary64 精确表示，
包括 32 位正负极值，避免转成 float32 时损失最低位。

解码后第 `n` 帧对应源第 `n` 帧，时刻为精确的 `n / sample_rate` 秒；帧零偏移为零，
完整时长仍为 `frames × 1,000,000 / sample_rate` 有理数微秒。没有估计速度／节拍或
对既有 MIDI 时钟作任何处理。源 RIFF 的全部块清单、偏移、原数据哈希及完整文件
身份保存在嵌套预检快照中；分析文件仅含固定 fmt／fact／data，不把源元数据当样本。

输出固定 58 字节头：18 字节 WAVEFORMATEX、格式标记 3、64 位样本、cbSize=0，
fact 保存帧数，data 保存全部样本。它是项目内部分析中间件，不是宿主验收或播放
兼容性证明。[Microsoft WAVEFORMATEX](https://learn.microsoft.com/en-us/windows/win32/api/mmreg/ns-mmreg-waveformatex)
说明帧对齐和格式字段，其所述通用浮点示例为 32 位；64 位 WAV 在
[libsndfile 1.2.2 的独立实现](https://github.com/libsndfile/libsndfile/blob/1.2.2/src/wav.c)
中有 DOUBLE 路径。本项目使用原创编码／验证代码，没有复制或安装该库；未来消费者
仍须实际验证这种中间格式。Python [`struct`](https://docs.python.org/3.11/library/struct.html)
显式指定小端双精度，避免依赖本机字节序／结构填充。

## 来源与独立核验

`integer-pcm-to-float64-wave-v1` 报告保存：完整输入预检、Python 实现／版本、当前
解释器可执行文件和解码／验证／预检／契约模块文件身份、输出完整身份、样本区 SHA-256、
固定换算规则及精确时钟。标准库不需要新增包、原生解码器或启动子进程。
解释器路径先解析其正常安装链接，再记录实际文件；音频和输出路径继续拒绝链接／
reparse、歧义路径及后端目录。身份是本地完整性记录，不是签名、操作系统隔离，
也不是 Python 动态库／整个发行包的供应链证明。

`validator.pcm_decode.verify_pcm_decode(report_path)` 不调用正向转换算法：独立解析
全部输出头字段，读取全部浮点样本，检查有限值／范围／整数可逆性，再恢复原整数
字节并逐块与当前源 PCM 比较。同时检查帧数、EOF、样本哈希、当前预检和文件身份，
核验前后检查来源与运行时。修改输出再重算报告哈希，仍会因样本不同而失败。
报告拒绝重复 JSON 键、未知字段、超过 1 MiB、时间偏移／时长矛盾及产物路径不符。

已经完成的 decode 在核验和恢复时重新执行上述比较。源、产物、报告、代码或所记录
解释器改变即失效，必须创建新作业；不改写旧报告以“更新”依赖身份。
`musical_correctness=not_assessed`、`host_compatibility=unverified`、
`writer_eligibility=blocked` 始终保留。

## 作业、取消与资源

GUI／CLI 均由[共享作业服务](JOBS.zh-CN.md)调用。每次尝试使用新的
`decode-<开始事件编号>` 子目录；只有当前独立核验通过，才把 PCM 和报告两个身份
记为 decode 完成。历史 M1 输入预检报告仍按原规则核验，可追加解码；原记录不变。
后续 separate 或其他 worker 的结构事件不能冒充已经获得执行资格。

每块最多 4,096 帧，每次转换／逐样本核验各有 300 秒预算，在安全检查点响应超时或
取消。完整源／产物身份哈希和磁盘 I/O 可能先结束；不是可中断系统调用或硬实时限额。
输出大小固定为 `58 + frames × channels × 8`，支持范围上限 1,843,200,058 字节；
流式处理不把全曲载入内存，但磁盘仍须容纳放大的 PCM 和所有保留尝试。

失败／取消保留新建的完整或部分候选；部分 WAV 可能只有头或不足声明长度，不能仅
凭文件存在认为成功。未通过独立核验的尝试没有阶段完成事件；恢复使用新子目录，
不会覆盖旧候选。独占创建、flush/fsync 和事件链防止正常使用中的覆盖／半写复用，
不承诺恶意同用户并发替换或断电目录项的原子耐久性。

## 后续资格范围

[SoundFile 0.13.1](https://pypi.org/project/soundfile/0.13.1/)／
[libsndfile](https://libsndfile.github.io/libsndfile/) 仅作候选研究，未接入、安装或固定为
本项目运行依赖。它们的包装层／原生库许可与打包内容须分别审计；压缩输入还需要
完整损坏检查、MP3 priming／padding 与帧零语义、固定平台 wheel 和实际运行证据。
本切片不据此声称 MP3／FLAC 已可用。分离、转写、真值评分、宿主和发布验收继续按
[完整设计](superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)逐批推进。
