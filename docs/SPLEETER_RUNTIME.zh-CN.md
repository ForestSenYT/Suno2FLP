# Spleeter 本地分轨运行环境：准备与真实握手

这是 M2 的运行前提切片。它提供 `prepare-spleeter` 和 `verify-spleeter`，在独立
Windows CPU 子进程中加载固定模型，保存原创合成信号的原始输出并独立核对。
**它尚未提供完整歌曲分轨、合格模型、完整转换作业或 FLP 交付。**
音频分离质量、完整歌曲的分块／重采样／残差、共享作业接入仍是后续切片；
参见[批准设计](superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
和[持续路线](DELIVERY_ROADMAP.zh-CN.md)。

## 固定对象与依赖差异

| 对象 | 固定身份 |
| --- | --- |
| 本地执行 | 可信应用 CPython 3.11.16、Windows x64；CPU、8 个 intra-op 线程、1 个 inter-op 线程 |
| Spleeter | 2.4.2；源码 `c8854001ac8acad34a9bc2bd15f28475541828b1`；wheel SHA-256 `11b6aad050f89752e3752e08d8f69c69b699929157424e47c00e3e4db21073f9` |
| 模型 | 官方 v1.4.0 `4stems.tar.gz`，146,308,147 字节；SHA-256 `3adb4a50ad4eb18c7c4d65fcf4cf2367a07d48408a5eb7d03cd20067429dfaa8` |
| 主要运行包 | TensorFlow／Intel 2.12.1、Keras 2.12.0、NumPy 1.24.3、SciPy 1.15.3、pandas 1.5.3 |
| 配方 | `spleeter4-local-graph-windows-cp311-v1`；50 个固定 wheel、模型归档、4 份补充通知，共 55 个输入文件 |
| 完整清单 | [`spleeter_pins.json`](../src/suno2flp/integrations/spleeter_pins.json)：每包官方 URL、大小、SHA-256、通知、成员映射；模型五个成员与 30 个 Spleeter 源码成员身份 |

默认 Spleeter 依赖要求 TFIO GCS **0.32.0**，该版本没有 Windows wheel。本配方明确
偏离默认安装，只执行本地图计算：保留 TensorFlow 自身元数据允许的 **0.31.0**，
并禁用模块化文件系统；其原生插件没有获得兼容资格。上游 TFIO 兼容表也没有把
0.31.0 与 TF2.12 配对。没有静默替换依赖后声称原始闭包满足。

`spleeter.utils.tensor` 顶层需要 pandas，所以即使不读训练 CSV，也保留其固定依赖。
不调用 Spleeter CLI、FFmpeg、ModelProvider、Norbert／MWF、云文件系统或 TensorBoard
服务。初始 47 包候选缺少 pandas，在执行前根据源码补齐；原候选及失败的默认依赖
解析记录留在本地，未伪装成成功安装。

代码及模型使用作者 JOSS 论文中的 MIT 声明作为来源依据，同时保留 README 只提代码、
模型许可问询仍无回复的差异。模型归档没有随附新的许可证；本地安装保留 Spleeter MIT
通知。TensorFlow／JAX 等主要为 Apache-2.0，NumPy／SciPy／pandas 为 BSD 系列，
certifi 为 MPL-2.0，其他依赖及原生／vendored 组件以各自完整通知为准，不能一概改标 MIT。
四份 wheel 缺失的通知从精确官方源码提交补充。具体出处与执行风险见
[独立研究](research/2026-10-16-spleeter-runtime.zh-CN.md)及[依赖清单](DEPENDENCIES.md)。

## 使用开发命令

准备者须先按固定清单把 55 个官方文件下载到一个新的私有目录并核对哈希。
这两个命令不会联网、下载模型或改动主 Python 环境。

```powershell
uv run suno2flp prepare-spleeter --artifacts D:\private\spleeter-artifacts --output D:\private\spleeter-backend-v1
uv run suno2flp verify-spleeter D:\private\spleeter-backend-v1 --output D:\private\spleeter-probe-v1
```

路径仅为示例；输出必须不存在、父目录必须存在，且不能位于输入／后端内部或
`site-packages`／`dist-packages` 路径。原有目录、软链接／reparse 路径、重叠路径、缺包、
错误 Python／平台、大小／哈希／成员差异均明确失败。失败的新尝试保留诊断，不覆盖重试。

准备结果是 `prepared_not_probed`。只有实际子进程恢复 checkpoint、完成信号实验、
核对结果和当前文件身份后才返回 `native_runtime_verified`；两者都保持：

- `model_qualification=not_assessed`，音乐质量未验收。
- `whole_song_support=not_implemented`，不能拿此入口处理整首歌。
- `writer_eligibility=blocked`、`execution_allowed=false`，不推进作业成功或 FLP 写入。

## 安装与执行边界

安装仅复制检查过的普通归档成员，不执行 setup／构建脚本或 `.pth`。唯一按哈希排除的
setuptools 启动 `.pth` 保留在源 wheel；libclang 的 `.data/platlib` 成员有逐项显式映射。
模型归档中的 `./._checkpoint` AppleDouble 记录映射到安全的惰性名字，保留原名、大小
和哈希；没有放宽通用路径检查。`checkpoint`、`model.meta` 留作来源材料，恢复模型只用
固定 `model/model` 前缀的 index／data，绝不导入序列化 meta graph 或跟随归档中的路径声明。

实际 TensorFlow 本机库为 665,107,456 字节，因此此配方显式使用单成员最多 1 GiB、
单 wheel 展开最多 2 GiB、完整负载最多 3 GiB／20,000 文件、输入归档总计最多 768 MiB。
Basic Pitch 的默认单成员 128 MiB／展开 1 GiB 门槛保持。当前 50 个 wheel 的下载总量为
457,752,811 字节；55 个输入合计 604,108,723 字节。准备还需展开副本及每次实验的磁盘空间。

子进程使用 `-I -S -B`，固定 CPU、线程、种子和关闭 oneDNN 的配方。通用启动器只传递
必要 Windows 临时目录环境；worker 再禁用 CUDA、TFIO 及额外插件路径。私有目录不能触发
TF 的 site-packages 插件扫描，实际模块必须来自固定负载。完整负载、运行时、适配代码和
原始归档在执行及报告发布边界重复核对。1800 秒超时、取消及日志上限沿用有测试的有界
进程工具；只停止自己创建的子进程。哈希检查在边界执行，取消不是即时抢占所有文件 I/O。

这是可信本机文件的完整性防护，不是操作系统安全沙箱，也不声称所有 Windows 系统 DLL
已经获得独立发布资格。这里只验证小型信号；10 分钟输入、峰值资源、10 次稳定运行及
最终安装包的系统依赖均仍须按产品设计另行验收。

## 信号、时序与结果材料

worker 从固定源码构造 `4stems` 图：44,100 Hz、双声道，窗长4096、步长1024、
T512、F1024、`mask_extension=zeros`、MWF关闭。restore 后记录实际变量形状与值摘要；
没有用“文件存在”“版本相同”代替模型执行。

三份原创信号分别是 1025 帧静音、12347 帧首／中／末脉冲，以及 44117 帧左右声道不同
的非零周期信号。每个信号完整运行两次，保留两个版本的四个原始 float32 输出，要求形状、
有限数值和哈希相同。父进程另读所有样本，检查源信号、完整长度、非零信号的非平凡输出，
以及脉冲峰位置偏差不超过一个采样点。

四轨不会包含默认模型舍弃的全部高频。父进程按固定声部顺序以 float64 计算
`unassigned_residual = input - sum(stems)`，保存每个样本，报告峰值及不超过 `1e-12`
的信号守恒误差；残差是未分配内容，不是第五种分离乐器。守恒误差小也不证明声部归属正确。

新目录包含输入、24 个原始输出、3 个 float64 残差、请求、原始结果、stdout／stderr
及带完整来源链的报告。先写 `probe.pending.json`，核对其字节、全部见证文件和负载，
再以同目录独占硬链接发布 `probe.json`；这个最后的原子步骤是完成标记。校验失败仅留下
暂存报告和原始诊断。目标已存在或文件系统不支持硬链接时明确失败，不覆盖或退回非原子
写入。成功时两个名字共享字节，都必须作为不可变证据保存；完成标记证明当次核验，
不能代替后续使用前的当前哈希复核。上游不保证 TF1 Session 普遍确定性，所以报告只写
`observed-two-runs-per-fixture`；独立新进程的比较由 opt-in 测试另提供证据。

默认合成测试不需要模型／网络／DAW。真实测试需显式设置：

```powershell
$env:SUNO2FLP_SPLEETER_ARTIFACTS='D:\private\spleeter-artifacts'
uv run pytest tests/integration/test_spleeter_external.py
```

本地首轮真实准备和两个独立子进程测试已通过（约639秒，包括多次完整文件核验，
不是整曲性能基准）。两个进程的50包版本、296个恢复变量摘要及全部输出哈希一致。
脉冲峰在 `[0,6000,12346]`，静音残差为0；非零周期信号的未分配残差峰值约0.18615，
加入残差后的最大守恒误差约 `2.78e-17`。实际安装负载为16,788个文件、1,801,808,107字节。
固定 Keras 学习阶段 API 的弃用警告完整保留在 stderr，没有被隐藏为新版本兼容。

后续自查另复现并修复结果 JSON 在解析与单独哈希之间变化的记录问题：现在身份和
解析字节来自同一次读取，新增变更测试会拒绝不一致。首轮原始记录和源码快照保留，
该修复后的第二轮实际独立进程复测也通过（约558秒）。独立审查随后复现最后校验失败
却留下完成报告的问题，改为上述暂存核验与独占发布；新增5个拒绝路径及完整23个后端
合成用例已通过。当前受限沙箱拒绝硬链接，普通用户权限下已验证成功路径；该限制会
明确报错，不通过复制回退。所有旧尝试和对应源码快照保留。
合并前仍需对最终适配代码重新做 native 验证；实际最终提交／CI／审查以对应 PR 为准。
24 片段的 SI-SDR 改善、六首实曲、分离后转写、宿主重开／渲染及听验门槛不会被探针替代。
