# M2：小型公开配对参考审计

2026-10-18。一手资料审计后，已通过有界 Range 取得 **BabySlakh v1 的一组公开配对
候选**，开展开发诊断。原始文件只读，未下载完整归档，也未分发这些数据。
它不能替代产品设计的 24 片段、6 曲、校准和发布保留集；
Single 试听失败和 MoE 音乐质量未验证的状态不变。

## 身份、许可与获取

官方 BabySlakh 是 Slakh2100 的 Track00001–Track00020，16kHz WAV，作者定位为
调试／原型数据。[v1 元数据][baby1]、[v2 元数据][baby2]。

| 固定记录 | 官方文件／字节数 | 上游 MD5 |
| --- | --- | --- |
| [4603844，v1 ZIP][zip] | `babyslakh_16k.zip`，882883087 | `ea1797fc57689a0e33c759c17a2292f5` |
| [4603870，v2 tar.gz][tar] | `babyslakh_16k.tar.gz`，882818115 | `311096dc2bde7d61c97e930edbfc7f78` |
| [4599666，redux][full] | `slakh2100_flac_redux.tar.gz`，104322767708 | `f4b71b6c45ac9b506f59788456b3f0c4` |

两个 BabySlakh 记录的 `metadata.license.id` 均为 **cc-by-4.0**；因此依据发布者声明，
可带署名作本地开发诊断。数据作者为 Ethan Manilow、Gordon Wichern、Prem Seetharaman、
Jonathan Le Roux；来源 DOI 为 `10.5281/zenodo.4603844`，许可
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。引用 Manilow 等 WASPAA 2019
《Cutting Music Source Separation Some Slakh》，并说明截取／重采样等修改。
这不证明基础歌曲全部权利、模型训练／商业分发或其他音乐素材获得一揽子授权。
上游未提供 SHA256；选择性获取无法核验整档 MD5，必须注明只核对成员 CRC、
大小及自行计算的 SHA256。[发布者许可][baby1]、[网站声明][site]。

实际获取：仅请求 ZIP 尾部／中央目录和选中成员，要求 HTTP206、精确
Content-Range／长度及 identity 编码；响应200须在读正文前关闭。中央目录固定
首个数字 track（Track00001），再按 metadata 固定首个 Piano（S02）。发现下述
flags 矛盾后保留异常，只取得条件诊断候选，没有把 flags 改成通过。
保留成员名、偏移、压缩／解压大小、CRC，限制总量并拒绝路径越界／重复成员。
取得 metadata、mix、S02 音频和 10 份 MIDI 的一次成功运行共传输 **12679847 字节**；
13 个成员均核对 CRC／大小并记录 SHA256。另保留最初探针因匹配 Mac 辅助元数据而
拒绝选择的失败记录。整档 MD5 **未核验**，不能冒称完整归档哈希通过。
早期 ZIP preview 读取曾被自动审批拒绝，原因是可能触发整档下载；未重试该接口，
后续严格 Range 路径已成功，响应200会在读取正文前停止。

## 标签与时序

官方布局为 `TrackXXXXX/{mix.flac,metadata.yaml,all_src.mid,MIDI/Sxx.mid,stems/Sxx.flac}`；
BabySlakh 改为16kHz WAV，具体归档前缀／成员仍须检查。**`MIDI/Sxx.mid` 才是
该 stem 实际合成输入**；`all_src.mid` 是原 Lakh，可能未经乐器特定音高修正，不能
直接当混音等价标签。须用 metadata 的 `audio_rendered`、`midi_saved`、`is_drum`、
`program_num` 配对，不能按来源顺序猜角色。[固定工具说明][utils]。

后续主代理取得的 Track00001 metadata 中，各源两个 flags 均为 false，而归档仍有
多数同名 WAV／MIDI；这是待解释的不一致，不可改写为 flags=true。固定生成源码
存在一个**可能解释、未经发布历史证实**的路径：L239–241重建 metadata 并先置false；
L265–267遇已存在 MIDI 直接跳过，未到L277–278置true，但L281–283仍写metadata；
随后L333–336遇已存在 WAV 直接跳过，未到L388置true及L392–393保存。重复运行默认
不重新渲染时可产生这种状态；本轮未找到作者对BabySlakh这份文件的明确确认。
因此文件存在、命名一致及源码可解释性不等于实际配对已获验证，须保留异常并独立
核查节目号、事件时钟、起音与尾部；主代理另记具体成员／采样检查。[初始化及跳过][flags]、
[渲染跳过及保存][render-flags]。

原 Slakh 为44.1kHz／16bit／mono；部分音色含混响／压缩，mix 是归一化 stems
求和。固定生成脚本保留原 PrettyMIDI 时间对象、逐源保存，经规则修改音高，
渲染到原 MIDI 结束后5秒。故音频衰减尾音不等于 MIDI note-off，不能用固定 BPM
替代 MIDI tempo map，也不能把音色起音延迟吸收到“修正真值”中。[生成脚本][render]。
BabySlakh 降采样已损失高频，重采样滤波／量化和 stem 求和误差需实测；支持脚本
复制 MIDI／metadata 并分别重采样 mix／stems，但记录没有证明该版本实际使用的
精确滤波器和软件版本，不能预先保证逐采样对齐。[支持脚本][resample]。

