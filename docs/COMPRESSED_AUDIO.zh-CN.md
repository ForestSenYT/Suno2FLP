# 固定压缩音频解码与时序证据

M2 新增限定 FLAC／MP3 的只读完整扫描、显式隔离运行时准备、新 PCM 文件和独立复核。
GUI／CLI 使用同一作业服务。成功仅完成 input／decode；分离、转写、FLP、宿主和音乐
质量仍未完成。整数 WAV 保留原有[源整数逐样本证明](AUDIO_DECODE.zh-CN.md)，没有改走有损路线。

## 当前支持范围

所有输入最多 1 GiB、600 秒、8–192 kHz、单／双声道；不截断、重采样、交换声道或改变
呈现帧零点。压缩源先捕获一个身份校验的不可变快照，最多占用 1 GiB；逐样本解码按
4096 帧流式进行。单遍解析／解码／复核预算各 300 秒，取消在安全边界响应。

| 输入 | 放行所需证据 | 明确拒绝或阻断 |
| --- | --- | --- |
| FLAC | 原生容器，8／16／24 位整数，非零已知总帧数和 PCM MD5；完整元数据及逐帧结构、连续编号、CRC8／CRC16、完整 EOF | 未知总长／MD5、未支持位宽／编码、超限阻断；残缺、追加字节、拼接流、CRC／样本计数矛盾失败 |
| MP3 | MPEG Layer III，固定采样率／声道，完整 Xing／Info 和 LAME revision 0 扩展；帧数／字节数、delay／padding、music CRC／tag CRC 一致 | 不猜测无标记或未知编码器的起点；free-format、其他 layer、未知时序阻断；残缺帧、额外帧、校验矛盾失败 |

MP3 支持 8／11.025／12／16／22.05／24／32／44.1／48 kHz，单／双声道，CBR／VBR。
已知 ID3v2.3／2.4 前置标签（包括 v2.4 footer）与 ID3v1 尾标签保留区域身份；未知
元数据／串联流不会通过重新同步或丢弃字节来凑出成功。LAME delay／padding 分别最多
3000 帧，呈现帧数严格等于音频 MPEG 帧数乘每帧样本数，再减去 delay 和 padding。
不将第一帧 Xing 元数据计作音频帧，也不对解码样本再次裁剪。

MP3 还核对每个音频帧的 side information：在排除头、可选 CRC、side information 和
Xing 的音频载荷坐标上，检查 `main_data_begin` 指向已存在的数据，所有 granule／声道
的 `part2_3_length` 总和不读取未来帧，也不重用之前已消耗的位。保留合法的非零回指
和未用 ancillary 数据；音频 side-info 的原始字节按源顺序加入独立摘要。
这是结构范围检查，不是 Huffman 语义验证。

