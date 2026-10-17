# 固定 Spleeter 4stems：Windows CPU 运行边界与采样时钟审计

审计日期：2026-10-16。本文是 M2 新切片的原始研究记录，补充而不改写
[前次模型调研](2026-10-16-audio-model-backends.zh-CN.md)。依据是固定源码、官方
PyPI 元数据、模型发布资产及模型作者论文。本研究子任务没有安装 TensorFlow、下载大模型、
执行分离或上传私有音频；因此不构成运行成功、质量资格、10 分钟资源资格或发布许可
审查已完成的证据。产品状态仍以[路线表](../DELIVERY_ROADMAP.zh-CN.md)及
[已批准设计](../superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)为准。

## 结论与必须保留的边界

1. Spleeter 2.4.2 的官方小 wheel 内全部 30 个 `spleeter/` 成员，与审查提交
   `c8854001ac8acad34a9bc2bd15f28475541828b1` 的对应 Git blob 一致。代码／固定配置
   可以沿用本次源码结论；此比对不证明 wheel 的构建过程、依赖二进制或权重内容。
   [PyPI][sp-pypi]、[固定树][sp-tree]
2. 模型作者正式论文明确把源码和预训练模型都描述为 MIT 分发；固定 README 只写代码，
   两个模型许可问询仍没有可见的维护者确认。可据作者声明研究这个官方模型，但应保留
   这种文件表述不一致、MIT 通知及精确资产来源，不能声称上游已补齐模型随附许可证。
   [论文第 3 页][paper-pdf]、[README][sp-readme]、[问询 898][issue898]、[问询 957][issue957]
3. **原生 Windows 的完整默认依赖不可按当前固定 wheel 集安装**：Spleeter 无条件要求
   `tensorflow-io-gcs-filesystem==0.32.0`，官方该版本只有 14 个发布文件，没有 Windows
   wheel，也没有 sdist。若接入本地 PCM／checkpoint 的裁剪依赖配方，必须明确记录它
   偏离上游声明，并独立审计和执行验证；不能静默换版本后声称原依赖闭包已满足。
   [Spleeter 元数据][sp-pypi]、[TFIO 0.32.0 元数据][tfio-pypi]
4. 默认 `4stems` 是 **44,100 Hz、双声道、约 11 kHz 带宽**。四条估计分轨不会保留
   整个原混音高频。保留 `vocals/drums/bass/other` 原始估计，另外明确命名未分配残差，
   才能记录源波形尚未由四轨解释的部分；残差不是第五种模型乐器，也不证明音乐分离质量。
   [固定配置][sp-config]、[掩码扩展及输出][sp-model]
5. 数组接口没有重采样和 600 秒截断，但内部时间分区一次进入同一个图，**不是内存有界
   的逐块流式 API**。长曲接入必须另有经验证的分块配方；超预算必须明确失败。
   [Separator][sp-separator]、[分区函数][sp-tensor]
6. TensorFlow 2.12.1 自己的确定性说明排除了对 TF1 `Session` 的保证。固定 CPU、线程、
   种子、checkpoint 和算法开关是实验条件，完整重复执行比较才是本机可重复性的证据，
   不应把启用确定性开关写成跨机器或跨版本的保证。[TF 2.12.1 配置源码][tf-config]

## 身份及许可证据

