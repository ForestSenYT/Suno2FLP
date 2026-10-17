# Windows 音频输出的只读前提检查

`inspect-windows-audio` 查询 Windows 输出端点和三个默认设备角色，保存完整证据。
它不启动 FL Studio、不打开音频流、不改变设备／注册表／驱动，也不授权 FLP 写入。
目前只有独立诊断命令；共享作业、完整 GUI 和宿主生命周期尚未接通。

```powershell
uv run suno2flp inspect-windows-audio --output diagnostics/audio-001
```

父目录须已存在，输出目录必须是新路径。启动前独占保存 `request.json`，记录完整命令、
代码／解释器身份和资源上限。保留 `stdout.bin`、`stderr.bin`、
`inspection.pending.json` 和独占发布的 `inspection.json`；失败尽可能留下原始流与
`failure.json`，其中保留原请求和原始流身份，不会发布完成名。不能覆盖、使用链接或把
输出放进后端目录；输出超过上限时只保留限额内诊断并明确失败，不截断后报告成功。

| 结果 | 退出码 | 含义 |
| --- | --- | --- |
| `output_detected` | 0 | 观察期间检测到活动输出及至少一个有效默认角色 |
| `output_absent` | 2 | 观察期间没有活动输出 |
| `default_absent` | 2 | 有活动输出，但三个默认角色均未找到设备 |
| 发现失败 | 1 | 平台、运行时、API、完整性、路径或资源前提不满足；不能解释成设备缺失 |

所有结果均保持 `host_compatibility=unverified`、`execution_allowed=false`。
有效期仅为 `observed_interval_only`；保存报告不是当前硬件状态证明。以后启动宿主的
服务必须重新取得当前证据，并继续独立验证正常退出、完整音频、重开／另存和试听。
这里的设备检查不能代替其他 ASIO 驱动或音源的资格验证。

## 接口、运行时与溯源

原生接口固定为 `IMMDeviceEnumerator` 的 IID
`A95664D2-9614-4F35-A746-DE8DB63617E6`。只使用输出方向的
`EnumAudioEndpoints`、`GetDefaultAudioEndpoint`、`IMMDevice.GetId/GetState` 和 COM
生命周期；不调用 `IMMDevice.Activate`、通知订阅或设备修改接口。
实现是本项目原创 Python 互操作代码，没有复制或分发微软实现。

单独的 `-I -S -B -X utf8` 标准库子进程只支持 Windows x64、普通 CPython
3.11.16／3.14.7。当前调用限制为15秒、合并标准流4MiB、最多256个完整端点；超过限制
显式失败，不截断后返回成功。取消只结束本次拥有的子进程。默认测试使用原创假接口，
真实只读集成测试须显式设置 `SUNO2FLP_TEST_WINDOWS_AUDIO=1`。

报告保留全部端点原始 ID／状态、三个角色 HRESULT、精确观察时间区间、Windows
版本、实际解释器和代码身份，以及已加载 `kernel32.dll`、`ole32.dll`、`MMDevApi.dll`
对应系统文件的 SHA-256／大小／修改时间。系统文件必须来自 Windows System32，
发布前重查身份。它们是所选 API 文件证据，不是完整 OS／驱动依赖闭包或全部映射内存
认证；Windows 更新后的指纹不能由旧报告代替。运行时隔离不是 OS 安全沙箱。

只接受四种已定义端点状态，拒绝重复 ID、缺少／重复角色、伪造的活动默认设备及
不支持的 HRESULT。`E_NOTFOUND` 与访问失败等 API 错误分开；设备在查询期间变化导致
不一致时失败，应在环境稳定后创建新观察，不改写旧报告。
微软说明：[设备状态](https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-state-xxx-constants)、
[默认输出](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-immdeviceenumerator-getdefaultaudioendpoint)、
[接口定义](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nn-mmdeviceapi-immdeviceenumerator)。

## 当前 FL26 调查结论

固定宿主26.1.7.5654上的新 MIDI Out/LSD 基准及独立3xOsc正向参考，都在60秒内未形成
有效音频，结束时仅有80字节 WAV；每次只终止拥有的进程且无残留。相同输入曾有有效
历史渲染，所以不能仅凭当前失败归因于输入、某个 MIDI 通道或某个插件。
另外一次10秒线程快照在采集后主动结束，不计为正常退出或成功渲染。

新旧启动日志中的 ASIO 参数相同；失败日志没有启动完成标记。独立只读注册表观察及
真实 Core Audio 握手均发现16个已登记输出、0个活动输出，三个默认查询均为
`0x80070490`。这是已确认的环境缺口；它与停滞的因果关系仍需在设备恢复后，以相同
字节、参数和新副本取得正常退出及独立全音频对照。没有延长超时来算成功。

当前不再盲目启动宿主。需要用户接通耳机、音箱或显示器音频；实际 API 确认活动输出
后才继续新的对照。没有自动切换驱动、修改全局设置、安装虚拟声卡或通过界面输入
处理等待。原先精确变速、63组接收路由、crop/flag、另存／重开及听验限制仍保留。

原始素材、模板、基准和旧实验继续保持原样；新副本、启动日志、有限线程转储、设备
ID及完整本地实验记录只留在忽略目录，不进入 Git、wheel 或源码包。