独立审查复现过一种原生假成功：只把第一音频帧回指改为 511 并重新计算完整 CRC，
解码器仍报告原帧数和零错误，但起始 240 帧被静默补零。当前门槛在 input 阶段拒绝
该情形，不让相同解码器的重放掩盖丢段。布局及载荷坐标依据
[Sieler／Sperschneider 的 Layer3 语法说明](https://mp3guessenc.sourceforge.io/MPEG%20Layer3%20Bitstream%20Syntax%20and%20Decoding.pdf)
§4.1.4／4.2.4；静音补偿行为另见 [mpg123 Layer III 解码器](https://raw.githubusercontent.com/madebr/mpg123/master/src/libmpg123/layer3.c)。

完整扫描最多一百万帧；FLAC 单帧解析预算 4 MiB。合法但超出支持预算的文件明确阻断，
不声称它们已经损坏。结构扫描不验证每个 MPEG 熵编码语义，也不证明音乐正确；随后
必须由固定 native decoder 实际读取完整帧数、无错误、全部有限样本并通过重放。

## 固定版本与真实握手

核心依赖和锁文件不增加 SoundFile／NumPy。用户显式准备到一个新私有目录；保留固定
wheel、全部许可通知、完整解压文件清单及 `backend.json`。支持 Windows／Linux x86_64，
Linux 需要 glibc 2.28+；应用解释器严格为 CPython 3.11.16 或 3.14.7，使用各自 ABI。
后端记录无权指定另一个可执行文件；切换应用解释器或安装位置需要重新准备运行时。

| 组件 | 固定版本／来源 |
| --- | --- |
| SoundFile | 0.14.0，源码 `3162358d0315be769b97f3e4c12545fe18a676bc` |
| libsndfile | 1.2.2，二进制子仓库 `a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87` |
| NumPy／CFFI | 2.3.5／2.0.0，固定 Windows／Linux、cp311／cp314 wheels |
| pycparser／typing_extensions | 2.23／4.16.0 |

十二个不同 wheel 的官方 URL、长度与 SHA-256，以及两个原生库哈希完整记录在
[`codec_wheels.json`](../src/suno2flp/integrations/codec_wheels.json)。Windows DLL SHA-256 为
`22518c16f9d13eda5ae5adf999c4740d7d16cc2d6b178b36dd4ac2f759a38559`；Linux SO 为
`c872fb84af2afc0e96b603e0000f0f407af86c49ad1126f2785e5722c7bb27d7`。wheel 原生载荷与固定
上游 git blob 做过逐字节映射；记录源码位置不等于声称可重现编译全部第三方二进制。

每次先核对官方归档与所有载荷，拒绝额外文件、链接、路径逃逸或变化，再真实启动
当前可信应用解释器的 `-I -S -B` 子进程。导入只增加指定包目录，禁止系统 libsndfile
回退；握手核对实际加载库路径／哈希、各包版本、Python ABI 和真实格式清单。
存在可执行文件／库文件不等于准备成功。操作前后重验身份，旧 JSON 成功标记不放行。
这提供进程和依赖隔离，**不是操作系统安全沙箱**；不保证抵御原生库中的所有漏洞。

SoundFile wrapper 为 BSD-3-Clause，libsndfile 为 LGPL-2.1-or-later；其编解码依赖还含
BSD／LGPL 等通知，NumPy wheels 另有捆绑库许可。CFFI 为 MIT、pycparser 为 BSD、
typing_extensions 为 PSF-2.0。原始通知全部保留在本地包树中；本仓库及发行 wheel
只包含原创适配器和固定元数据，不上传／打包这些二进制或上游源码。未来安装器的
许可清单、对应源码、库替换能力等发行验收仍属 M5，不能把当前审计当作完成。

依据：[SoundFile 0.14.0](https://pypi.org/project/soundfile/0.14.0/)、
[固定原生库仓库](https://github.com/bastibe/libsndfile-binaries/tree/a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87)、
[libsndfile API](https://libsndfile.github.io/libsndfile/api.html)、
[FLAC RFC 9639](https://www.rfc-editor.org/rfc/rfc9639.html)、
[ID3v2.4](https://id3.org/id3v2.4.0-structure)、
[LAME 官方源码](https://sourceforge.net/projects/lame/files/lame/3.100/)。

## 准备、运行和重放

以下命令仅用于研发阶段，父目录需已存在；始终选尚不存在的新目录：

```powershell
suno2flp provision-audio-decoder "D:\Runtimes\audio-v1"
# 也可显式给出已准备的官方固定 wheels，完全离线：
# suno2flp provision-audio-decoder "D:\Runtimes\audio-v2" --wheelhouse "D:\Wheels"
suno2flp verify-audio-decoder "D:\Runtimes\audio-v1"
suno2flp create-audio-job "C:\Music\song.flac" --output "D:\Jobs\song-v1" --job-id song-v1
suno2flp run-audio-job "D:\Jobs\song-v1\states\00000000.json" --decoder-directory "D:\Runtimes\audio-v1"
# 后续核验传运行结果中的 record.path：
suno2flp verify-audio-job "D:\Jobs\song-v1\states\00000005.json"
suno2flp-gui --jobs-root "D:\Jobs" --audio-runtime "D:\Runtimes\audio-v1"
```

准备命令默认只下载清单里的官方 PyPI wheels；GUI 启动不下载、不准备、不运行转换。
缺少运行时仍可完成 input 扫描，再以 `audio_backend_unavailable` 在 decode 阻断。
每次尝试创建新的 `decode-序号/attempt.json`，固定源身份、应用／适配器身份、请求的
运行时位置、零点和转换规则。失败／取消保留 `failure.json` 及已有候选；失败记录
包含有界 stdout／stderr，绝不复用半成品或覆写旧目录。已完成后指定另一运行时需新任务。

成功候选另有 `decoded.wav`／`decode.json`，原生进程按原始采样率和声道顺序写入
小端 float64，保持完整呈现帧数。报告保留原始容器时序字段、源／PCM／样本哈希、完整
运行时及请求身份。独立验证器只读重扫当前源、核对 58 字节 WAV 头及完整样本，再由
固定库逐样本重放比较；即使同时改 PCM、报告及对应哈希，也不能绕过当前源重放。
FLAC 还重算并对照源 STREAMINFO 的整数 PCM MD5；MP3 没有未压缩真值，明确记录
`unavailable-lossy`，相同解码器重放只是固定解码结果一致性的证明。

阶段完成产物为 `[PCM, decode report, attempt request]`。旧整数 WAV 保留两产物契约。
完成前必须通过独立复核；核验不写任何文件。所有结果保持音乐未评估、宿主未验证和
writer blocked；没有从音频证据自动取得 FLP 写入许可。

## 验证范围

默认测试仅含原创微型容器／损坏夹具和标准库子进程，不下载、不要求原生库／DAW。
显式设置 `SUNO2FLP_CODEC_WHEELHOUSE` 才运行真实 codec 集成测试，覆盖固定握手、完整
解码／重放、篡改拒绝、共享服务和 GUI model。原创 MP3 在九个采样率乘两个声道布局
上核对非整块尾长、完整帧数及相对于源的相关峰零偏移；FLAC 检查三种位宽的精确样本。
这些是有限资格样本，不保证任意编码器或曲目；不支持的时序标记继续阻断。

CI 四个平台／Python 组合使用固定的 3.11.16／3.14.7，在真正安装的 wheel 中显式准备
固定运行时并执行 `scripts/codec_smoke.py`。四个必需检查名称保持不变，不跟随次版本
最新补丁漂移。损坏／伪造检查只改该次新建原创候选，原始样本与运行时保持
不变。私有歌曲及其派生件只留本地；没有宿主启动、FLP 生成或音乐质量放行。

本地另从现有真实 WAV 创建一个新 FLAC 派生副本，48 kHz／双声道、8,400,000 帧、
精确 175 秒；完成全源重放后与原 WAV 的全部整数样本对照一致。它是无损派生测试，
不冒充用户提供了原始压缩素材。原文件身份保持不变，过程未启动宿主或生成歌曲 FLP。
