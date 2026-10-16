# 可追溯的 pitched 音符评分

此功能比较**同一份已验证音频时钟**上的候选音符和显式参考注释，给后续模型基准提供
固定评分器。它不执行转写，不生成 MIDI／FLP，不推进作业的质量阶段，也不把已知
MIDI 自动当作录音的人工真值。当前尚未建立 24 片段基准、模型资格或单曲音乐验收。

## 固定规则

`pitched-note-exact-maximum-matching-v1` 使用最大基数一对一匹配。音符必须同时满足：

- MIDI 整数音高完全相同；目前不评估连续音高、弯音、人声滑音或鼓类别。
- 起音绝对误差 ≤50,000 微秒。
- 结束误差 ≤max(50,000 微秒, **参考音符**时长／5)。边界包含等号。

所有时间使用原音频起点上的非负有理数微秒 `{numerator, denominator}`，不舍入、
移动或对齐到节拍。音符有各自唯一 ID；同音同时间的重复音符保留为独立对象。
输入注释原顺序保留在快照中；匹配只在按 ID 排序的视图上执行。候选边按候选 ID
排序，参考 ID 顺序执行迭代式广度优先增广路径，匹配对按参考 ID 输出。
算法不优化匹配总误差；有多个最大匹配时按上述固定顺序选择，而不是逐次最近邻。

定义 TP 为成功匹配对数，P=TP／候选数，R=TP／参考数，F1=2TP／(候选数+参考数)。
输出约分后的精确分数。参考非空、候选为空时 P/R/F1 都为 0。没有参考文件时
`reference_unavailable`，参考文件没有音符时 `no_reference_notes`，两者指标都为
`null`，不能算完美分或混入有 pitched 真值的发布平均。

匹配概念参考 [mir_eval 的音符评估说明](https://mir-eval.readthedocs.io/latest/api/transcription.html)。
本项目实现独立算法，无 mir_eval 依赖；整数音高和精确分数边界不是其浮点／连续音高
接口的逐字节兼容保证。评分算法版本属于本项目，修改规则必须新版本并重做基准。

## 输入与来源

`NoteAnnotation` 的 JSON 字段：

| 字段 | 要求 |
| --- | --- |
| `schema_version` / `profile` | `1` / `pitched-note-annotation-v1`（可使用模型默认值） |
| `role` | `candidate` 或 `reference`，命令参数位置必须对应 |
| `origin` | 候选 `inferred_candidate`，参考 `declared_reference`；原创测试可用 `synthetic_fixture` |
| `method` | 1–1024 字符的产生／标注方法，不能用置信度代替准确率 |
| `provenance_files` | 1–32 份当前产生者／人工标注／合成说明文件的 `FileIdentity` |
| `decode_report` | 已完成的 PCM 或限定压缩解码 `decode.json` 的 `FileIdentity` |
| `source_audio` | 解码报告的原音频身份 |
| `sample_rate` / `channels` / `frames` | 与独立验证的解码来源完全一致，最长 600 秒 |
| `notes` | 最多 10,000 条：`id`、`pitch`、`onset_microseconds`、`offset_microseconds` |

`FileIdentity` 包含绝对 `path`、完整 `sha256`、`size_bytes` 和 `mtime_ns`。
可用现有 `capture_stream_input` 对当前文件建立身份，不能只填写文件名或占位哈希。
注释中的路径必须指向实际本地证据。音符 ID 为 1–96 个 ASCII 字母、数字、`_.-`；
pitch 为严格整数 0–127；起音非负，结束必须晚于起音，且不超过精确来源时长。
时间分子最多 128 位、分母最多 64 位。每个对象的未知字段和重复 JSON 键被拒绝。

例如一条音符记录（只示意音符，不是可独立评分的完整注释）：

```json
{"id":"voice-001","pitch":60,
 "onset_microseconds":{"numerator":0,"denominator":1},
 "offset_microseconds":{"numerator":1000000,"denominator":3}}
```

候选和参考必须绑定**同一个当前解码报告**及来源时钟，不能各自填近似秒数。
整数 PCM 会独立逆变换并核对每个原样本；压缩路径会检查固定运行时并重新执行原有
完整源／样本验证，FLAC 另有源 MD5，MP3 仍不宣称原始无压缩波形相等。
压缩路径需要先显式准备的合格解码运行时；评分器不会下载依赖或回退系统解码器。
该路径沿用压缩解码的多次有界验证，可能显著慢于纯匹配。

参考数据的许可、人工正确性和独立性仍需曲库审计。`origin`／说明文件不是认证，
不能证明参考确实正确，更不能把候选复制成参考来证明模型达标。报告始终保留
`annotation_truth_verified=false`、`model_qualification=not_assessed`、
`musical_correctness=not_proven_per_song`、`human_review=not_performed`、
`host_compatibility=unverified`、`writer_eligibility=blocked` 和 `execution_allowed=false`。

## 使用和重放

```powershell
uv run suno2flp score-pitched-notes D:\work\candidate.json --reference D:\work\reference.json --output D:\work\new-score.json
uv run suno2flp verify-note-score D:\work\new-score.json
# 无参考：仍生成显式无法评分的报告，退出 3
uv run suno2flp score-pitched-notes D:\work\candidate.json --output D:\work\new-unavailable.json
```

退出 0 表示生成／重放了有效的测量报告，**不表示分数达标或可交付**；低分同样是有效
测量。退出 3 表示没有参考或参考为空；退出 1 表示输入、身份、资源或证据错误。
本功能供研发基准使用，尚未添加到面向用户的 GUI，不要求普通用户编辑 JSON。

报告保存原注释快照、全部输入身份、PCM 身份、匹配／未匹配 ID 和精确误差，以及
当前评分模块、基础契约／文件工具和 Python 可执行文件／版本、Pydantic 版本。
`verify-note-score` 用当前注释、当前代码和独立解码验证重新计算整个报告；修改注释、
产生者文件、来源、PCM、结果或评分配方会使旧报告重放失败。解码的代码／运行时
变化也受其自身证据检查。更换安装位置／运行时后应生成新评分报告，不能复用旧身份。
重放使用同一固定匹配实现，独立性来自当前输入／解码检查和测试中的穷举图匹配预言机；
不宣称存在两套独立评分算法。

输出只允许新 JSON 文件，父目录须已存在，禁止链接／reparse 路径和后端树；
不覆盖任何输入或旧报告。输入身份在计算前后和发布前后检查。若发布后的检查失败，
失败候选可能保留，但命令失败，不能当作验收通过；再次使用必须新路径及完整重放。
这些是可信本地文件的快照和变化检测，不是防恶意并发修改的操作系统隔离。

## 资源与当前验收

注释 JSON ≤4MiB，报告／每份产生者证据 ≤16MiB；最多 200,000 条合格匹配边。
密集歧义超限、取消或匹配超过 300 秒明确失败，不返回截断匹配或部分分数。
300 秒是匹配阶段的合作式预算，解码验证沿用各自的有界阶段，不是整条命令总时限。
默认测试不需要 DAW、模型、网络或原生解码包；另有安装后原创 PCM／注释检查。
合成高分只能证明评分行为，不能算作模型成绩或 24 片段固定基准。

后续仍须补齐鼓类别／起音、节拍、分轨 SI-SDR 与对齐、曲库许可和三组拆分、固定模型
资格与校准、真实曲库及宿主／试听验收。[原质量门槛](superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
保持不变：有 pitched 真值片段 F1 各自 ≥0.70、每个固定子集宏平均 ≥0.80。
