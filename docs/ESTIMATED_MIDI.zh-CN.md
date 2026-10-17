# 音频推断的可编辑 MIDI 候选

`export-estimated-midi` 把当前完整三声部和鼓生产者组合为新的可编辑 MIDI，供首首
真实歌曲的新 FLP 使用。它不重新运行模型、不读取既有 MIDI、不启动 FL Studio，
也不解除音乐质量或 FLP 写入限制。输出始终为 `unqualified_candidate`。

```powershell
uv run suno2flp export-estimated-midi D:\private\pitched\stem-transcription.json --drums D:\private\drums\drum-transcription.json --output D:\private\new-midi
uv run suno2flp verify-estimated-midi D:\private\new-midi\estimated-midi.json
```

可选 `--beats` 只沿用同来源节拍证据，不推断拍号或音乐速度。新目录必须不存在，
且不得与输入／生产者／后端重叠。输出为 `candidate.mid`、完整来源和时间审计
`estimated-midi.json`，以及保留的独占 pending 名称。失败可能保留新诊断文件，
没有完成 JSON 时不能视为成功；已有文件从不覆盖。

## 时间与完整性

- SMF Type1：一个技术时钟轨和 vocals／drums／bass／other 四轨，通道分别为
  0／9／1／2。轨道和每个推断音符／鼓事件的原索引、峰索引、完整输入快照均保留。
- 960 PPQ、每拍500000微秒是将音频秒数表示成 MIDI 的技术坐标；不是歌曲120BPM
  的音乐分析结论，不写入假定4/4拍号。所有既有 MIDI 导入／保真规则保持不变。
- 每个推断边界以精确有理数独立四舍五入，正好半 tick 时向上，保留原微秒、目标
  tick 和有符号微秒误差。每边界误差绝对值最多 `3125/12` 微秒。源尾部不足一采样
  的 padding 不裁剪；各轨保留共同原时长，并容纳明确派生的鼓触发尾部。
- 原始推断列表不排序或去重；MIDI 消息按时间确定性排列，同 tick 先释放再触发。
  同通道／音高的嵌套释放会导致 SMF FIFO 重配对，因此明确拒绝；正时长塌缩到0
  tick 也拒绝，不自动延长、删除或偷偷移动推断边界。

## 明确的预览选择

音符力度固定96，鼓触发时长固定50ms；两者都是预览渲染策略，不来自模型 activation、
鼓 velocity 数值或已知真实 note-off。推断 activation／logit／velocity 浮点位和原生
bend 文件地址在完整来源中保留，尚未渲染弯音，明确列入阻塞。

九类键号选择如下，是本软件的显式近似策略；不证明具体鼓音源、安装状态或实际
通道送达，也不更改上游 `drum-gm-routing-unavailable` 状态。

| 类别 | 键号 | 类别 | 键号 | 类别 | 键号 |
| --- | --- | --- | --- | --- | --- |
| CY_CR | 49 | CY_RD | 51 | HH_CHH | 42 |
| HH_OHH | 46 | KD | 36 | SD | 38 |
| TT_HFT | 43 | TT_HMT | 48 | TT_LMT | 47 |

不写 program、CC、pitchwheel，也不加载插件。General MIDI 的声音名称／兼容约定
不能证明某个本地接收器的音色或行为；参见 [MIDI Association](https://midi.org/general-midi-level-1)。
后续 FLP 必须另有明确可发声音源、独立路由和实际宿主验证。

## 验证和发布

导出从完整当前生产者重建含鼓编排，使用已有数值验证和调用内保留的完整重查。
同一次调用不额外生成编排报告再从头重读。冻结全部来源、投影和配方后独占写入
MIDI；独立解析器先核对整个 SMF 头／五轨边界、最多四字节的规范 VLQ、七位音符
数据、固定 meta 长度和最终空 EOT，再解码比对所有消息、通道、力度、tempo、尾部
和无额外字节，避免解码器正规化后隐藏非法负载；随后复核生产者、原生成员、代码／mido 来源及 MIDI 身份，再提交
完成名。取消或输入／输出变化会拒绝完成发布。既有／明显重叠输出先于昂贵来源
验证拒绝。配方记录完整 mido Python 源文件身份和版本，无新增运行依赖。

`verify-estimated-midi` 重新读取当前完整上游并重建全部派生字段，不只相信保存的
分数、哈希声明、status 或来源标签。移动报告、修改音符／力度／技术时钟、原生
额外成员、旧配方、追加 MIDI 消息或尾字节均拒绝。

CLI 退出0仅表示候选导出／当前结构验证完成。无逐音符真值成绩，模型尚未资格
认定、没有宿主或人工试听通过记录，`writer_eligibility=blocked`、
`execution_allowed=false`。此切片不生成 FLP、不完成整个用户作业；最终24片段／
6曲质量、真实新工程重开／渲染、GUI和安装发布条件继续有效。
