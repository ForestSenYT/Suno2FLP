# 节拍与重拍分析（开发中）

当前接口提供固定后端准备、真实合成探针、完整来源绑定候选、全新推断重放、
条件参考评分和 CLI；共享作业、模型质量、
鼓类别、确定拍号、FLP 和最终交付门槛保持阻断。推断不改变已有 MIDI。

## 固定运行时

[Beat This!1.1.0](https://github.com/CPJKU/beat_this/tree/b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c)
提交 `b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c`；wheel 的 Python 源码对应此提交。
仅使用官方 final0 权重，SHA-256：
`8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331`。
19个本地 wheel 的地址、大小、哈希、notice、166个模型张量的形状／类型和完整
状态值哈希固定于 `integrations/beat_pins.json`，原始下载文件仍是运行前提。

Windows x64 CPython3.11.16，匹配 CPU Torch/Torchaudio2.11.0+cpu，NumPy1.26.4，
Soxr0.3.7；不修改核心依赖。独占准备不联网、不运行构建脚本／`.pth`。
读取时复核源归档、运行时、适配器及完整文件树，伪造清单哈希不能替换固定权重。
原生进程采用 `-I -S -B`、私有包／缓存、CPU8／1线程、float32、确定性算法、
最高矩阵乘法精度，禁用 CUDA/MKLDNN。只加载固定本地权重，要求
`weights_only=True`、安全 globals 和完整张量状态核对；不调用上游有联网回退的
checkpoint 或音频加载器。这是可信本地组件的完整性检查，不是恶意代码沙箱。

## 来源时钟和完整预测

源声道按顺序求 float64 均值，Soxr HQ 转为22050Hz，再显式转换 float32。
保留完整下混、重采样、模型输入、128频带谱、每块输入／两个 logits、合并 logits
及最终秒值。独立复核下混、转换、块输入／补零、边界裁去和 keep_first 合并；
模型／重采样／谱的真实性仍需全新原生重放，不能只重算哈希。

模型帧率50Hz、块长1500、两侧各6帧，尾块可能前移。峰值复核保留并列正峰、
相邻峰平均值和重拍对齐前后记录。平均值可能是半帧：11025Hz时半帧为 `441/4`
源样本、10000微秒。源坐标始终按精确分数 `模型帧×源采样率/50` 计算，不从
浮点秒值反推或取整；末端 padding 明示，禁止静默裁去或钳位。
重拍按上游 binary64 秒值的首次最小距离移至节拍并去重；无节拍时保持重拍原位。

## 探针与保留限制

`provision_beat_backend` 准备本地文件，`probe_beat_backend` 对静音、脉冲、反相双声道、
跨块长尾各启动两个独立原生进程，比较全部数组，保存请求／日志／完整输出、实际
模块／版本、进程时长和内存峰值。取消或最终完整性检查失败不发布完成标记。
默认测试不安装模型；真实测试须设置 `SUNO2FLP_BEAT_BACKEND`，缺前提明确跳过。

反相下混可抵消有声输入；静音或没有预测不代表质量通过。模型不提供拍号分母、
乐器角色或鼓类别，激活值不是校准置信度。进程峰值不是整个作业资源测量。
四种探针不能替代固定24片段／6首歌、保留集、稳定性、宿主重开／渲染和试听验收。

上游代码和发布权重适用 MIT；上游另说明训练音频有受限版权，代码许可不保证
训练／音乐数据权利。Soxr LGPL2.1+、tqdm MPL2.0/MIT 及依赖附带 notice 保留；
后端和模型不随应用包分发，不上传私有证据。

## 开发命令

```powershell
uv run suno2flp prepare-beat-backend --artifacts D:\Models\beat-artifacts --output D:\Models\beat-backend-new
uv run suno2flp probe-beat-backend D:\Models\beat-backend-new --output D:\Results\probe-new
uv run suno2flp analyze-beats D:\Results\decode\decode.json --backend D:\Models\beat-backend-new --output D:\Results\beats-new
uv run suno2flp verify-beat-analysis D:\Results\beats-new\beats.json --output D:\Results\replay-new
uv run suno2flp score-beats D:\Results\candidate-labels.json --reference D:\Results\reference-labels.json --output D:\Results\score-new.json
uv run suno2flp verify-beat-score D:\Results\score-new.json
```

所有输出均须新建。候选 JSON 保留全部来源、精确坐标、峰值和重拍对齐记录。
重放必须启动新的原生推断并逐一比较全部数组；保存的 receipt／成功布尔值不能
跳过推断。CLI 输出始终保留 `model_qualification=not_assessed` 和写入阻断。

评分输入是 `BeatAnnotation`，字段定义见 `core/beat_annotations.py`：显式
candidate/reference、来源声明／方法／证据文件、当前解码报告／原音频身份、源帧数／
采样率／声道，以及含唯一ID、beat/downbeat标签、精确分数微秒及 source/padding
域的事件。候选末端允许保留最多一帧模型 padding，不能丢弃后评分。参考超出源
时钟或来源不同均拒绝。标注证据只证明声明的当前文件，不能证明人工作业或标签正确，
也不能替代原生候选验证；报告明确 `annotation_truth_verified=false`。

相同标签以固定500ms诊断窗口做一对一匹配，先最大化数量，再最小化总绝对误差。
有序点上的精确动态规划保留所有重复事件ID、未匹配ID、precision/recall以及每对
误差。中位数使用中间值均值，P95使用最近秩；20/100/120ms误差应得到100/120ms，
不能通过收窄窗口隐藏较大误差。无参考、空参考、没有匹配时，未定义指标保持空值。
最多12000事件、400万匹配单元、60秒；超过预算明确拒绝，不裁去事件。
30ms中位数／80ms P95 发布门槛没有降低；这些条件指标不授予模型资格，也不替代
独立的鼓类别F1、固定曲库和完整交付验收。
