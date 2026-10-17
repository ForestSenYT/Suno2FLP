# 隔离的 Basic Pitch 音频转写候选

这是 M2 的开发接口：从已经独立核验的本地解码报告运行真实模型，保存完整预测和
估计音符。它不产生 MIDI／FLP，不完成共享作业的分离／转写阶段，不授予模型或音乐
质量资格。完整交付要求仍以[产品设计](superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
为准。GUI 目前仍在分离阶段阻断。

## 固定运行时与许可

- Basic Pitch 0.4.0 对应官方提交 `9991303bba609a3b93089d13ec80d1d495083596`；实际
  wheel 的 27 个 Python 文件及 ONNX 模型均与该 Git 树逐文件匹配。
- 模型 `nmp.onnx` 为 230444 字节，SHA-256
  `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`。
- 代码及保留的 Apache-2.0／NOTICE 与[Spotify 对开放模型用途的明确说明](https://engineering.atspotify.com/2022/06/meet-basic-pitch)
  分别核对；不把其他模型的代码许可推定为权重许可。完整选型见[一手来源审计](research/2026-10-16-audio-model-backends.zh-CN.md)。
- 首个原生配置仅支持当前可信应用解释器 CPython 3.11.16、Windows x64、
  ONNX Runtime 1.23.2、CPUExecutionProvider。模型采用 8 个 intra-op 线程、1 个
  inter-op 线程及顺序执行。GPU、其他 Python／系统尚未取得原生资格。
- [固定清单](../src/suno2flp/integrations/basic_pitch_pins.json)包含 42 个官方 PyPI
  归档，另有一份固定官方 FlatBuffers LICENSE。下载约 140.3MB；实际展开的
  7816 个文件共 412310778 字节。核心依赖和锁文件不增加 NumPy／模型运行时。
- 这是有意采用的无 TensorFlow 配置；上游在 Python3.11 默认要求 TensorFlow，
  不能声称等同上游普通安装或已通过其完整依赖检查。首次握手发现 resampy0.4.2
  使用未声明的 `pkg_resources`，因此明确固定 setuptools80.9.0；不执行 setup／
  构建／安装入口。[Setuptools 已在82移除该接口](https://setuptools.pypa.io/en/stable/deprecated/pkg_resources.html)。
- Pretty MIDI 0.2.11 只有源码归档：只复制核对过的七个 Python 文件及 MIT 许可，
  不执行构建、不复制或使用其音色库。coloredlogs.pth、setuptools 的
  distutils-precedence.pth 启动钩子及 NumPy 的一个预编译缓存共三项按固定哈希
  排除，其余 wheel 文件及全部原生／第三方通知保留。
  FlatBuffers wheel 缺失的完整 LICENSE 单独固定到官方提交补齐。

清单的 `license` 是发行包声明，不能覆盖 vendored 内容。实际核对到 setuptools
所带 autocommand2.2.2 的 LGPLv3 通知；它和其他 vendored 许可一起保留。完整
wheel 私有准备不等于只采用 setuptools 的 MIT 条款，也不构成安装器分发批准。

这些依赖只准备到私有目录。仓库及安装 wheel 不包含模型、供应商代码、DLL、音色库
或真实素材。BSD／MIT 包装层不能代替 NumPy／SciPy 的原生库、SoundFile／soxr
的 LGPL 等通知与分发义务；安装器的完整分发／替换／干净环境验收仍未完成。

## 明确准备与调用

当前准备接口消费已经按固定清单下载的本地文件，缺少或改动任何文件即失败，不会
在推理时下载模型，也没有自动安装到系统或 GUI 启动时准备依赖的行为。

```powershell
suno2flp prepare-basic-pitch --artifacts "D:\Suno2FLP-work\fixed-artifacts" --output "D:\Suno2FLP-work\backend-v1"
suno2flp verify-basic-pitch "D:\Suno2FLP-work\backend-v1" --output "D:\Suno2FLP-work\probe-v1"
suno2flp transcribe-audio "D:\Suno2FLP-work\decode\decode.json" --backend "D:\Suno2FLP-work\backend-v1" --output "D:\Suno2FLP-work\candidate-v1"
suno2flp verify-transcription "D:\Suno2FLP-work\candidate-v1\transcription.json" --output "D:\Suno2FLP-work\replay-v1"
```

父目录必须存在，所有输出目录必须全新且位于输入／后端之外。解码报告来自
`importer.pcm_decode.decode_pcm_wave` 或[限定压缩解码](COMPRESSED_AUDIO.zh-CN.md)，
也可使用真实作业中当前核验通过的解码产物；任意自填 JSON／未核验 WAV 不受信任。
CLI 返回0只表示这项准备／候选／重放操作成功，输出仍为 `unqualified_candidate`；
参数或前提失败返回1。它与共享作业的 `succeeded` 无关。

准备只复制安全、常规、大小受限的固定归档成员；拒绝链接、路径穿越、大小写冲突、
歧义名称和扩展超限。原生握手必须真正加载模型并推理，核对版本、模块路径、CPU
提供器、线程及输出形状，两次相同输入逐字节一致；文件存在不算握手成功。

## 估计坐标与保留数据

原始解码 PCM 保留原采样率、声道和全部帧。模型前端明确按 binary64 声道均值转成
float32 单声道，再用固定 SciPy `resample_poly`、Kaiser5、常量零边界得到22050Hz。
帧数为 `ceil(原帧数×22050/原采样率)`，原点不变；没有额外音量归一化或限幅。
这个派生波形另存 `mono.f32`，原 PCM 和源文件不改写。

模型输入窗口43844采样、步长36164、虚拟左补3840；每窗真实输出 note／onset
`[1,172,88]`、contour `[1,172,264]`。全部窗口、全部行以小端 float32 原样保存。
本适配器明确使用每窗15..156行中落在源内的行，锚点是
`窗口编号×36164 −3840 + 行号×256`。接缝实际间距可为68采样，不能强行当成
均匀86FPS；重叠／补零行仍可按原始地址核查。有效尾行必须距源结束不超过256采样。

这是显式的**估计坐标配置**，并非神经网络 onset 准确率证明。窗口／重采样的确定
关系不等同于每个预测音符正确。没有使用上游 MIDI 默认120BPM、音色、重叠弯音
删除策略或经验秒数修正，更没有修改既有 MIDI。固定上游原始后处理阈值为
onset0.5／frame0.3、min_note_len11、energy_tol11、infer_onsets／melodia开启，
频率范围不裁剪；这些工程默认值尚未通过发布校准。

`transcription.json` 保存当前源／解码／解释器／适配器／全部模型文件身份、参数、
原始数组、模型逐帧音符及弯音地址。`native/` 保留请求、结果、标准输出／错误、
派生波形、三个原始数组和 `bends.i8`。弯音单位为1/3半音，每个音符完整保留，
重叠不删除；activation 是模型激活值，明确不是校准置信度。速度和角色均未估计。
辅助 `frame_notes_to_scored` 按这些锚点转换为原采样时钟的有理数微秒，尾端使用
原时长；它仅用于已声明的候选评分，不赋予源 MIDI 权威。

## 当前证据与限制

默认离线测试使用原创小数据和明确标注的模拟原生协议，测试失效、原始数值范围、
来源变化、独占输出、取消及重算哈希的伪造预测。四个现有 CI 平台执行安装后纯接口
冒烟，不下载模型；它们不构成原生模型验收。

Linux CI 曾发现运行中的虚拟环境 Python 是符号链接，转写配方因此提前拒绝记录。
现与解码／评分一致，只对已经运行的应用解释器解析真实路径并绑定文件身份；素材、
模型和输出路径仍拒绝链接／路径穿越。回归覆盖解释器别名、目标变化与输入规则，
这不扩大仅支持 Windows x64 的原生后端范围。旧候选保留当时配方及源码快照，
配方变更后不能冒充当前版本的新推理证据。

本机真实握手已经成功。三个原创8秒振荡器片段分别覆盖顺序单音、复音和接缝／
尾音，共8个参考音符；三项 onset+offset F1 均为1，全部原始预测和音符重放一致。
这些是工程夹具，不属于24片段发布曲库，不能据此认定真实乐器／人声准确率。

当前175秒私有歌曲完成解码、转写和完整新推理重放：107个原始窗口、15152个
有效锚点、3022个估计音符，源文件身份未变。该次总墙钟约375秒，包含完整性
扫描和重复推理；不是纯模型耗时，也不是发布性能基准，尚未测峰值内存及10次
稳定性。单曲没有逐音符真值，仍标记 `ground_truth_metrics=unavailable`。

原生 opt-in 首次回归实际发现测试把2秒音频的有效行数错写为174；独立坐标推导
为首窗142行＋次窗31行＝173，下一锚点44100恰为不包含的结束位置。仅修正测试，
补充44100／44101采样的两侧边界，未移动源事件或改变生产时钟。失败证据保留；
新的独占目录原生回归已通过（1项，约477秒），涵盖真实准备、握手、转写和完整
重放。模型与生产时钟在这次修正中保持不变。

核验不是只重算文件哈希：`verify-transcription` 先独立验证当前源／解码，再在新
目录重新执行真实模型，比较全部原始预测、派生波形、音符及弯音；更新声明哈希也
不能掩盖与重新推理不同的结果。准备／核验保留全部文件及目录变化检查。后台子
进程使用 `-I -S -B`、最小环境、捕获日志、1800秒上限和取消；只停止自己创建的
进程。目录树扫描有300秒／1GiB／20000文件上限及逐块取消。依赖隔离不是 OS 沙箱。
Windows CI 进一步发现目录时间戳可能未及时反映新增成员；扫描结束还需重新列出
各目录成员，核对名称集合与目录身份。合成回归刻意恢复原时间戳后新增文件／空目录，
仍须拒绝该次扫描，不能仅以时间戳相同推断目录未变。

Basic Pitch 最适合单乐器，整曲混音候选不代表已经分离出乐器。24片段／6曲质量、
鼓与节拍、分离、校准、10次稳定性、完整性能／峰值内存、宿主、GUI／安装和试听
仍未通过；`model_qualification=not_assessed`、`ground_truth_metrics=unavailable`、
`musical_correctness=not_proven_per_song`、`writer_eligibility=blocked`、
`execution_allowed=false` 始终保留。[来源绑定分轨候选](SEPARATION.zh-CN.md)已有独立开发
入口；尚须明确的分轨来源／精度桥接才能供转写消费，不能把分离估计伪装为原始解码。
后续再接共享作业／推断编排；未知或不足的音乐和宿主证据继续阻断交付。