| 对象 | 本轮核对到的事实 | 证据边界 |
| --- | --- | --- |
| 源码 | `c8854001ac8acad34a9bc2bd15f28475541828b1`；项目元数据写 2.4.2；MIT，版权 Deezer SA | 固定源码审查点，不以版本字符串代替文件比对。[项目元数据][sp-project]、[LICENSE][sp-license] |
| PyPI wheel | `spleeter-2.4.2-py3-none-any.whl`，48,673 字节；SHA-256 `11b6aad050f89752e3752e08d8f69c69b699929157424e47c00e3e4db21073f9` | 本轮实际下载这个小文件并独立计算哈希，与官方元数据一致。[PyPI][sp-pypi] |
| wheel／源码对应 | 30 个 `spleeter/` 成员逐一计算 `SHA1("blob " + byte_length + NUL + bytes)`，全部匹配固定提交递归树的对应 blob；包括 `separator.py`、模型构造和全部 JSON 配置 | 仅包内源码／资源成员；`dist-info` 是打包产物，不能与整个仓库或构建过程画等号。未把代码相同推论为 TensorFlow 或模型已验证。[固定树][sp-tree] |
| 模型发布资产 | 官方 v1.4.0 的 `4stems.tar.gz`；asset ID `15780960`；146,308,147 字节；API `digest=null` | 大归档本轮未下载／解包。不能把 API 空 digest 写成哈希校验成功。[发布 API][sp-release] |
| 模型摘要 | 官方 `checksum.json` 的 `4stems` 为 `3adb4a50ad4eb18c7c4d65fcf4cf2367a07d48408a5eb7d03cd20067429dfaa8` | 核对了官方 checksum 文件；实际准备仍须计算归档及解出文件哈希、验证精确成员，并检查 checkpoint 引用。[checksum][sp-checksum] |
| CPU 运行候选 | CPython 3.11.16／Windows x64；`tensorflow==2.12.1` | Spleeter 要求 `>=3.8,<3.12`，可覆盖该 Python 主次版本；具体解释器构建、标准库、DLL 和实际加载身份另由准备清单固定。本轮没有验证该解释器执行。[项目元数据][sp-project] |

模型许可的直接作者依据是 Romain Hennequin、Anis Khlif、Felix Voituret、Manuel
Moussallam（Deezer Research）的 JOSS 论文，2020-06-24 发表，DOI
`10.21105/joss.02154`。固定仓库的 `paper.md` 与正式 PDF 第 3 页均明确将源码和
预训练模型列为 MIT 分发。这比仅凭仓库徽章或 PyPI 分类推测模型许可更直接。
作者同时说明训练数据因版权原因不公开；这不授予训练数据或输入音乐的权利。
论文自身的 CC-BY-4.0 许可与它陈述的模型 MIT 许可应分开记录。
[论文发表记录][paper-joss]、[正式论文][paper-pdf]、[固定论文源码][sp-paper]

固定 README 只说代码 MIT，而 #898／#957 有商业使用和格式转换的追问。截至本轮读取，
页面没有可见的维护者答复，也没有找到与作者论文相反的新模型授权。其他用户的计划、
转述及“+1”不是 Deezer 的授权；“没有相反条款”也不是新增授权。本轮建议的使用依据
就是作者论文及官方原资产，发布记录应保留这条链，不能扩展到第三方再训练权重。
[README][sp-readme]、[898][issue898]、[957][issue957]

## 真正的执行路径、导入和依赖

`Separator.separate()` 调用 `_separate_tensorflow()`，再创建单个
`Dataset.from_tensors({waveform, audio_id})`，经 Estimator 预测；它不接收采样率，
不会检查或转换采样率。`separate_to_file()` 则默认 `duration=600.0`，调用默认音频
适配器加载，随后保存。默认适配器为 FFmpeg：它探测外部 `ffmpeg/ffprobe`，自行重采样，
保存调用 `overwrite_output()`；因此不满足本项目独占输出和独立解码身份要求。
[Separator][sp-separator]、[适配器][sp-adapter]、[FFmpeg 实现][sp-ffmpeg]

数组通道转换也需要前置限制：`to_stereo()` 对 `(N,1)` 复制为两列，对多于两列的数组
直接取前两列。worker 应只接受经过合约验证的非空 `(N,1)`／`(N,2)` 有限 float32，
自行记录单声道复制规则；拒绝其他维度、额外声道及 NaN／Inf，不让上游默默丢声道。
输入振幅缩放由 PCM 派生配方决定，不能让模型前的隐式归一化改变来源链。
[转换函数][sp-convertor]

