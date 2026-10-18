# YourMT3+ MoE：独立配置与生成完整性证据

这是 M2 的独立开发候选，不是已验收的音乐重建或可交付 FLP。Single 的 60–75 秒
试听失败记录继续保留；MoE 的听感、真值评分、角色路由、宿主和发布另行验收。

## 固定身份与真实加载

- 作者 Space：`5e66c1ea173a8186e0d20432b841d3180cc015b5`。
- 权重库：`e45ebd70398682d54b7bb1901a5216e18f3b1824`。
- 模型：`YPTF.MoE+Multi (noPS)`，权重文件
  `logs/2024/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/checkpoints/last.ckpt`。
- 实际权重 561544628 字节，SHA256
  `ae38e415c79efd5592dcb9b658cdb99ddb11d4c4e1eaa364cab04a052473fc25`。
- 31 个作者源码文件、完整通知和 59 个 wheel 与 Single 使用相同固定版本；新建私有
  文件和运行目录，不向应用核心安装 ML 依赖，不分发模型、后端或歌曲。

来源与许可分别依据[固定 Space 卡](https://huggingface.co/spaces/mimbres/YourMT3/blob/5e66c1ea173a8186e0d20432b841d3180cc015b5/README.md)
及[固定模型卡](https://huggingface.co/mimbres/YourMT3/blob/e45ebd70398682d54b7bb1901a5216e18f3b1824/README.md)
的 Apache-2.0 声明；保留现有第三方和 wheel 通知，不泛化为整个运行时都是 Apache，
也不由此推导训练音乐权利或完整模型分发资格。参见[依赖清单](DEPENDENCIES.md)。

原生调查在独立 Windows CPython3.11.16／Torch2.11.0+cpu／float32、8 工作线程、
interop1、固定 seed3、确定性算法下执行。默认安全加载明确拒绝未审对象后，只对
已固定源码、无恢复 hook 的作者类型及明确 NumPy 类型使用安全白名单，始终
`weights_only=True`。655 个完整状态条目（649 个 float32、6 个 int64）均有限，
key／shape／dtype 完整匹配并 `strict=True` 加载；没有丢弃 pitchshift 或其他参数。
训练器、优化器、回调和在线日志不恢复，app／Gradio 演示入口不执行。

文件名中的 `rms` 不能决定模型归一化。固定 checkpoint 实际声明
`layer_norm_type=layer_norm`。作者覆盖函数写入 `rope_partial_pe=True`，而配置中
另有不同的 `rotary_partial_pe=False`。首轮私有探针用错相近名称，严格比较拦住了
18 处 RoPE 形状差异；修正为作者实际覆盖后，全部 655 项通过。失败尝试完整保留，
没有修改作者源码或使用 `strict=False` 掩盖差异。训练 dropout 与演示默认值的
差别不被隐去；本路径使用 `.eval()`，运行配置单独完整记录，不冒称论文 GPU 精度。

## 十三个通道及原始时钟

模型解码通道依次是 Piano、Chromatic Percussion、Organ、Guitar、Bass、Strings、
Brass、Reed、Pipe、Synth Lead、Synth Pad、Singing Voice、Drums。完整 99 个
program 到通道的作者映射保存在固定清单。它们不是来源 MIDI 通道、独立音频分轨
或已经正确识别的乐器，更不等于音源可用或 DAW 路由已经通过。

输入按已验证 PCM 的 float32 算术平均声道、固定默认 sinc 重采样到 16kHz。
从全曲模型帧 0 连续使用 32767 帧窗口，只对最后窗口补零；保留原采样帧坐标、
每窗口有效尾帧、全部 13 个地址和所有原生词元。每通道单独解码／接续，保留
合并前 events／ties、合并后 notes 和错误计数。不调用作者额外的 `mix_notes`
重叠裁剪；诊断合奏只是把全部通道相加，没有偷偷删音、量化、改音高或移动时序。
作者窗口原点仍按 10ms 网格解释，不能把它标成源 MIDI 精确时间或已校准起音。

## 有界生成对照

作者默认每通道最多 256 个词元；在本地完整歌曲诊断中，16 个窗口至少一条流在
上限处仍没有 EOS。不能把保存了最后一个词元等同于生成已经结束。

固定[作者推理 API](https://huggingface.co/spaces/mimbres/YourMT3/blob/5e66c1ea173a8186e0d20432b841d3180cc015b5/amt/src/model/ymt3.py)
接受独立的 `max_token_length`，其生成器把它用作循环上限。新实验保持源码、权重、
输入、全局窗口、精度和种子相同：

1. 先将这些窗口的上限设为 512，所有原 256 个词元逐通道完全相同；15 个窗口
   到达 EOS，剩余窗口的时间事件继续从 1.3 秒推进至 1.8 秒，但仍触顶。
2. 只对剩余窗口使用 1024 上限，原 512 个词元保持一致，在 599 个词元处结束。
   所有最终流均有 EOS，13 通道独立词元解码与记录一致。

产品候选使用明确的一次有界策略：默认 256；仅在任一通道缺 EOS 时重试 1024，
要求全部初始 256 个词元是相同前缀；初始和重试两份流均保留。1024 仍未结束时
记录具体窗口／通道，不称为生成完整，不授予写入资格。这是超过训练上下文 256
的推理预算变体，尚需质量校准，不是降低音乐阈值或增加训练能力的证明。

原始默认诊断覆盖 175 秒／86 窗口，约 434 秒，峰值 commit 约 2.77GB；后续对照
只重算触顶窗口，不能把其额外耗时当作完整作业基准。输出音符增加、EOS 完整、
严格加载或相同词元重放都不证明错音、节奏和缺段已改善。六个固定片段仍属于同一
首歌，不替代 24 个真值片段／6 首真实曲库；当前真实音符 F1 为未获得参考真值。

## 接入状态

独立 MoE 合同和事实清单已建立；正式 backend／worker／候选发布／命令行及当前
源码下的原生复验由本切片后续步骤完成。私有诊断不自动转换为正式后端资格，
Single 记录也不能改标签升级为 MoE。新 FLP、后台宿主渲染、GUI 作业接通和发布
仍保持阻断；旧精确变速、控制送达、字段和基准限制不变。
