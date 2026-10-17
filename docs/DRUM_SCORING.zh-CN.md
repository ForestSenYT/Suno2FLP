# 鼓点类别与原时钟评分

这是开发用的条件评分工具，尚未接入鼓点模型或完整转换作业。
`score-drums` 比较用户声明的候选和参考，`verify-drum-score` 从当前原音频、
解码结果、标注和生产者文件重新计算。不会生成 MIDI、FLP 或调用 FL Studio。

```powershell
suno2flp score-drums candidate.json --reference reference.json --output new-score.json
suno2flp verify-drum-score new-score.json
```

不提供 `--reference` 时仍生成来源报告，状态 `reference_unavailable`、退出码3。
空参考为 `no_reference_events`、退出码3，precision/recall/F1 均不可用；
非空参考时退出码0仅表示已完成条件测量，分数可能为0。输入／校验错误退出码1。
报告及 `.pending.json` 名称必须全新；发布后两者均视为不可变，不能覆盖。

## 输入与单位

标注的 `profile=source-clock-drum-annotation-v1`、`schema_version=1`。
`role` 为 `candidate/reference`，`origin` 为
`inferred_candidate/declared_reference/synthetic_fixture`；来源不能和角色矛盾。
必须声明 `method`、当前 `decode_report/source_audio` 文件身份（绝对路径、SHA256、
大小、mtime）、1–32个 `provenance_files`，以及原音频 `frames/sample_rate/channels`。
验证器独立检查完整 PCM 数值或合格压缩音频解码证据，拒绝仅重新计算哈希的伪造 PCM。
生产者证据单文件不超过16MiB，标注不超过4MiB；超过预算明确失败。

`events` 按原声明顺序完整保存在报告快照中；每个事件为：

```json
{"id":"hit-1","label":"KD","microseconds":{"numerator":1000000,"denominator":3}}
```

`microseconds` 是从原音频采样0开始的精确非负微秒分数，必须严格小于原音频末尾。
不舍入到 tick、不移动源事件，也不接纳尾部 padding。分子／分母限制128／64位。
支持8–192kHz、1–2声道、最长600秒，每个标注最多20000个唯一ID。
没有 offset、音高或 MIDI velocity 字段，不为评分虚构鼓音符时长。

类别固定为 `CY_CR/CY_RD/HH_CHH/HH_OHH/KD/SD/TT_HFT/TT_HMT/TT_LMT`，
采用候选 IDM 的九类名称作为显式标签词表。没有别名合并、GM 映射、鼓组插件或
实际乐器识别。使用词表不表示已采用、运行或取得该模型的质量资格。

## 匹配与解释

`drum-class-onset-max-cardinality-50ms-v1` 按同类别、onset 误差≤50000微秒匹配，
一对一，重复时间的不同ID均计数。先按精确时间及ID排序，再配对最早可行事件；
统一对称容差下，该算法得到最大匹配数，排序后为线性时间，不展开稠密配对矩阵。
它不承诺在同样的匹配数下最小化误差；结果按参考ID／候选ID稳定排序。
报告保留每对精确误差、全部未匹配ID和输入快照。

非空参考时 `precision=TP/C`（C=0时记0）、`recall=TP/R`、`F1=2TP/(C+R)`，
以约分分数保存。不同类别在同一时刻仍算错；50000微秒之外任何有理数差都不匹配。
这是单片段事件汇总，尚未计算发布曲库的跨片段宏平均，不能据此宣布达到发布门槛。
无参考的单曲不生成虚构分数；空参考中的误报保留在候选和未匹配列表，不按满分处理。

`source-bound-drum-score-v1` 报告绑定完成路径，复制到别处会被重放检查拒绝。
重放完整核对当前输入、原时钟、生产者、解码依赖清单、评分源码／运行时、
匹配结果及限制字段。发布前再次核对见证文件，独占建立完成名；失败不会留下完成名。
可信标注本身仍是声明，未通过人工音乐真值认证。

固定状态为 `annotation_truth_verified=false`、`musical_correctness=not_proven_per_song`、
`human_review=not_performed`、`model_qualification=not_assessed`、
`host_compatibility=unverified`、`writer_eligibility=blocked`、`execution_allowed=false`。
不改变已有 estimated-arrangement-v1、严格 MIDI、精确变速、控制路由、crop/flag、
宿主、GUI 安装或发布验收门槛。下一步是独立审计鼓点模型运行时并取得真实推理证据，
再准备固定曲库、校准和发布保留集；本工具不授予这些资格。