| 入口／阶段 | 审查到的外部导入 | 实施含义 |
| --- | --- | --- |
| 直接导入 `spleeter.model.EstimatorSpecBuilder` | `tensorflow`；其 `utils.tensor` 顶层还导入 `pandas` | 即使不用训练 CSV，pandas 仍是当前源码的导入要求；不能按“推理不用 CSV”直接删掉。[模型][sp-model]、[tensor][sp-tensor] |
| 构造固定 `unet.unet` | TensorFlow／Keras 的卷积、归一化、Dropout、激活及初始化器 | 固定推理学习阶段、固定图与 checkpoint 对应关系；不加载用户提供的模型模块。[U-net][sp-unet] |
| 导入 `Separator` | NumPy、TensorFlow；`AudioAdapter` 又导入 `utils.logging`，后者顶层 `from typer import echo` | 只使用数组接口也不意味着可以删除 typer。直接 builder 路线可绕开这层，但须作为受控改编记录。[Separator][sp-separator]、[logging][sp-logging] |
| `ModelProvider.default()` | 延迟导入 `github` provider，后者顶层导入 `httpx` | 初始化 provider 本身就需要 httpx；仅把下载函数换成空操作仍可能保留导入要求。[provider][sp-provider]、[GitHub provider][sp-download] |
| MWF | `_build_mwf_output_waveform()` 内才导入 `norbert`，通过 `tf.py_function` 调用 NumPy Wiener 运算 | 首个配方固定 `MWF=False`；启用会改变算法、导入和复现边界。[模型][sp-model] |
| 文件适配器 | 延迟导入 `ffmpeg-python` 并寻找外部二进制 | 直接数组／builder 推理不需要调用它；禁止把它作为失效时的隐式备用解码器。[适配器][sp-adapter] |

这些是 **Spleeter 层调用链**，不是完整 TensorFlow 闭包证明。TF 导入会涉及其自身 Python
与原生依赖、Keras、Estimator 等，裁剪配方仍需逐包验证及实际新进程导入／推理测试。

Spleeter wheel 声明：Python `>=3.8,<3.12`，TensorFlow `==2.12.1`，TFIO GCS
`==0.32.0`，NumPy `<2`，pandas `>=1.3,<2`，norbert `>=0.2.1,<0.3`，
ffmpeg-python `>=0.2,<0.3`，httpx/http2 `>=0.19,<0.20`，typer `>=0.3.2,<0.4`；
musdb／museval 属于 evaluation extra。本轮同时核对 wheel 的 METADATA 和 PyPI。
[wheel 元数据][sp-pypi]、[项目声明][sp-project]

Windows 的 `tensorflow` 包转向 Intel CPU 实现。`tensorflow-intel==2.12.1` 的元数据
进一步要求 NumPy `>=1.22,<=1.24.3`、typing-extensions `<4.6`、wrapt `<1.15`、
Keras／Estimator `>=2.12,<2.13` 等，并声明 `jax>=0.3.15` 及 TFIO GCS `>=0.23.1`。
因此不能拿现有核心 NumPy 2.x 或任意“最新版”闭包来满足它；仅满足版本求解也不等于
wheel 都有 Windows 构建。特别是 Spleeter 额外固定的 TFIO 0.32.0 是已确认阻塞。
[TF Intel 元数据][tfintel-pypi]、[TFIO 发布文件][tfio-pypi]

实施切片随后提出的 **graph-only 候选** 是单独固定 Spleeter wheel，使用
TF／Intel 2.12.1、NumPy 1.24.3、SciPy 1.15.3、Windows TFIO GCS 0.31.0 的闭包；
本研究只读见到了其下载的候选 wheel，没有执行该环境。0.31.0 能满足 TF 自身较宽的
`>=0.23.1` 声明，却不满足 Spleeter 的 0.32.0。TFIO 官方兼容表还把 0.31.0 配对到
TF 2.11.x、0.32.0 配对到 TF 2.12.x，所以也不能从求解成功推断原生 TFIO 插件兼容。
这个配方应关闭模块化文件系统、仅用本地 checkpoint；CLI、FFmpeg、MWF 和云文件系统
均不在候选支持范围。是否实际可导入、恢复模型和推理，由实施阶段提供独立证据。
[TF 元数据][tfintel-pypi]、[TFIO 官方兼容表][tfio-pypi]

本轮只读扫描候选 wheel 内 Python 文本：TF Intel 2.12.1 内没有发现 `pkg_resources`
引用；TensorBoard 2.12.3 的 `default.py`／`data/server_ingester.py` 有顶层引用，
wrapt 1.14.2 的插件发现函数内部也使用它。不能据此断言所有间接导入都与选定
setuptools 84.0.0 兼容；应由图推理的真实导入测试决定，同时明确 TensorBoard
服务／插件发现不在工作进程入口内。[TensorBoard 默认模块][tb-default]、
[TensorBoard server ingester][tb-ingester]、[wrapt 导入工具][wrapt-importer]

