# YourMT3+ 固定隔离候选

这是 M2 的开发用多乐器转写路径，输出带完整原始证据的未验收候选。它不接通交付
作业、GUI 自动转换、MIDI 导出或 FLP 写入，也不因推理完成而授予音乐质量资格。
本曲之前的候选已被用户明确否定：错音、节奏错误、段落缺失。该结论继续保留。

## 固定来源与许可

| 项目 | 固定身份 |
| --- | --- |
| 作者 Space 源码 | `mimbres/YourMT3`，`5e66c1ea173a8186e0d20432b841d3180cc015b5` |
| 作者权重仓库 | `mimbres/YourMT3`，`e45ebd70398682d54b7bb1901a5216e18f3b1824` |
| 模型 | `YPTF+Single (noPS)`，`ptf_all_cross_rebal5_mirst_xk2_edr005_attend_c_full_plus_b100/checkpoints/model.ckpt` |
| 权重实际大小 | `361050039` 字节 |
| 权重 SHA256 | `507ff129bf68f65b3b3439368706fc413523fc729d994e4da2c3f50860b05dde` |
| 本轮运行配置 | Windows x64，CPython 3.11.16，Torch/Torchaudio 2.11.0+cpu，NumPy 1.26.4，einops 0.8.0，Transformers 4.45.1，PyTorch Lightning 2.4.0 |

完整 59 个 wheel、31 个作者模块、许可文件、逐文件 URL／大小／哈希、386 个张量的
完整形状及类型、实际配置、允许恢复的对象名称均固定在
`src/suno2flp/integrations/yourmt3_pins.json`。只重用本地已审计安装包作为新目录的
只读输入，不共享旧后端的可变包目录，不向应用核心添加 ML 依赖。

