# 在 FL Studio 中创建独立参考工程

目的：得到你亲自在 FL Studio 26.1.7（build 5654）中制作、能够确认音符长度和
播放位置的小工程，用来对照读取结果。它是新的测试参考，不是现有歌曲，也不会上传
GitHub。原文件 `templates/user-minimal.flp` 保持不变，不用它另存改造。

## 创建步骤

1. **从空工程开始。** 在 `File → New from template` 中选 `Minimal` 类别下的空模板
   （若有 `Empty`，选它）。不要打开或覆盖 `user-minimal.flp`。菜单名称若不同，选择
   不带鼓组和效果器的空模板，并记下实际模板名称。官方说明确认新建使用所选模板：
   [File 菜单](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/menu_file.htm)。
2. **设置时间。** 顶部速度设为 **120 BPM**；打开工程设置，确认 **4/4、Timebase / PPQ = 96**，
   在输入音符前设置好。默认 PPQ 通常为 96，但请查看实际值。
   [工程时间设置](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/songsettings_settings.htm)。
3. **只保留一个乐器。** 在 Channel Rack 添加 **3x Osc**；若空模板带有其他通道，
   只在这个新工程中移除多余通道。使用默认音色，不添加采样、第三方插件或混音效果。
   [添加乐器及打开钢琴卷帘](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/channelrack.htm)，
   [3x Osc](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/3x%20Osc.htm)。
4. **在 Piano roll 画音符。** 右键该乐器通道 → `Piano roll`。使用普通画笔和拍网格，
   在同一个 `Pattern 1` 的第一小节画下表两个有长度的横条。拖动音符右边缘，保证每个
   音符占一拍。不要通过 Channel Rack 的步进按钮输入，也不要启用滑音、连音或自动化。
   [音符绘制与长度调整](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/pianoroll.htm)。

| 音符 | 界面音高标签 | 开始位置 | 长度 | PPQ 96 时的开始/长度 ticks |
| --- | --- | --- | --- | --- |
| 第一个 | C5 | 第 1 小节第 1 拍 | 1 拍 | 0 / 96 |
| 第二个 | E5 | 第 1 小节第 3 拍 | 1 拍 | 192 / 96 |

两个音符的力度保持相同且大于零，记录界面实际显示的值即可。八度编号和力度百分比
只作为界面观察，不能凭它们猜二进制 MIDI 编号或原始力度字节。

5. **放入 Playlist。** 从左侧 Pattern 列表把 `Pattern 1` 放到 `Track 1` 的第 1 小节
   开头，只放一份。不要裁切、拉伸、循环、叠加或修改片段左右边缘；记录自然显示的
   结束位置。不要新增其他 Pattern、Automation clip 或 Audio clip。
   [播放列表与放置片段](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/playlist.htm)。
6. **试听并另存为新文件。** 切到 `SONG` 模式，确认能听到两个音符。使用
   `File → Save as`（`Ctrl+Shift+S`）保存为：

   ```text
   D:\Git\Suno2FLP\templates\user-reference-fl26-positive-v1.flp
   ```

   这是新的参考文件名，不能选择原始文件。格式选 FL Studio project（`.flp`），
   不用 ZIP、音频或模板导出。[另存为说明](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/menu_file.htm)。
7. **重新打开这个新文件检查。** 确认版本、120 BPM、两条音符、一个片段，以及
   没有缺失乐器/采样提示。记录实际结果；若无法重新打开或出现提示，保留文件并记录
   原因，不要把“已经保存”当成验收通过。

## 保留哪些观察

保留版本/拍号/PPQ、Piano roll 和 Playlist 的画面或文字记录；写明实际乐器名、
音符标签、位置/长度/力度、片段位置和试听结果。不要填写未观察过的“已验证”声明。
这些内容和 `.flp` 均留在本地，不添加到 PR。

新文件保存好后，告知本地路径即可继续只读检查；无需上传到 GitHub。读取器会计算
文件哈希并对照上述观察，保留真实字节、裁剪值和插件声明。**新参考工程不保证自动
具备写入资格**：若默认属性、裁剪、未知事件或其他门槛仍不满足，会继续阻断，不能
靠清零原始字节或伪造宿主声明通过。

## 已完成的本地对照与下一步

已通过 FL Studio 界面创建、保存并重新打开上述独立参考，核对了 120 BPM、4/4、
PPQ 96、两条正时长音符和一个片段。播放时观察到主输出电平，但没有采集或听取本机
声音，因此不填写“试听通过”。软件包本身仍不自动控制 DAW 或加载插件。

随后通过界面分别新存左裁一拍、再右裁一拍、仅开启第一个音符 Slide 的三个本地副本。
原工程和基准参考均未改动。确认普通音符的标记为 `0x4000`，Slide 对照为 `0x4008`；
Pattern 裁剪端点按整数读取与界面一致，依次为 `96/384`、`96/288` ticks。
完整证据范围、原始字段保留和测试见 [FL26 字段对照](FL26_FIELD_EVIDENCE.md)。

受限写入器只新增对完整匹配普通音符属性组合的原样保留；滑音、未知组合继续阻断。
默认 `ffffffff` 裁剪形式和显式裁剪端点仍没有获得写入资格，不能清零或直接改写。
原始工程与新参考仍受未知事件、片段属性、裁剪和完整宿主验收等门槛阻断；下一步需要
继续逐项验证这些字段和新输出行为。所有私有工程、记录和后端文件仅留在本地。