TF 实际 wheel 的 `tensorflow/__init__.py` 还体现了环境加载边界：
`TF_USE_MODULAR_FILESYSTEM=1/true` 才显式导入 TFIO GCS；它收集 `sys.path` 中的
site-packages、用户站点及 `site.getsitepackages()`，在判断为 pip 包运行时扫描
`tensorflow-plugins`，并能从 `TF_PLUGGABLE_DEVICE_LIBRARY_PATH` 加载原生插件。
固定 worker 因此必须控制这些环境和站点路径，不能只依靠 `-I/-S` 字样宣称所有原生
加载均被隔离。必须检查实际导入和 DLL 来源，保留固定可信依赖目录。
[TF 2.12.1 顶层模块模板][tf-api-template]

### 缺少随包完整 LICENSE 的四个候选依赖

实施阶段发现以下 wheel 缺少完整许可文本后，本研究追溯官方标签。下列是应补充保留的
上游许可来源；这不把一般源码标签对应提升为可重现二进制构建证明，也不取代其他随包
第三方通知。TensorFlow 的 LICENSE 含额外来源条款，必须完整保留。

| 候选包 | 核对的固定源码／许可来源 |
| --- | --- |
| flatbuffers 25.12.19 | `v25.12.19` 注释标签最终指向 `7e163021e59cca4f8e1e35a7c828b5c6b7915953`；`python/setup.py` 明确版本 25.12.19 和 Apache 2.0。[标签 API][fb-tag]、[固定 setup][fb-setup]、[完整 LICENSE][fb-license] |
| tensorflow 2.12.1 Windows 元包 | `v2.12.1` → `8e2b6655c0c488290179ab90a0daed0f6d3006f7`；Apache 2.0 及文件中附带的来源通知。元包与实际 Intel 负载分别记录。[标签 API][tf-tag]、[完整 LICENSE][tf-license] |
| tensorflow-estimator 2.12.0 | `v2.12.0` → `1bcfb76591c4ae8f520e4ec0178582de3f250f67`；Apache 2.0。[标签 API][est-tag]、[完整 LICENSE][est-license] |
| tensorboard-data-server 0.7.2 | **`data-server-v0.7.2`** → `81150b898a306b89cde90e949358c2eefe018eaa`；Apache 2.0。其 universal wheel 唯一 Python 模块与该提交的源文件 SHA-256 实际一致：`78204e97bfc44e702a8903915f7f63476befb49ff0742f030718286ee6f8fa33`。[标签 API][tds-tag]、[版本源码][tds-source]、[完整 LICENSE][tds-license] |

TensorBoard 自身 `2.15.0` 标签中的 data-server 模块已经标为 0.8.0a0，不能把它当作
0.7.2 的版本对应证据。当前 Windows 候选用 universal data-server wheel，模块在没有
附带 server 二进制时返回 `None`；它不证明 Windows 获得了 Rust 数据服务。
[正确的 0.7.2 源码][tds-source]、[2.15.0 标签中的模块][tds-wrong-version]

官方 TensorFlow 文档指出 2.10 是原生 Windows NVIDIA GPU 支持的最后版本；2.12.1
在本配方按 CPU 处理。Windows CPU 构建由 Intel 发布，文档还要求相应 MSVC 运行库并
提示 AVX 要求。CPython 3.11 wheel 标签和用户存在 RTX 显卡都不能证明 GPU 可用；
本切片不隐式安装 WSL、CUDA、DirectML 或修改全局环境。[官方 Windows 安装说明][tf-install]

## STFT／iSTFT 的坐标推导

以下是固定代码及 TensorFlow 2.12.1 信号实现的静态推导，不是已经测量到的模型精度。
令输入为 `x[N,2]`，`Fs=44100`、窗长 `L=4096`、步长 `H=1024`、分区长度
`T=512`、模型频点数 `F=1024`。[固定配置][sp-config]、[模型实现][sp-model]、[TF 信号源码][tf-spectral]