固定 YourMT3 的 `midi2note` 默认处理 CC64、10ms 量化、同音重叠裁剪及最短
offset 修复；直接调用会改变标签。诊断须保留原事件／tempo／CC，并分别明确
key-release 与 sustain 延音口径；鼓以 onset 单独评分，不把混响尾部当 note offset。
[固定源码][parser]；本地对应文件 SHA256 为
`5b8cb566bb47a2c94c171d507a071057a5434f944f8a2f4f05f4ab3b1245992f`。

## 重叠限制与下一步

YourMT3+ 作者论文训练集包含 Slakh；固定 Space 的 `all_cross_v7` 包含 `slakh`，
其 train/validation/test 分开，另有合并 train+validation 的 `slakh_final`。
这证明存在训练分布重叠风险，**不能单凭权重文件名认定具体训练成员**。
BabySlakh 来自最初20曲，当前没有与固定权重训练 manifest 逐项比对；原 Slakh
还曾跨 split 重复 MIDI，redux 才移除重复。[作者论文][paper]、[固定配置][presets]、
[重复说明][utils]。本轮全部命名为开发诊断，不称未见／保留集。

官网演示仓库固定提交 `bc84207152469a207aa998d9460d9f7ac49c96a9` 仅提供
8个 MP3，无匹配 MIDI／stems，不能用来评分。[完整树][demo]。
配对归档路线已足够，暂不扩大数据集搜索。获取后先核验布局、真实事件时钟、
采样数／静音／尾部与角色，再固定有音符的短片段，对原 mix 和单 piano stem
运行同一固定 MoE；分开报告 pitch+onset、onset+offset、乐器归类与错误类型，
由标签评分和试听共同决定下一修复，不以覆盖、EOS 或音符数代替准确率。

## Bass 八度口径的一手源码发现

固定 Space 的 `preprocess_slakh.py` L64／L130默认 `fix_bass_octave=True`；
L97–103对0起算节目32–39执行 `note.pitch -= 12`，唯一例外为
`scarbee_jay_bass_slap_both.nkm`；L138明确声明 Slakh bass 标签高一个八度。
Track00001 S03 的 `scarbee_rickenbacker_bass_palm_muted.nkm` 不在例外。
[固定预处理源码][bass-preprocess]。Slakh 固定 `midi_rules/pitch.json` L9–12
启用 Bass `shift_all_notes:12`；`midi_inst_rules.py` L82–92以原起止／力度构造
pitch+shift 的音符，生成器L269–275先应用规则再保存供渲染的stem MIDI。
[生成规则][bass-rule]、[规则实现][bass-impl]、[保存与渲染][render]。
这些源码支持“原渲染 MIDI 与作者训练标签存在八度口径差”的解释；未检查／执行
Kontakt patch 的实际发声音高，不能证明每个候选音符正确，也不自动变更原MIDI
或主评分。应原样保留结果，把该假设与后续独立音高核验分开记录。

## 本地固定诊断口径

Track00001 的 mix 与 S02 均为16kHz、单声道、16bit PCM、3864916帧，时长
241.55725秒；13份所选文件的大小／CRC／SHA256已核对。S02 MIDI 的唯一节目为1，
符合 metadata 的 Bright Acoustic Piano；401个原始音符，无CC64或pitchwheel。
最早 MIDI 起音2.999624秒，音频首个非零采样在2.9969375秒；这只是起点检查，
不足以证明全部配对或逐音延迟，未移动任何事件以消除差值。

模型运行前固定两个新60秒片段：分别原样复制 piano 与 mix 的前960000帧，
逐样本核对来源前缀，不归一化、不改音符或音高。观察区间固定为[5,20)、[30,45)秒，
选择区间内起音并保留完整结束时间；选中结束超出60秒则拒绝评分。模型保留连续
60秒上下文及所有13通道／生成记录；这些不是完整241秒曲目的模型结果。
参考由本项目 MIDI importer 与原 tempo map 精确换算，采用按键释放时间，
不调用作者会量化／延音／裁剪的默认 MIDI 预处理。钢琴参考分别有44、18个起音。
混音参考保留9份非鼓实际 MIDI 的同音重复；pitchwheel、控制和乐器混淆另列限制。

原始结束时间参与现有 pitch+onset+offset 评分。另行标注的 onset-only 开发测量
在两侧副本中都用相同60秒结束值，仅消除 offset 条件；它不替换原注释或事件，
也不能冒充产品要求的完整音符F1。钢琴分别查看全部 pitched 输出和模型 Piano
通道，混音查看全部 pitched 输出；鼓和弯音未获得本轮评分资格。
报告始终保持 `annotation_truth_verified=false`、`model_qualification=not_assessed`、
`writer_eligibility=blocked`。当前用户歌曲的10份 MIDI 虽然结束时间接近音频，
仍没有独立对齐／正确性证据，不被自动提升为真实音符标签。

