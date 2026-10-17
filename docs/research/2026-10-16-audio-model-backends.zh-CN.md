# M2：本地分离与 pitched 音符转写后端审计

审计日期：2026-10-16。**一手来源审计完成；未安装、执行或取得模型资格。**
建议先实现隔离的 **Basic Pitch 0.4.0／ONNX CPU 转写**，再接入
**Spleeter 4stems／TensorFlow CPU 分离**。两者均找到超出“代码仓库许可证”
的一手模型许可依据；推荐的是可复验的下一实验路径，尚无完整锁定、实测合格的
运行时组合。Demucs 暂不进入产品推理路径：其权重许可不能从 MIT 代码许可推导。

本轮只读取公开源码、许可、作者文章及官方元数据，保存少量公开参考文本到新的
忽略目录 `.tools/m2-model-research-v1/`。Basic Pitch 的一个小型 ONNX blob 经
GitHub contents API 在内存中解码并计算哈希，未保存或加载；未下载其他权重、
wheel 或原生库，未安装任何上游组件，未运行模型、DAW、插件或 UI。
没有上传私有素材，没有修改源音频、MIDI、模板、基准及旧实验。

已阅读 [架构](../ARCHITECTURE.md)、[交付路线](../DELIVERY_ROADMAP.zh-CN.md)、
[获确认的产品设计](../superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
及现有依赖／集成证据约定。本报告不改变 active 目标、已实现能力或发布门槛。

## 选择与许可证据

| 候选 | 代码许可 | 权重的独立一手依据 | 决定 |
| --- | --- | --- | --- |
| Spotify Basic Pitch 0.4.0 | 固定源码的 [Apache-2.0 LICENSE][bp-license] 和 [NOTICE][bp-notice] | Spotify 作者文章明确说开源的是模型，并允许将工具用于任何目的、集成其他音乐工具；权重随官方仓库／包提供。[作者文章][bp-blog]、[模型目录][bp-tree]、[打包清单][bp-manifest] | 首个真实 pitched 转写实验；保留 Apache／NOTICE 和实际依赖通知 |
| Deezer Spleeter 4stems | 固定源码 [MIT LICENSE][sp-license] | Deezer Research 作者的论文明确将源码与预训练模型一起列为 MIT 分发；论文另说明训练数据不公开，不能把模型许可扩大到训练数据。[论文源码][sp-paper]、[正式发表记录][sp-joss] | 首个分离候选，先用 CPU；实际包／原生依赖及资源资格仍待完成 |
| Facebook Demucs／维护者 fork HTDemucs | [维护者源码 MIT][de-license] | 维护者在官方 issue 明确排除权重的 MIT 许可并限定科学用途；2026-08-31 又在自己 HF 权重仓库删除 `license: mit`，当前模型卡无替代授权。[维护者答复][de-weight-license]、[删除提交][de-remove-license]、[当前卡／资产元数据][de-hf-api] | 不作为已获产品用途授权的模型；不以用户本地下载或格式转换绕过权重条款 |

Basic Pitch 的判断使用作者对**模型开源与用途**的明确说明，以及同一官方发布树
内的模型、LICENSE、NOTICE 和打包清单，未仅凭 PyPI 分类或一个仓库徽章推断权重许可。
Spleeter 的依据是模型作者论文中的明确权重声明；其 README 只提代码 MIT，
官方 [#898][sp-898]、[#957][sp-957] 的再次确认请求截至本轮读取仍无维护者答复。
这是应保留的文件一致性问题，不能把第三方评论当作新增授权；正式分发时应一并
保留作者声明、MIT 通知和实际权重身份，不宣称获得了逐资产补充授权。

## 固定身份与可核对资产

### 首个转写候选

Basic Pitch `v0.4.0` 标签指向完整提交
`9991303bba609a3b93089d13ec80d1d495083596`；版本号和依赖声明一致。
[官方标签 API][bp-tag]、[固定元数据][bp-project]。

| 对象 | 固定值／来源 |
| --- | --- |
| 官方 ONNX 权重 | [`basic_pitch/saved_models/icassp_2022/nmp.onnx`][bp-model-download]，230444 字节 |
| 权重 SHA-256 | `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`；本轮对官方 contents API 返回内容在内存中计算，并核对长度及 Git blob 身份，非上游签名证明。[内容 API][bp-model-api] |
| Git blob SHA-1 | `c30e5f9438e798604b7177aa26be1fe64482f767`；这是 Git 对象身份，不是原始文件 SHA-256。[树 API][bp-tree] |
| 官方 Python wheel | `basic_pitch-0.4.0-py2.py3-none-any.whl`，758279 字节；SHA-256 `738adb503aae7fdfc7d1e1511aa0ce35052315f260a19531ef4c356708425db0`。[PyPI 元数据与下载 URL][bp-pypi] |
| 独立 CPU ONNX Runtime 候选 | `onnxruntime==1.23.2`；源码标签指向 `a83fc4d58cb48eb68890dd689f94f28288cf2278`，代码 MIT。[标签 API][ort-tag]、[LICENSE][ort-license] |
| 已确认存在的 ORT Windows wheel | `onnxruntime-1.23.2-cp311-cp311-win_amd64.whl`，13468349 字节；SHA-256 `902c756d8b633ce0dedd889b7c08459433fbcf35e9c38d1c03ddc020f0648c6e`。[PyPI 元数据与下载 URL][ort-pypi] |

wheel 身份与源码／单独权重身份分别记录。本轮未读取 wheel 内容，尚未证明该
wheel 的全部代码与上述提交逐文件相同，亦未检查 wheel 中所有原生库通知。
准备阶段必须重新核对下载字节、成员清单和模型 SHA-256；不能用版本字符串代替。

### 后续分离候选

Spleeter 固定审查源码为
`c8854001ac8acad34a9bc2bd15f28475541828b1`，其中元数据版本为 `2.4.2`。
官方标签 API 当前只有 `v2.3.0` 和 `v1.4.0`；**未发现 `v2.4.2` 标签**，
不得编造标签或声称 PyPI 2.4.2 与当前源码自动等同。
[提交 API][sp-commit]、[标签 API][sp-tags]、[固定元数据][sp-project]。

| 对象 | 固定值／来源 |
| --- | --- |
| 推理包候选 | `spleeter-2.4.2-py3-none-any.whl`，48673 字节；SHA-256 `11b6aad050f89752e3752e08d8f69c69b699929157424e47c00e3e4db21073f9`。[PyPI 元数据与下载 URL][sp-pypi] |
| 官方模型 release | `v1.4.0`，release ID `21022168`；模型 release 与推理包版本分别固定。[release API][sp-release] |
| 模型资产 | [`4stems.tar.gz`][sp-model-download]，asset ID `15780960`，146308147 字节；API 的 `digest` 为 null，不能声称由该字段验证 |
| 官方模型 SHA-256 | `3adb4a50ad4eb18c7c4d65fcf4cf2367a07d48408a5eb7d03cd20067429dfaa8`，来自作者发布的 [`checksum.json`][sp-checksums]；不是本轮对大模型下载的实测值 |
| Windows CPU TensorFlow 入口 | `tensorflow==2.12.1`；`tensorflow-2.12.1-cp311-cp311-win_amd64.whl`，1916 字节，SHA-256 `4575641b7803dd87adbd0d610da147c08399c1aa7eac3505deedbad71671cc28`。[官方 PyPI][tf-pypi] |
| 实际 Windows CPU 大包 | `tensorflow_intel-2.12.1-cp311-cp311-win_amd64.whl`，272888761 字节，SHA-256 `f9fdbdaf075db41c7fafd9f61bb296112b81bf93e47718907b4321f09c911a92`。[官方 PyPI][tfi-pypi] |

模型 release 路径可被上游重新发布，只有固定哈希匹配的字节可进入准备流程。
解包后 checkpoint／配置的逐文件 SHA-256 清单、包与源码对应关系及完整依赖闭包
尚未取得；本报告不能替代这些证据。

### Demucs 记录，避免继续采用过时假设

原 Facebook 仓库已归档；本轮读到的归档 head 为
`e976d93ecc3865e5757426930257e200846a520a`，源码版本声明为 `4.1.0a2`，
Python `>=3.8`，最小依赖含 `torch>=1.8.1`、`torchaudio>=0.8,<2.1`。
这不是当前维护者 `v4.1.0`。[归档仓库][de-legacy]、[归档 metadata][de-legacy-setup]、
[归档依赖][de-legacy-deps]、[归档版本][de-legacy-version]。

维护者 fork 的 `v4.1.0` 指向
`6a604bb002d12c4fbabb303ba64db40b5c5743f0`，要求 Python `>=3.10`、
Torch `>=2.1`；普通推理使用 `sphn>=0.1.12`、safetensors、HF hub、julius 等，
torchaudio 已移到训练 extra。该标签 README／Windows 页仍含旧 torchaudio 安装
说明，不能据此安装不一致依赖。[标签 API][de-tag]、[固定 pyproject][de-project]、
[固定 Windows 页][de-windows]。

HTDemucs 权重 HF revision 为 `cbc8a9b1a87023b7fd74e7b3412e6321c0eab003`；
`955717e8.safetensors` 大小 84025440 字节，官方 LFS SHA-256 为
`d9fa14133cfcc034a6758923bb3a8ca9f8dfd0b582134643bbf83f72c17576dd`。
[固定资产 API][de-hf-api]、[固定下载地址][de-model-download]。
旧资产登记还有 `hybrid_transformer/955717e8-8726e21a.th`；文件名仅含短哈希，
不能当成完整 SHA-256。[登记文件][de-registry]。这些身份记录不授予使用权。

## Windows 推理与能力边界

| 项目 | 读取到的实际行为 | 集成要求 |
| --- | --- | --- |
| Basic Pitch 运行时选择 | Python 3.11 的官方依赖会安装 `tensorflow>=2.4.1,<2.15.1`；Windows 的默认 ONNX 依赖仅对 Python `<3.11` 生效。`[onnx]` 不会删除 TensorFlow 基础依赖。[metadata][bp-project]、[wheel 元数据 API][bp-pypi] | 推荐 CPython 3.11 独立进程、显式完整 wheel 清单及无 TF 的人工审查依赖闭包；这是对默认安装依赖的**明确偏离**，必须记录和实际验证，不能直接递归安装 `[onnx]` 后称其无 TF |
| Basic Pitch 实际执行 | 导入会探测多个 runtime，按 TF／CoreML／TFLite／ONNX 顺序尝试；ONNX `Model` 明确指定 `CPUExecutionProvider`。[初始化][bp-init]、[Model／predict][bp-inference] | 显式固定 `.onnx` 路径和实际 provider；只安装 GPU 包不会使此源码自动使用 GPU。无 TF 环境避免先加载 TF；8 线程需由 runner 明确配置并验证 |
| Basic Pitch 输入与输出 | 内部下混单声道并重采样至 22050Hz；权重处理约 2 秒窗口，音符范围对应钢琴 88 键，返回 note／onset／contour 与秒坐标事件。[输入处理][bp-inference]、[常量][bp-constants]、[音符后处理][bp-notes] | 保存原采样时钟、混声／重采样配方、窗口／重叠及回映射；实际转写只覆盖 pitched 音符，不是鼓类别检测或完整编制分轨 |
| Basic Pitch MIDI 默认值 | 导出初始 tempo 默认 120、乐器固定 Electric Piano 1；事件幅度转为 velocity，重叠 pitch bend 有丢弃／分 instrument 处理。[后处理][bp-notes] | 使用原始秒坐标 notes 与模型输出；120BPM／GM program 不是模型估计，velocity 也不是校准置信度。保留 bend 原始证据和派生策略，不拿生成 MIDI 默认值冒充编排事实 |
| Spleeter 运行时 | Python `>=3.8,<3.12`，固定 TensorFlow 2.12.1、tensorflow-io-gcs-filesystem 0.32.0，另有 NumPy／pandas／norbert 等；TF 2.12.1 实际进一步约束 NumPy `>=1.22,<=1.24.3`。[metadata][sp-project]、[TF 元数据][tf-pypi] | 独立于核心和 Basic Pitch 环境锁定；不能套用核心 NumPy 2.x。旧 TF／Estimator 依赖的兼容性与安全维护状态必须作为发布前工作，不能静默升级 TensorFlow |
| Spleeter 原生 Windows GPU | TensorFlow 官方指出 2.10 是原生 Windows GPU 支持的最后版本；2.11+ 的官方 NVIDIA 路径需要 WSL2。[官方安装文档][tf-install] | 此 2.12.1 配方先明确 CPU；不承诺 RTX 加速，不自动安装 WSL、CUDA、DirectML 或改全局环境 |
| Spleeter 分轨 | 固定配置为 44100Hz、双声道、vocals／drums／bass／other；`Separator.separate()` 接收数组，`separate_to_file()` 则使用音频适配器且默认 duration 为 600 秒。[配置][sp-config]、[Separator][sp-separator]、[adapter][sp-adapter] | 先接收已验证 PCM，显式重采样，用数组 API 避免另走 FFmpeg 解码和隐含截断；返回声部长度／起点必须独立核查。other 仍是混合残余，不能宣称已得钢琴／吉他独立轨 |

Basic Pitch 作者明确说明最适合一次处理单个乐器；分离的 vocals／bass 可以作为
先测对象，而 other 的多乐器混合仍需要明确拒绝／复核政策。
[固定 README][bp-readme]。人声主旋律、复音和声与低音的实际支持范围需要分别
评分；鼓类音符、节拍、速度、结构均未由这一对后端解决。

**音符时钟是首个适配实验的实质门槛。** 固定源码的 `ANNOTATIONS_FPS` 使用
`22050 // 256 = 86`，输入窗口为 43844 采样，重叠 30 行；`unwrap_output`
从每窗两端各裁 15 行后展平，再按 `floor(原始重采样长度×86/22050)` 裁尾。
`model_frames_to_time()` 另带每窗 `0.0018` 秒经验修正。
[常量][bp-constants]、[展平／裁切][bp-inference]、[时间换算][bp-notes]。
这些静态算术提示长曲尾部覆盖／坐标存在待验证风险，**本轮没有真实 native 输出
shape，不能断言已复现错误**。必须保存各窗输入采样起点、原始输出行及裁切关系，
以音频采样时钟映射推断事件；上游 heuristic 秒坐标与生成 MIDI 只能作为派生结果，
不能被接受为精确源时钟。该门槛应由真实短窗／边界／长尾实验解决，不阻止先接通
隔离推理、保留未获时钟资格的候选证据。

## 下载、模型加载和输出保护

- **Basic Pitch**：模型随官方包提供，已读的 `Model`／`predict` 路径加载本地文件，
  没有模型下载／私有音频上传调用；数据集下载命令是另一入口，不接入产品 runner。
  不调用在线 demo、训练／data extras 或第三方 VST。转写不需要 FL 插件。
  官方可选 sonify 使用 `pretty_midi.synthesize`，不能把它当作 FL 宿主渲染验收。
  [模型加载][bp-inference]、[入口声明][bp-project]、[sonify][bp-notes]。
- **Spleeter**：`ModelProvider.get()` 会在模型目录缺失时自动下载；`.probe` 存在
  或目录已存在不等于内容完整。默认 provider 可被 `GITHUB_HOST`／repository／release
  环境覆盖。下载器运行时取 checksum，并直接 `tar.extractall()`，不适合直接委托
  我们的安全准备流程。[provider][sp-provider]、[下载器][sp-download]。
  准备必须单独显式执行：固定 URL／size／SHA-256、拒绝越界／绝对路径／链接／特殊
  tar 成员、限额解包、完整 checkpoint 成员清单及逐文件哈希；推理前验证完整性，
  禁用下载分支并清理上述重定向环境。仅创建 `.probe` 不算合格准备。
- **Spleeter 加载**：图由固定 Python 模型代码构造，再从 checkpoint 恢复；模型配置
  动态导入函数，音频 adapter 也支持动态导入。只允许固定配置／固定模型函数及数组
  接口，禁止用户注入 module／class、图或 checkpoint 路径。
  [Separator][sp-separator]、[模型构建][sp-model]、[adapter][sp-adapter]。
- **Demucs**：新 HF 路径默认下载未指定 revision 的文件；失败会回退到旧远端。
  safetensors loader 仍根据元数据动态 import 类，旧 `.th` 路径明确
  `torch.load(..., weights_only=False)`；这不是可接受任意模型的安全边界。
  [选择逻辑][de-pretrained]、[HF loader][de-hf-loader]、[旧 repository][de-repo]、
  [状态加载][de-states]。即使未来取得许可，也需固定 revision、完整哈希及类别
  allowlist，并拒绝网络回退／任意模型入口。

以上是对已读应用代码路径的结论，未审计所有传递依赖／原生执行行为。
独立进程提供依赖与崩溃隔离，**不等于 OS 安全沙箱或已证明无网络能力**；
离线实验必须记录网络限制及缓存行为。TensorFlow 官方也将模型／图视作可执行程序，
不能把换成 checkpoint／ONNX／safetensors 当作自动信任依据。[官方安全说明][tf-security]。
所有结果由我们的新尝试目录、独占发布和输入前后身份核对保护，不直接信赖上游
CLI 的路径／覆盖检查。

## 当前硬件与质量证据

参考机按获确认设计为 i9-12900K／64GiB／RTX 3070 Ti 8GiB；父任务本轮只读
设备查询补充驱动 617.14。作业预算保持 8 CPU 线程、RAM ≤16GiB、VRAM ≤6GiB，
不是整机可用内存。当前核心环境没有模型栈；本轮未取得新推理时长或峰值证据。

Basic Pitch 作者发表过轻量、快于实时及小模型内存成绩；这来自作者配置与当时模型，
不是 Windows 完整 Python 进程、当前 ONNX 序列化、10 分钟输入或本机 RAM 基准。
[作者文章][bp-blog]。Spleeter 作者的 RTX 2080／双 Xeon 实验非常快，但不证明
原生 Windows CPU／本机预算表现。[论文][sp-paper]。Spleeter 源码按时间分块构造
频谱，却仍可把整段作为批输入；没有本机实测就不能保证长曲峰值低于 16GiB。
[模型构建][sp-model]。

Demucs 固定 README 给出默认约 7GB GPU 内存及缩小 segment／CPU 备用方案；
默认描述已超过本项目 6GiB 预算。HT 模型 segment 最大约 7.8 秒，同页笼统的
“建议至少 10 秒”不能直接套用；CPU 约 1.5 倍曲长也是上游概述，不是本机保证。
[固定 README][de-readme]。现阶段没有理由为了 GPU 路径忽略权重许可或改质量门槛。

本报告没有音符 F1、SI-SDR 或真实歌曲成绩。上游论文指标不能替代产品固定的
onset+offset F1 ≥0.80／单片段 ≥0.70，也不能证明 ≤1 解码采样对齐、鼓点门槛、
3 分钟暖运行 ≤30 分钟或连续十次稳定性。原有 MIDI／writer／宿主门槛保持阻断。

## 下一个可执行实验

1. **先完成 Basic Pitch CPU 的固定准备与真实离线推理。** 在新私有目录使用
   CPython 3.11，保存全部 wheel URL／SHA-256、原生成员及许可证通知；显式记录
   ONNX-only 无 TF 对默认依赖的偏离。固定模型 SHA-256、CPU provider／线程配置，
   真实子进程 handshake 应返回版本、实际加载文件和 provider，缺件／错 hash／
   不可加载／超时／取消必须明确失败，默认测试用原创极小数据且不安装模型。
2. 用原创、带真值的单声部和复音短 PCM 实际转写，保存 raw note／onset／contour、
   窗口／输出行原点、上游秒坐标及单独验证的采样映射、参数、输入输出和 runtime
   哈希；核对实际 ONNX shape、每窗裁切、末尾覆盖和跨窗重复／缺失，再接现有评分。
   首个“模型产出了音符”仅是推理完成证据，不能把作业改为交付成功。后续再做
   固定开发／校准／保留集与合法真实素材，任何阈值不因当前模型成绩变动。
3. **再准备 Spleeter CPU**：先核实 PyPI 包与审查源码差异，固定完整旧 TF 依赖
   闭包／通知和 4stems archive／checkpoint 清单；以已验证 44100Hz PCM 调用数组
   API，关闭导出多进程，拒绝隐含下载。先短片段测 RAM／线程／时序，随后决定
   外部分块策略；分块边界、重采样与尾部必须有独立对齐证据，不能只拼接 WAV。
4. vocals／bass 分别送入已验证转写器；other 保留其混合身份，drums 先只是音频轨。
   超资源、低置信度或未覆盖范围明确 blocked。GPU 分离留待有明确权重授权和
   原生 Windows 固定运行时的独立切片；不自动添加 WSL／驱动／模型转换器。

尚缺：传递 wheel／原生许可证闭包、源码与 wheel 对照、真实进程握手、离线约束、
取消与限额、重采样／分块时序资格、每类校准和保留集、完整歌曲与宿主／试听证据。
这些缺口不阻止先实现 Basic Pitch 的有界隔离实验，但阻止宣称模型已发布合格或
Suno 音频到可交付 FLP 已完成。更强转写模型本轮未独立审计；不把未经同等许可／
资源／基准核对的替代方案当作已可用后端。

## 一手来源与读取方式

Firecrawl search 用于定位官方仓库／作者材料，scrape 读取正文与固定源码；遇每分钟
配额后改用只读官方 GitHub／PyPI API 和少量官方文档读取，没有上传本地文件。
下列固定源码／LICENSE／NOTICE、模型目录、版本／资产 API、作者文章、相关官方
issue 正文均实际读取；下载 URL 由官方元数据确认，未声称全部大资产已下载核验。

[bp-license]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/LICENSE
[bp-notice]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/NOTICE
[bp-blog]: https://engineering.atspotify.com/2022/06/meet-basic-pitch
[bp-tree]: https://api.github.com/repos/spotify/basic-pitch/git/trees/9991303bba609a3b93089d13ec80d1d495083596?recursive=1
[bp-manifest]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/MANIFEST.in
[bp-tag]: https://api.github.com/repos/spotify/basic-pitch/git/ref/tags/v0.4.0
[bp-project]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/pyproject.toml
[bp-model-api]: https://api.github.com/repos/spotify/basic-pitch/contents/basic_pitch/saved_models/icassp_2022/nmp.onnx?ref=9991303bba609a3b93089d13ec80d1d495083596
[bp-model-download]: https://raw.githubusercontent.com/spotify/basic-pitch/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/saved_models/icassp_2022/nmp.onnx
[bp-pypi]: https://pypi.org/pypi/basic-pitch/0.4.0/json
[bp-init]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/__init__.py
[bp-inference]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/inference.py
[bp-notes]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/note_creation.py
[bp-constants]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/constants.py
[bp-readme]: https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/README.md
[ort-tag]: https://api.github.com/repos/microsoft/onnxruntime/git/ref/tags/v1.23.2
[ort-license]: https://github.com/microsoft/onnxruntime/blob/a83fc4d58cb48eb68890dd689f94f28288cf2278/LICENSE
[ort-pypi]: https://pypi.org/pypi/onnxruntime/1.23.2/json
[sp-license]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/LICENSE
[sp-paper]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/paper.md
[sp-joss]: https://joss.theoj.org/papers/10.21105/joss.02154
[sp-898]: https://github.com/deezer/spleeter/issues/898
[sp-957]: https://github.com/deezer/spleeter/issues/957
[sp-commit]: https://api.github.com/repos/deezer/spleeter/commits/c8854001ac8acad34a9bc2bd15f28475541828b1
[sp-tags]: https://api.github.com/repos/deezer/spleeter/tags?per_page=30
[sp-project]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/pyproject.toml
[sp-pypi]: https://pypi.org/pypi/spleeter/2.4.2/json
[sp-release]: https://api.github.com/repos/deezer/spleeter/releases/tags/v1.4.0
## 后续实现的实际前提补记

本文的初始来源审计与后续本机采用分开记录。当前实现及实际试验见
[Basic Pitch 接入](../BASIC_PITCH.zh-CN.md)。最初41归档的元数据闭包在真实导入时
缺少 resampy0.4.2 未声明的 `pkg_resources`；固定 setuptools80.9.0 后成为42归档，
不使用构建入口。该接口在[Setuptools82已移除](https://setuptools.pypa.io/en/stable/deprecated/pkg_resources.html)。
实际 wheel 审计还发现 setuptools vendored autocommand2.2.2 的 LGPLv3；保留其
通知，不能用发行包 MIT 元数据覆盖。完整分发／安装验收仍待完成。

[sp-model-download]: https://github.com/deezer/spleeter/releases/download/v1.4.0/4stems.tar.gz
[sp-checksums]: https://github.com/deezer/spleeter/releases/download/v1.4.0/checksum.json
[sp-config]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/resources/4stems.json
[sp-separator]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/separator.py
[sp-adapter]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/audio/adapter.py
[sp-provider]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/provider/__init__.py
[sp-download]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/provider/github.py
[sp-model]: https://github.com/deezer/spleeter/blob/c8854001ac8acad34a9bc2bd15f28475541828b1/spleeter/model/__init__.py
[tf-pypi]: https://pypi.org/pypi/tensorflow/2.12.1/json
[tfi-pypi]: https://pypi.org/pypi/tensorflow-intel/2.12.1/json
[tf-install]: https://www.tensorflow.org/install/pip#windows-native
[tf-security]: https://github.com/tensorflow/tensorflow/blob/master/SECURITY.md
[de-license]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/LICENSE
[de-weight-license]: https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611
[de-remove-license]: https://huggingface.co/adefossez/HTDemucs/commit/cbc8a9b1a87023b7fd74e7b3412e6321c0eab003
[de-hf-api]: https://huggingface.co/api/models/adefossez/HTDemucs/revision/cbc8a9b1a87023b7fd74e7b3412e6321c0eab003?blobs=true
[de-model-download]: https://huggingface.co/adefossez/HTDemucs/resolve/cbc8a9b1a87023b7fd74e7b3412e6321c0eab003/955717e8.safetensors
[de-legacy]: https://github.com/facebookresearch/demucs
[de-legacy-setup]: https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/setup.py
[de-legacy-deps]: https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/requirements_minimal.txt
[de-legacy-version]: https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/demucs/__init__.py
[de-tag]: https://api.github.com/repos/adefossez/demucs/git/ref/tags/v4.1.0
[de-project]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/pyproject.toml
[de-windows]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/docs/windows.md
[de-readme]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/README.md
[de-registry]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/demucs/remote/files.txt
[de-pretrained]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/demucs/pretrained.py
[de-hf-loader]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/demucs/hf.py
[de-repo]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/demucs/repo.py
[de-states]: https://github.com/adefossez/demucs/blob/6a604bb002d12c4fbabb303ba64db40b5c5743f0/demucs/states.py