| 步骤 | 尺寸及确切行为 | 对时间／内容的意义 |
| --- | --- | --- |
| 左补零 | `concat(zeros([4096,2]), x)`，长 `N+4096` | STFT 第 `k` 帧窗起点对应原输入 `k*1024-4096`，不是原输入 `k*1024` |
| STFT | 先转 `[2,N+4096]`；periodic Hann；`pad_end=True`；未传 FFT 长度，TF 取包住 4096 的最小 2 次幂，即 4096 | 单边谱 2049 个频点；`Q=ceil((N+4096)/1024)` 帧；再转 `[Q,2049,2]` |
| 时间分区 | 沿 Q 维末尾补零到 512 的倍数，再 reshape | `B=ceil(Q/512)`，输入幅度谱 `[B,512,1024,2]`；Q 正好整除 512 时不会额外加整区 |
| U-net | 每个声部一个固定网络，估计同形状幅度谱 | 分区之间没有模型时间上下文重叠／跨区融合；音频窗本身仍有 STFT overlap |
| 比率掩码 | 平方估计幅度，分母加 `1e-10`，每个分子加 `1e-10/4` | 被学习频段内四个掩码在数学上和为 1；浮点结果需容差验证；这只说明混合谱分配，不证明声部正确 |
| 高频扩展 | 默认 `mask_extension=zeros`，补到 2049 频点；把 B/T 展平并裁回 Q | 频点 1024–2048 的每个声部掩码为零；首个置零频点 11,025 Hz，最高预测频点为 11,014.2333984375 Hz |
| iSTFT | 转 `[2,Q,2049]`；相同 periodic Hann；inverse STFT overlap-add 后乘 `2/3` | Hann 的平方重叠补偿与 `H=L/4` 绑定；不能随意改变 H/L 或把本实现换为另一“默认”窗 |
| 输出裁切 | 转 `[M,2]` 后取 `[4096:4096+N,:]` | 移除人工左补零，声明原点 0，输出 N 帧；不是将检测到的音符强行对齐到 hop 网格 |

TF 的 STFT 使用真实窗长对信号分帧，`pad_end=True` 补足越界窗；iSTFT 对每帧逆 FFT
后再次乘窗，再 overlap-add。因此精确原点由以上前补／后裁配对恢复；应以首尾脉冲及
独立分析／合成测试验证，不能再习惯性减 `L/2` 或增加一个 hop。
[TF 2.12.1 信号源码][tf-spectral]、[Spleeter 合成裁切][sp-model]

固定 `4stems-16kHz` 资源也仍是 44,100 Hz 采样率，只把 `F` 改为 1536。名称中的
16 kHz 指更宽的处理频带，不是 16 kHz 输入采样率。切换该配置会改变候选、计算量与
结果，必须有新配方／测试，不能静默用它修补当前 4stems 的高频缺失。
[16 kHz 配置][sp-config16]

四轨和与原输入之间的差别应显式记录。建议保留四条未经幅度归一化的原始估计，并在
同一 44,100 Hz 网格计算 `unassigned_residual = input - sum(stems)`；另保留求和次序、
计算精度与浮点容差。残差包含模型默认未分配的频带及数值误差，必要时也包含其他重建
差别，不能只凭名称断言全是高频。若导出原采样率，另对最终输出网格检查重建误差。
这是本项目的建议派生步骤，不是上游提供的第五个 stem。[掩码及合成事实][sp-model]

## 重采样、长音频与内存

数组入口没有采样率参数，48 kHz 数组直接交给模型会被当作 44.1 kHz 解释。最窄首版
可以明确只支持已验证的 44.1 kHz PCM；扩展时必须在 worker 外或固定 worker 配方内
显式进行有审计的重采样，保存源 `Fs/N`、目标 `44100/Nm`、有理比例、滤波器、边界
补零／裁切规则和输入输出哈希。对于目标样本 `j`，源连续坐标是 `j*Fs/44100`；
不能累计浮点秒数再四舍五入每块边界。[入口无重采样的源码依据][sp-separator]

建议重采样合约明确端点采用 `[0,N/Fs)`，并规定例如 `Nm=ceil(N*44100/Fs)` 的整数
规则；该规则只是实施选择，必须在实际适配器中固定，而非推断上游已有保证。回到原
网格时严格恢复 N 帧，任何为滤波边界所作的裁切／补零都应有记录，不能掩盖漏掉尾部。
重采样可以改变带宽与样本值，“时间坐标可追溯”不等于“波形无损”。