## 实测结果与限制

同一固定 MoE 后端各运行一次，钢琴约231秒、混音约244秒；各30个连续窗口，
所有生成流结束，全部13通道经独立词元重放核对。下表是**原渲染 MIDI 口径的条件
比较**，不是该用户歌曲、保留集或发布成绩。钢琴两种输出视图在这两段结果相同。

| 输入／原参考 | 秒区间 | 参考／候选数 | 完整音符TP | onset-only F1 | 完整音符F1 |
| --- | --- | --- | --- | --- | --- |
| 单钢琴／S02 | 5–20 | 44／42 | 41 | 0.9767 | 0.9535 |
| 单钢琴／S02 | 30–45 | 18／17 | 16 | 0.9714 | 0.9143 |
| 混音／9份非鼓MIDI | 5–20 | 116／111 | 74 | 0.7401 | 0.6520 |
| 混音／9份非鼓MIDI | 30–45 | 95／89 | 51 | 0.7391 | 0.5543 |

事后按起音单独配对 S03 与模型 Bass 通道：第一段22对均相差−12半音；第二段
20对有19对相差−12、1对相差−3。另有界取得 S03 音频（含目录请求共5413393字节），
原样分析三个250ms稳定窗口；参考音高减12对应周期的最大归一化自相关分别为
0.99994、0.99975、0.99991，而原渲染 MIDI 音高对应周期为负值。这支持本样本的
八度口径解释，不能证明整曲逐音正确，实际插件未启动。

据上述固定作者规则，**另建**“YourMT3 Slakh Bass 标签口径”参考：仅本曲S03、
节目33、已核对的非例外patch，将22／21条参考标签减12；各条保留 before/after
音高、相同起止和顺序。原MIDI、原注释、原低分和模型结果全部保留。新条件比较的
完整音符TP为96／68、F1为 **0.8458／0.7391**。这是源码及局部波形支持的
事后标签视图，不是修正模型输出，更不是所有Bass都应转调的产品规则。

两份60秒模型候选、8份完整音符评分（含重复钢琴通道视图和独立Bass口径）均完成
当前来源检查／报告重放。评分器合成回归53通过、1项因系统符号链接权限跳过。
应用行为未变，数据、模型、后端和原始输出均留在忽略目录；仅发布本研究和状态文档。
当前优先继续定位复杂混音的音符结束、残留识别错误和角色混淆；Bass口径变化使
原低分不能直接全部归因于模型。Single的用户否决、MoE单曲听验未确认、24片段／6曲、
精确MIDI、路由、宿主、GUI与安装门槛继续保留，没有生成新FLP或授予发布资格。

[baby1]: https://zenodo.org/api/records/4603844
[baby2]: https://zenodo.org/api/records/4603870
[zip]: https://zenodo.org/records/4603844/files/babyslakh_16k.zip
[tar]: https://zenodo.org/records/4603870/files/babyslakh_16k.tar.gz
[full]: https://zenodo.org/api/records/4599666
[site]: https://www.slakh.com/#license
[utils]: https://github.com/ethman/slakh-utils/blob/3f62d6a4b0e5952237dd5178ac3513e42161ec0a/README.md
[render]: https://github.com/ethman/slakh-generation/blob/e6454eb57a3683b99cdd16695fe652f83b75bb14/render_by_instrument.py
[flags]: https://github.com/ethman/slakh-generation/blob/e6454eb57a3683b99cdd16695fe652f83b75bb14/render_by_instrument.py#L239
[render-flags]: https://github.com/ethman/slakh-generation/blob/e6454eb57a3683b99cdd16695fe652f83b75bb14/render_by_instrument.py#L333
[resample]: https://github.com/ethman/slakh-utils/blob/3f62d6a4b0e5952237dd5178ac3513e42161ec0a/resampling/resample.py
[parser]: https://huggingface.co/spaces/mimbres/YourMT3/blob/5e66c1ea173a8186e0d20432b841d3180cc015b5/amt/src/utils/midi.py
[presets]: https://huggingface.co/spaces/mimbres/YourMT3/blob/5e66c1ea173a8186e0d20432b841d3180cc015b5/amt/src/config/data_presets.py
[paper]: https://arxiv.org/html/2407.04822v3
[demo]: https://api.github.com/repos/ethman/Slakh/git/trees/bc84207152469a207aa998d9460d9f7ac49c96a9?recursive=1
[bass-preprocess]: https://huggingface.co/spaces/mimbres/YourMT3/blob/5e66c1ea173a8186e0d20432b841d3180cc015b5/amt/src/utils/preprocess/preprocess_slakh.py#L97
[bass-rule]: https://github.com/ethman/slakh-generation/blob/e6454eb57a3683b99cdd16695fe652f83b75bb14/midi_rules/pitch.json#L9
[bass-impl]: https://github.com/ethman/slakh-generation/blob/e6454eb57a3683b99cdd16695fe652f83b75bb14/midi_inst_rules.py#L82
