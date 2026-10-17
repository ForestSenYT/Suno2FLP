# 来源绑定的鼓点候选

这是单独的开发切片：从当前分离候选的 `drums.model` 运行固定编码器，保留完整原始
输出、原音频坐标、候选鼓点及填充区排除记录。它不生成 MIDI／FLP，不加载音源，
不改变既有编排、严格 MIDI 或共享作业的资格。`model_qualification=not_assessed`、
`ground_truth_metrics=unavailable`、`writer_eligibility=blocked`、`execution_allowed=false`。

## 固定范围与许可

上游为 [inverse-drum-machine 固定提交](https://github.com/bernardo-torres/inverse-drum-machine/tree/456656868538205ef756912c7cf5b0fd936de8af)，
仅采用 `Encoder`、ConvNeXt、mel/STFT、池化和转写头；不调用完整 IDM、decoder、
Hydra、训练入口或上游便利加载器。源码及仓库内检查点的固定归档 SHA256 为
`7ed64f8cc064055e80a694bba1013c15a23dc6d962b8a91b08fadb1e47b95bef`，检查点 SHA256 为
`5856a9bee7c6d503842795756d238dc8470f6f3e010e9e4f33ede0362850cb4c`。

`integrations/drum_pins.json` 保留全部来源、字节数、哈希、许可、完整归档清单、
11个选定源码／配置／权重成员、330个张量的形状和 dtype。完整194个 `encoder.*`
张量严格加载；136个非编码器张量保留为未使用元数据。使用 CPU 上的
`torch.load(weights_only=True)`，检查不安全全局项、全量键／形状／dtype／有限数值，
不执行不受限 pickle。配置只作来源证据，构造器固定，不解析任意 `_target_`。

原仓库 Apache-2.0 正文随隔离负载保留；ConvNeXt 的 Meta MIT 补充正文固定为
[官方 Git blob](https://api.github.com/repos/facebookresearch/ConvNeXt/git/blobs/b93be90515ccd0b9daedaa589e42bf5929693f1f)，
正文1088字节、SHA256 `da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93`。
该 API 返回正文的 base64 包装，准备目录需要解码后的 `ConvNeXt-MIT.txt`，不能把
API JSON 当正文。不会自动下载。未采用 decoder 的第三方来源不能据此宣告许可已清。
训练音频与下游音乐的权利不由代码许可证明，发布资格仍需独立审计。

仅把转写头的激活导入改为受审计的窄辅助文件，保留原 float32 `exp_sigmoid` 运算，
拒绝配置之外的激活；原始／修改后哈希都有记录，不引入整份 `utils` 的训练依赖。
应用内包含这个 Apache 派生辅助文件，因而同时携带完整许可与修改说明；第一方源码
仍按原根目录 MIT 许可。发行包的 SPDX 表达式为 `MIT AND Apache-2.0`，并显式列出
三个 `license-files`，遵循 [PyPA 混合组件示例](https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/)
与[发行包元数据范围](https://packaging.python.org/en/latest/specifications/core-metadata/)。
外部源码归档、权重、原生库、私有音频与后端不进入 Git 或应用发行包。

## 独立运行时与命令

固定普通 CPython3.11.16、Windows x64、CPU8线程／交互线程1、确定性算法、
`mkldnn=false`、无 CUDA、最高 matmul 精度。实际 getter 结果随每次运行保存。
13个已审计官方 wheel 为 Torch/Torchaudio2.11.0+cpu、NumPy1.26.4、einops0.8.0，
以及 filelock/fsspec/Jinja2/MarkupSafe/mpmath/networkx/setuptools/sympy/typing-extensions；
完整固定版本及实际各自许可／原生 notice 见 pins。无核心 ML 依赖或自动安装。

这个组合不同于上游训练依赖 Torch/Torchaudio^2.1.1、einops^0.7.0；只证明选定图的
当前运行、严格加载、完整输出与重复性，不宣称复现论文或全套上游训练／分离表现。
worker 使用 `-I -S -B`，只导入隔离负载，禁用网络和下载兜底，缓存只放新尝试目录。
有界进程保留完整 stdout/stderr／失败与部分输出，观测峰值内存，超过16GiB明确失败。

```powershell
suno2flp prepare-drum-backend --artifacts fixed-local-artifacts --output new-backend
suno2flp verify-drum-backend new-backend --output new-probes
suno2flp transcribe-drums separation/separation.json --separation-replay separation-replay/replay.json --backend new-backend --output new-drums
suno2flp verify-drum-transcription new-drums/drum-transcription.json --output new-drum-replay
suno2flp export-drum-annotation new-drums/drum-transcription.json --output new-drum-annotation.json
suno2flp score-drums new-drum-annotation.json --output new-score.json
```

准备目录须已有13个固定 wheel、pins 中命名的完整上游归档与 MIT 正文，共15个输入。
`prepare` 只准备／校验文件，明确 `prepared_not_probed`；`verify-drum-backend` 才进行
真实合成信号调用。已实际完成两类原创立体声信号各两次的正式验证，全部原始数组
逐字节重复一致，并用独立的逐对 float64 求和／乘半／转 float32 公式检查完整下混。
这不是歌曲质量成绩。外部测试须显式设置 `SUNO2FLP_DRUM_BACKEND`，默认离线跳过。

所有目标目录／完成 JSON 必须全新，保护源文件、模型负载及已有输出，拒绝路径重叠、
链接、缺失或不一致的前提。修改源码、参数、后端、输入或依赖会使旧记录失效，不能
修改旧 manifest 冒充新证据；应新建后端／候选。取消及发布前变更不会发布完成名。

## 时钟、原始数据与排除审计

输入来自当前分离的原始44100Hz双声道 float32 模型波形，直接下混；不再次重采样
源采样率的参考 WAV。保留原音频、解码与分离原始／重放的完整快照、哈希和时钟。
两份完整快照在 JSON 中使用显式 `zlib-base64-json-v1` 无损封装，每份保留解压后
字节数与 SHA256，解压上限32MiB，拒绝尾随／截断／超限流；不删字段或缩短数组。
文件本身的原始哈希独立保留，封装哈希不是执行／数值权威。完成报告仍受16MiB限制。
每次从不可信磁盘读取时完整检查两份分离的数值、解码／来源关系和声明的重放匹配，
不能仅凭收据 `complete_match`。本次不重新运行 Spleeter，报告明确区分这层当前数值
证据与本次新执行的鼓编码器。已建立的同次调用数值证据通过不可变内存见证复用，
消费与发布前重查全部字节和负载成员；不把序列化收据当作数值／原生执行权威。

选定图的 mel 为1024 FFT、128mel、hop256，先补齐右侧 hop，STFT 居中。其卷积在
时间方向额外扩展12行，输出行数为 `ceil(model_frames/256)+13`；完整原始输出以
类别优先的 little-endian float32 `[9, rows]` 保存。模型输入长度支持513–26460000帧，
更短或超过预算明确拒绝，不截断。另保留完整下混 `mono.f32` 和所有请求、结果、日志。

三个中间时间卷积各有 kernel3/pad3/stride1，几何中心为 `(row-6)*256` 个44100Hz
采样；不是把 row0 假作源时间0。转换为原音频微秒的精确分数是
`(row-6)*256*1000000/44100`。实际短脉冲／静音及重复实验已核对形状和负载一致性；
这仍不是音乐 onset 的延迟校准。前部负坐标和等于／超过原音频精确时长的坐标保留，
不舍入到 tick、不夹到边界，也不移动已有 MIDI 源事件。时长比较使用原帧数／采样率。

候选峰提取是固定实验配置：logit严格大于0，三帧局部最大，平台并列取最左；
没有校准置信度。九类标签沿用 pins 的明确顺序，既不等于 GM，也不证明独立乐器。
保留每个峰的原行、模型采样坐标、logit／velocity完整32位浮点位型。速度头数值
不是 MIDI velocity。填充峰以独立理由排除并保留原峰，绝不挪入源区。最多20000个
源事件和20117个总峰；超限失败，不截掉峰、类别或原始数据。

## 重放、评分与保留限制

当前读取完整检查原始依赖、原始／重放分离快照、后端、recipe、原始数组、独立
下混、峰／坐标和全部排除记录。候选必须在其原 `root/drum-transcription.json`，
移动、未完成、截断或变更文件会被拒绝。独立重放重新运行完整编码器到新目录，
比较全部数组及全部派生结果；同时伪造数值和哈希仍不能代替这次重新计算。
时间／内存是各自观测值，分别保留，不要求跨次相等。

导出的标注总是 `role=candidate/origin=inferred_candidate`，指向原音频／解码和当前
候选生产者，时间保持原采样时钟；不是参考真值。没有参考时评分明确不可用，见
[鼓点评分](DRUM_SCORING.zh-CN.md)。一次候选生成或重放完成的退出码0，均不表示
转换作业、模型音乐质量或 FLP 可交付。参考曲库、延迟与置信度校准、真实曲目试听、
新编排中的鼓映射／可发声音源、共享作业接入、宿主和安装验收仍待完成。