`T=512` 对应 hop 跨度 524,288 样本，即约 11.888617 秒；这不是可以直接把 WAV 切成
11.888617 秒再拼接的证明。该组 512 个 STFT 窗覆盖 `(512-1)*1024+4096=527360`
个样本，涉及左补零、窗重叠和全局分区边界。`Separator` 将整段输入放进一个 Dataset
元素，模型将所有分区作为 batch 维执行；配置的 `batch_size=4` 是训练配置，不能作为
推理峰值内存限制。[Separator][sp-separator]、[分区][sp-tensor]、[U-net][sp-unet]

纯尺寸估算：10 分钟双声道输入有 26,460,000 帧，Q=25,844、B=51。单份 complex64
完整 STFT 约 847,269,696 字节，四条 float32 输出约 846,720,000 字节；每个 U-net
第一个卷积结果 `[51,256,512,16]` 又约 427,819,008 字节。还没有计入其他激活、
临时张量、模型和运行时。这些是按源码尺寸计算的字节数，不是峰值 RAM 测量，也不能
直接相加宣称实际同时存活的内存。[模型尺寸][sp-model]、[卷积尺寸][sp-unet]

建议先建立短输入完整图作为基准，再验证有界方案。若按固定 STFT 分区逐块执行，必须
保留全局 STFT 的窗原点、所需上下文、分区补零和统一 overlap-add，证明与完整图在
指定精度容差内相同；如果选择独立 waveform 窗加交叠淡入淡出，则它是新的模型调用
配方，应明确记录重叠、裁切及融合，并独立做边界质量评估，不能宣称等同原始整曲图。
长曲超预算、取消或少一块时都失败，不能发布已处理前缀为“完成”。

## 离线模型加载与可重复性

`ModelProvider.get()` 将相对目录拼到 `MODEL_PATH`（默认 `pretrained_models`）。
它只有在 `.probe` 不存在 **且目录也不存在** 时才建立目录并下载；目录存在但缺权重时
直接返回。`.probe` 内容不被读取，现有 checkpoint 不被重新哈希。因此预建目录或
`.probe` 都不是完整性门槛，也不是通用禁网开关。
[ModelProvider][sp-provider]

默认 GitHub provider 从 `GITHUB_HOST/GITHUB_REPOSITORY/GITHUB_RELEASE` 环境读取
覆盖值，默认 release 是 v1.4.0；下载后取得远端 checksum，再用 `tar.extractall()`。
它不会执行本项目的固定成员、路径／链接或当前文件身份策略。不要把用户环境变量、
归档成员或 `.probe` 当作可信配置。[GitHub provider][sp-download]

推荐候选 worker 路线如下，均属于待实现／待实测的工程建议：

1. 准备步骤与推理分开。只从显式给定且哈希已固定的本地 wheel／模型归档生成全新
   私有目录，验证精确归档成员、常规文件、路径归属及 checkpoint 指向。已有准备结果
   在每次运行前重新核对全部文件；不执行包安装脚本或下载器。
2. 受信任独立 Python 启动固定 worker（沿用项目隔离与诊断约束），只接受结构化输入
   身份和独占输出目录。禁止用户配置路径、Python 模块名、网络 URL、动态 audio adapter
   和任意 TensorFlow GraphDef／MetaGraph。只接受本配方固定的 `4stems` 参数。
3. 直接构造 `tf.Graph`、固定 float32 waveform placeholder 和
   `EstimatorSpecBuilder(...).outputs`，通过固定 `Saver` 恢复已核验的本地 checkpoint
   前缀。用上游 Python 固定图重建，不调用 `import_meta_graph`、`latest_checkpoint`
   或 provider；核对变量集合及未初始化状态，防止静默随机初始化。此路线偏离公共
   `Separator` 包装层，需要与可控的上游基准比较。[图构造代码][sp-model]
4. 首配方固定 `MWF=False`、Keras 推理学习阶段、种子、CPU 可见设备及 Session
   `device_count={GPU:0}`；线程与数据管道线程纳入配方。候选 `intra_op=8/inter_op=1`
   需实测整个作业的实际线程和资源预算，两个设置并不自动约束所有依赖的线程池。
