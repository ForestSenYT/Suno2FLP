# FL26 控制事件：后台证据及精确写入阻塞

本批取得 **26.1.7.5654 的选定 Pattern 控制字段证据**。14 个独立后台进程均完成
新实验副本的 WAV 渲染，但中途变速仍不同于原始 MIDI 的精确时钟。没有生成真实歌曲
FLP，没有解除已有写入器限制。

## 实验与来源

本机发行包 `Shared/Python/Lib/midi.py` 声明速度 REC 地址为 `0x40000005`。
[API 作者的示例](https://il-group.github.io/FL-Studio-API-Stubs/midi_controller_scripting/midi/__rec_events/global%20properties/)
使用 BPM × 1000 的整数；Image-Line 的
[MIDI scripting 文档](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm)
说明 REC 接口。这些是运行时参数线索，本身不是文件格式或导入保存 API。

在独立正向参考的**新副本**中，向选定 Pattern 插入事件 223。每条实验记录的三个
小端 32 位字为位置、REC 地址和值。回读核对全部插入字节；删除第一批插入并恢复其
替换项后可恢复基准字节。第二批仅另行缩放已声明的 PPQ、音符/片段坐标或改变速度。
原参考和六个旧实验副本未修改。

| 对照 | 结果 | 结论边界 |
| --- | --- | --- |
| 120 BPM 标量 vs tick 0 的事件 120000 | PCM 全部相同 | 选定记录生效 |
| 60 BPM 标量 vs tick 0 的事件 60000 | PCM 全部相同 | 这个值按整数毫 BPM 工作 |
| 120.001 BPM 标量 vs tick 0 的事件 120001 | PCM 全部相同，且与 120 BPM 不同 | 支持这个 0.001 BPM 对照，不证明更细精度 |
| 120→60 重复渲染 | PCM 全部相同 | 可重复不等于时序正确 |
| 原生通道 0 音量值 0 | 静音 | 原生 REC 响应，不等于 MIDI CC7 |
| 原生通道 0 音量 12800→0 | 第二个音符不发声 | 选定中途音量事件生效 |

第二个音符位于第 2 拍；第一拍后把 120 BPM 改为 60 BPM，理想起点为 1.5 秒。
对 stereo 16-bit / 44100 Hz PCM，在持续超过 20ms 静音后寻找幅值大于 3 的首帧：

| 实验 | 理想起音帧 | 检测到的起音帧 |
| --- | --- | --- |
| 恒定 120 BPM，96/960 PPQ | 44100 | 两者均 44101 |
| 第一拍后 120→60，96 PPQ | 66150 | 65921，两次相同 |
| 同一切换，960 PPQ | 66150 | 66128 |
| 120→60→240，96/960 PPQ | 49612.5 | 49728 / 49625 |

检测含音源包络/阈值影响，但约 5.2ms / 0.5ms 的变速偏差明显超过恒速对照偏差。
这是音频起点证据，**不是内部调度的完整解码**；不归纳为“总是延后一 tick”，不移动
源事件抵消，不据总 WAV 长度推导歌曲时长。官方
[音频设置](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_audio.htm)
和[项目设置](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/songsettings_settings.htm)
说明 tick/PPQ 的作用，没有为本实验保证精确变速调度。

后台使用固定哈希及签名的 FL64 命令行导出；`WindowStyle Hidden` 不保证无窗口。
没有点击、键盘、鼠标、UI 自动化、脚本安装或设备设置修改。逐项修改、新文件哈希、
进程参数/退出码及输入前后身份只留本地。没有人工试听，旧缩放/另存/重开验收仍待办。

## 只读命令

```powershell
uv run suno2flp inspect-fl26-controls new-probe.flp --output controls.json
uv run suno2flp assess-midi-encoding performance-960.json --output encoding.json
uv run suno2flp verify-midi-encoding encoding.json
```

控制检查要求唯一、带 NUL 的精确版本及单个 FLdt；保留索引、偏移、Pattern、完整
payload、残缺尾部、三个原始字及有符号值投影，不当 float、不排序、不丢弃。只标注
实测的速度值/PPQ 组合和通道 0 音量；未知地址/值/PPQ、缺少 Pattern、越界位置或
残缺 payload 不获标记。字段匹配不能证明任意位置、模板或插件具有同样行为。
旧 inventory JSON、指纹及“不支持事件 223”诊断均保持不变。

编码评估先重放完整 performance 报告，重导入当前 MIDI 并重建 arrangement/时序。
报告保存输入身份/指纹，事件地址关联完整源快照。独占新 JSON，发布前后核对输入；
保存的评估可逐字段重新计算。命令不运行宿主，不写 FLP；成功退出仅表示分析/复核成功。
所有报告始终 timing/routing unverified、writer blocked、execution_allowed false。

## 精度与路由分析

保留精确微秒/拍和毫 BPM 分数。`hypothetical_nearest_millibpm` 仅为反事实分析：
在 60..240 BPM 内取最近整数，平局取较小整数；区间外返回 null，整曲模拟误差也为
null。区间取自实验端点，不表示区间内任意值通过验收，也不宣称区间外宿主不支持。

用 Fraction 分段累加 `(候选微秒/拍 − 原始微秒/拍) × 段长拍数`，记录有符号终点误差
及所有速度边界/结尾的最大绝对误差。固定段内速度时误差线性，边界可求该假设的最大
值。假设忽略宿主切换偏差，不能当渲染预测、容差或舍入授权。

私有歌曲 374 个有效速度全部无法精确表示成整数毫 BPM。假设取最近整数且切换理想，
终点误差约 +103.499µs（44100 Hz 下约 4.564 个采样）。这不为零，更不保证实际宿主
仅有该误差。源速度、全部事件和原时序未变。

路由按 `(source input, original MIDI channel)` 罗列需求，保留轨位置、事件索引、
delta/tick、原消息和精确时间。跨轨列表用源轨顺序，不自称唯一播放顺序；重复消息
不合并，同文件同通道跨轨同 tick 控制消息另列待评估组，不猜先后。无通道 SysEx
等单列。该分组只是需求目录，不分配音源/端口。

歌曲有 63 组输入/通道、66 次程序变更和 66 次末尾 CC7，跨来源复用通道 0..9，
也有同文件同通道的多轨消息。不能直接合到一个全局端口的同号通道，不能假定每轨
有独立程序状态；destination 全为 null/unverified。

只读核对预装 “All MIDI CC” 模板发现它声明版本 24.2.99.4720 和 Sampler，不是 FL26
MIDI Out 路由证据。未凭名称加载它或复制插件状态。官方
[MIDI Out 文档](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/MIDI%20Out.htm)
要求匹配端口/音源。原生音量响应不证明 CC7、bank/program、鼓通道或插件选择行为。
没有给整曲强配音色，没有省略末尾事件。

事件 223 的整数结构和选定地址已有后台证据；精确变速调度、原始速度可表示性、
目标音源及程序/CC 路由仍阻断。下一步需独立接收音源/端口证据及保留原始时钟的
编码方式。零长度音符、模板/crop/flag、依赖及试听门槛仍有效。默认合成测试不运行
宿主；没有新依赖，没有复制第三方实现。

本批新增 30 个合成单元用例，完整测试 804 通过、19 项明确跳过。代码/格式、严格类型、
源码包/wheel 构建及安装后的命令流程通过。独立代码审查未发现需修复问题；审查没有
替代宿主验收或独立重跑私有实测。跳过项为外部后端选择性测试及本机链接权限限制。