使用的是作者 [Space 的固定许可声明](https://huggingface.co/spaces/mimbres/YourMT3/blob/5e66c1ea173a8186e0d20432b841d3180cc015b5/README.md)
和[权重模型卡](https://huggingface.co/mimbres/YourMT3/blob/e45ebd70398682d54b7bb1901a5216e18f3b1824/README.md)
中的 Apache-2.0 授权。GitHub 展示仓库的 GPL-3.0 不被泛化为 Space 的许可，也没有
把它的代码复制进应用。Space 未提供独立根 LICENSE／NOTICE，保留模型卡、作者文件
头和完整 Apache 文本；来源不完整的第三方归属仍须另行核对，不能只凭模型卡抹去。

选中源码还引用 rotary-embedding-torch、x-transformers、nanoT5、D-Adaptation、
Hugging Face 的实现。隔离目录保留固定上游 MIT／Apache 许可、已有作者头及依赖
wheel 的全部许可证；tokenizers 和 tqdm 补充固定源码许可。certifi／tqdm 等依赖有
MPL 条款，不能把整个运行时统称为 MIT／Apache。只分发本项目原创适配器与固定清单，
不随应用上传或分发这些模型、后端、歌曲或私有工程。训练素材／生成音乐权利和后续
商业发布、完整模型分发审核不能从本轮运行证明中推导。

## 执行与时钟

准备命令只接受已经下载并核对的本地固定文件。它验证完整包内容及许可证，拒绝
链接、重复成员和隐式启动项；只有明确固定并校验哈希的 `.pth`／`.pyc` 可从 payload
省略。输出独占创建；当前应用源码、解释器、全部包内容和原始安装包均重查身份。
包和源文件保持原字节，不运行 upstream setup、Gradio、YouTube 或演示入口。

推理位于独立 `-I -S -B` 子进程，CPU 8 线程／interop 1 线程，float32，固定种子与
确定性算法。禁用 GPU、Python socket 连接／发送、Hub 下载回退、训练和在线日志；缓存和临时文件
放入新尝试目录。2700 秒、输出大小及 16 GiB **实测峰值**是验收限额，内存测量不是
操作系统内存沙箱。GPU、FP16、其他 Python／Torch 配置均未由 CPU 结果证明。
编译器缓存也必须显式位于本次尝试目录，不能依赖宿主用户名或全局缓存。

官方辅助函数使用 `weights_only=False` 和 `strict=False`，本适配器不调用它。
固定权重含训练元数据；默认安全加载先明确失败，随后审计固定作者类型及 NumPy
对象，只在精确哈希匹配时使用明确白名单的 `weights_only=True`。没有任意对象
发现／自动扩大白名单或不安全加载回退。所有 380 个 float32 和 6 个 int64 张量、
配置、词元含义及实例完整 state 必须匹配，最终 `strict=True`。
参见 [PyTorch 2.11 安全加载说明](https://docs.pytorch.org/docs/2.11/notes/serialization.html)。

输入必须是已独立验证的原始 PCM 解码报告。声道按作者的算术平均合为单声道，采用
固定 Torchaudio 默认 sinc 参数重采样到 16000 Hz；完整长度为原始帧数换算后的向上
取整值。从模型帧 0 开始连续使用 32767 帧窗口，仅最后窗口补右侧零，不按观察片段
裁切输入。原始帧、窗口起点、有效尾帧及所有词元保留；观察区间只作半开统计视图，
跨区间音符保留原始起止，不被剪短或移位。

作者的解码器会先将每个窗口的起点四舍五入到 10 ms 网格，再解释 shift 词元。
原生音符时间和解码事件均保留，不能称为原 MIDI 精确时间或由浮点换算证明神经
起音准确。也不调用作者的额外 `mix_notes` 修剪路径。解码本身的补齐／接续行为、
错误计数和前置事件仍可从完整词元与合并前窗口记录重放。

program 100／101 是本模型的歌声标签，128 是鼓，129 是未标注；它们不是已确认的
GM 音源或 FL Studio 通道。原生 velocity 0／1 也不是经校准的力度或置信度。
适配器不把这些标签强塞进既有四声部配置，不加载插件或暗中丢弃不支持的角色。

## 使用与独立检查

```powershell
uv run suno2flp prepare-yourmt3-backend --artifacts <固定本地文件目录> --output <新后端目录>
uv run suno2flp transcribe-yourmt3 <decode.json> --backend <新后端目录> --intervals <区间数组.json> --output <新候选目录>
uv run suno2flp verify-yourmt3 <新候选目录/yourmt3.json>
```

区间文件是 `[{"start_frame":0,"end_frame":720000}]` 形式的原始音频帧数组，不能重叠、
倒序或越界。成功名称 `yourmt3.json` 只在原始音频／PCM、后端、请求、输出和区间
统计通过独立检查后发布。检查器在新建的同级 `yourmt3-token-replay-*` 目录重放全部
词元并核对原生音符、合并前窗口／事件和错误计数；不修改原候选。它证明当前文件
与词元解码一致，**不证明模型数值推理重跑一致或音乐正确**。

默认测试完全离线，不需要模型／GPU／DAW。显式设置 `SUNO2FLP_YOURMT3_BACKEND`
才执行 `tests/integration/test_yourmt3_external.py`，使用原创信号验证真实握手、
1 帧短尾、重复词元、独立解码和原文件不变；缺少后端会明确跳过。

## 本曲对照与保留限制

推理前固定六段：0–15、30–45、60–75、90–105、120–135、160–175 秒。它们属于同一
首歌，不等于设计所需 24 个校准／保留片段或 6 首验收歌曲，也没有人工标注真值。
本地首轮探索完整覆盖 175 秒／86 窗口，得到 8753 个原生音符、23 类 program。
最终正式路径的全部词元和音符与首轮实验一致，独立解码与输入完整性检查通过。
用户随后对固定 60–75 秒的原曲／旧音符／YourMT3 同音色对照反馈「两者都不达标」；
该片段的音乐验收明确失败，其他片段不能由这一回答推定通过或失败。这不是宿主渲染
或最终音色验收，也不能由运行可复现解除新 FLP 和后台渲染限制。
保留了 30 次无对应起音的 note-off 解码错误，以及合并阶段 715 次找不到起音、
544 次 segment tie 错误。这些是错误出现次数，不能相加解释为唯一错误音符数。

更多音符、覆盖更广、严格加载成功或能发声均不足以证明错音、节奏和缺段改善。
真实曲目的音高／起音 F1 继续为 `reference_unavailable`。跨窗口接续、乐器标签与
实际音源映射需要进一步证据；在音乐对照及独立路由配置获得支持前，不生成新 FLP
或启动本曲后台宿主渲染。旧精确变速、控制送达、crop／flag、AudioClip、GUI 另存、
曲库、安装与发布门槛继续阻断。本曲素材、完整词元、失败尝试与对照只保存在本地
新的忽略目录，禁止上传。