5. 在导入 TF 前固定 `TF_ENABLE_ONEDNN_OPTS=0`，并记录实际构建是否采用对应分支；
   启用 `enable_op_determinism()`、设置种子。源码注明 oneDNN 不同运算次序可产生浮点
   差别，固定开关旨在缩小实验变量，不能取代重复性验证。[TF CPU 开关][tf-port]
6. 不调用网络路径，不保留 provider 的自动下载后备。Python 层网络拒绝／导入限制只
   是应用控制，不能描述为原生 TensorFlow 的 OS 网络沙箱。进程取消只终止本作业
   拥有的子进程，保存失败证据，不发布完整结果标记。
7. 输出先验证完整四轨、尺寸、有限值、当前源身份、重复执行及残差，独占保存新文件；
   独立重读采样率／声道／长度／内容。报告同时保留原始模型估计与派生残差的身份。

TF 2.12.1 的确定性文档要求同硬件、同软件环境、种子和确定性输入管道，并明确说明
TF1 Session 不能获得该保证；它也不保证跨版本、内存使用或耗时确定。
Spleeter 当前 Estimator／建议固定图都是旧图执行范式，因此只能先把“本固定环境的
新进程重放输出相等”作为验证目标。若相等失败，应保留每轨最大误差及哈希，调查原因，
不能静默放宽字节验证后仍称完全可复现。[TF 2.12.1 确定性说明][tf-config]

## 实施时需要的独立测试

这些是测试建议，不是本轮已通过项目。

| 类别 | 必须覆盖的证据 |
| --- | --- |
| 源时钟／尺寸 | N=1、1023/1024/1025、4095/4096/4097；Q 接近 512 倍数时的两侧；最后一帧有脉冲；输出均为 N×2，原点 0，无尾截断 |
| 独立 STFT 基准 | 用原始合成信号独立计算 periodic Hann、补零、单边 FFT、2/3 overlap-add 与裁切；测试恒等掩码及频带截断，区分信号处理错误与神经分离错误 |
| 边界／通道 | 第一／最后样本、hop 与分区边界脉冲；左右声道独立信号；单声道复制；拒绝三声道、非有限值、空数组和错误维度 |
| 高频／残差 | 确认模型原始四轨之和不冒充全频源；独立计算并重读 residual；记录频带限制，测试四轨＋残差的浮点重建误差；不靠残差给分离 SI-SDR 作弊 |
| 重采样 | 44.1k 直通；如支持 48k→44.1k→48k，用有理整数边界与首尾脉冲核对源坐标及 N；不同尾长和各块间不积累漂移 |
| 分块 | 同一短／中等输入的完整图与候选有界算法比较；块交界附近和最后不完整块；遗漏／重复／改序／改输入块必被验证拒绝 |
| 身份／离线 | 缺权重、改权重、额外文件、改 checkpoint 引用、旧配方、路径链接、来源改变；不能触发网络或默认 FFmpeg；失败不给成功标志 |
| 可重复／取消 | 全新进程重放逐轨比较；固定 CPU 配方重复 10 次；推理中取消、超时、资源超预算、半成品残留均有明确状态；峰值 RAM 和耗时实测 |
| 质量 | 合法固定真值／保留集上的 SI-SDR 改善、对齐及后续转写；无真值音乐报告真值指标 unavailable，不用 stem 数量或低重建误差代替声部分离质量 |

测试与报告仍服从已批准产品设计的 24 片段／6 首实曲门槛、固定资源及既有文件保护。
分离候选即使可执行，也不能把作业自动升级为完整 `succeeded` 或改变旧 FLP 阻断。

## 本轮保留材料

本研究子任务仅新增本文及忽略目录 `.tools/m2-separation-research-v1/`。目录含固定公开源码
文本、官方小 wheel、PyPI／发布／checksum 元数据及 30 成员对照 JSON；不含私有音频、
模型大归档或新运行时。另只读扫描实施阶段下载的候选 wheel，没有修改其目录。
最初受限网络请求因 DNS 失败未下载文件，随后获工具审查允许的
固定公开资源读取成功；本轮没有调用默认模型下载器。

静态检查确认了文件身份、调用链及以上公式；没有运行项目全套测试，也没有运行模型。
运行时准备、TF 本身依赖加载审计及真实分离验证由实施切片单独提供证据。

[sp-pypi]: https://pypi.org/pypi/spleeter/2.4.2/json
[sp-tree]: https://api.github.com/repos/deezer/spleeter/git/trees/c8854001ac8acad34a9bc2bd15f28475541828b1?recursive=1
[sp-project]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/pyproject.toml
[sp-license]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/LICENSE
[sp-readme]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/README.md
[sp-paper]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/paper.md
[paper-joss]: https://joss.theoj.org/papers/10.21105/joss.02154
[paper-pdf]: https://joss.theoj.org/papers/10.21105/joss.02154.pdf
[issue898]: https://github.com/deezer/spleeter/issues/898
[issue957]: https://github.com/deezer/spleeter/issues/957
[sp-release]: https://api.github.com/repos/deezer/spleeter/releases/tags/v1.4.0
[sp-checksum]: https://github.com/deezer/spleeter/releases/download/v1.4.0/checksum.json
[sp-config]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/resources/4stems.json
[sp-config16]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/resources/4stems-16kHz.json
[sp-separator]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/separator.py
[sp-model]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/__init__.py
[sp-unet]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/functions/unet.py
[sp-tensor]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/utils/tensor.py
[sp-logging]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/utils/logging.py
[sp-convertor]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/audio/convertor.py
[sp-adapter]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/audio/adapter.py
[sp-ffmpeg]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/audio/ffmpeg.py
[sp-provider]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/provider/__init__.py
[sp-download]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/provider/github.py
[tfintel-pypi]: https://pypi.org/pypi/tensorflow-intel/2.12.1/json
[tfio-pypi]: https://pypi.org/pypi/tensorflow-io-gcs-filesystem/0.32.0/json
[tf-install]: https://www.tensorflow.org/install/pip#windows-native
[tf-config]: https://github.com/tensorflow/tensorflow/blob/v2.12.1/tensorflow/python/framework/config.py
[tf-spectral]: https://github.com/tensorflow/tensorflow/blob/v2.12.1/tensorflow/python/ops/signal/spectral_ops.py
[tf-port]: https://github.com/tensorflow/tensorflow/blob/v2.12.1/tensorflow/core/util/port.cc
[tf-api-template]: https://github.com/tensorflow/tensorflow/blob/8e2b6655c0c488290179ab90a0daed0f6d3006f7/tensorflow/api_template.__init__.py
[tb-default]: https://github.com/tensorflow/tensorboard/blob/2.12.3/tensorboard/default.py
[tb-ingester]: https://github.com/tensorflow/tensorboard/blob/2.12.3/tensorboard/data/server_ingester.py
[wrapt-importer]: https://github.com/GrahamDumpleton/wrapt/blob/1.14.2/src/wrapt/importer.py
[fb-tag]: https://api.github.com/repos/google/flatbuffers/git/ref/tags/v25.12.19
[fb-setup]: https://github.com/google/flatbuffers/blob/7e163021e59cca4f8e1e35a7c828b5c6b7915953/python/setup.py
[fb-license]: https://github.com/google/flatbuffers/blob/7e163021e59cca4f8e1e35a7c828b5c6b7915953/LICENSE
[tf-tag]: https://api.github.com/repos/tensorflow/tensorflow/git/ref/tags/v2.12.1
[tf-license]: https://github.com/tensorflow/tensorflow/blob/8e2b6655c0c488290179ab90a0daed0f6d3006f7/LICENSE
[est-tag]: https://api.github.com/repos/tensorflow/estimator/git/ref/tags/v2.12.0
[est-license]: https://github.com/tensorflow/estimator/blob/1bcfb76591c4ae8f520e4ec0178582de3f250f67/LICENSE
[tds-tag]: https://api.github.com/repos/tensorflow/tensorboard/git/ref/tags/data-server-v0.7.2
[tds-source]: https://github.com/tensorflow/tensorboard/blob/81150b898a306b89cde90e949358c2eefe018eaa/tensorboard/data/server/pip_package/tensorboard_data_server/__init__.py
[tds-license]: https://github.com/tensorflow/tensorboard/blob/81150b898a306b89cde90e949358c2eefe018eaa/LICENSE
[tds-wrong-version]: https://github.com/tensorflow/tensorboard/blob/553dedcaf713206457e437c07a09da971048f945/tensorboard/data/server/pip_package/tensorboard_data_server/__init__.py
