# 桌面作业界面

当前已实现实际音频预检、整数 PCM WAV 解码及任务状态界面，完整音频转 FLP 仍未交付。
界面使用可选 `gui` 依赖，固定 `PySide6-Essentials==6.12.0`，只导入 QtCore、QtGui、
QtWidgets，不安装 Addons、模型、插件或后端。CLI 核心不依赖 Qt。

## 依赖依据及分发边界

[Qt 官方 PyPI 元数据](https://pypi.org/project/PySide6-Essentials/6.12.0/)
列出 Python >=3.10,<3.16 及 Windows x64／Linux x64 的 abi3 wheel，包含上述三个模块。
此项目 Python 下限仍为 3.11；实际导入、离屏运行及 CI 另行验证，不能由 wheel 标签
推断运行通过。版本与传递依赖／哈希由 `uv.lock` 固定。

PySide6 提供 LGPL／GPL／商业许可选项；所用 [QtCore](https://doc.qt.io/qt-6/qtcore-index.html#licenses-and-attributions)、
[QtGui](https://doc.qt.io/qt-6/qtgui-index.html#licenses-and-attributions)、
[QtWidgets](https://doc.qt.io/qt-6/qtwidgets-index.html#licenses)
官方模块页均列出 LGPLv3 选项及第三方归属。项目源代码的 MIT 许可不替代 Qt 的许可。
本阶段仅通过包管理器安装未修改的动态库并保留上游 notices，不将 Qt 二进制复制入
仓库或本项目 wheel。独立安装版须另验所有实际打包模块、对应源码／获取方式、许可与
归属文本、用户替换库及 LGPL 所需权利；未完成前不能宣布安装版可发布。

长 I/O 采用 Qt [线程池](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThreadPool.html)，
结果通过信号回到主线程。取消为安全边界请求，完整只读检查可能先结束，不强杀线程。
开发验证仅通过直接控制器调用及 offscreen 渲染，无桌面输入；实际交互验收仍待执行。

## 启动与使用

开发环境执行 `uv sync --locked --extra gui`，然后手动启动：

```powershell
uv run suno2flp-gui --jobs-root "D:\Suno2FLP-Jobs"
```

普通已安装 Python 包可选 `suno2flp[gui]`；该入口是研发预览，不是免 Python 的 Windows
安装版。开发依赖也固定相同 Qt，用于完整类型检查／测试；CLI-only 用户安装不含 Qt。
`--help` 不导入 Qt，不创建目录。正常启动读取所选目录的历史，不自动执行转换。
默认位置为启动目录下 `workspaces/audio-jobs`；可在左侧选择任务保存目录。

1. 选择音频，创建任务。每次使用新的独占子目录，原素材不变。
2. 开始检查／恢复，观察真实阶段。有效整数 PCM 完成音频检查和解码，再于分轨分离处阻断。
3. 核验来源与结果会重读文件、完整链、预检及[解码报告](AUDIO_DECODE.zh-CN.md)，
   将全部浮点样本恢复成源整数进行比较；成功仅表示当前证据一致。
4. 历史任务可重新载入。损坏／半写记录保持可见并阻断，不能从旧状态悄悄重跑。
   读取另一任务前会清空旧操作对象；若列表读取后文件损坏，也不会误操作上一任务。
5. 取消或关闭运行中的窗口会请求安全停止；当前读操作可能先结束，随后记录取消。
   已阻断／失败任务已经停止，保留原原因；修改源文件或完成产物后不能恢复。

耗时读取和环境检查均在窗口的单工作线程中执行。忙碌条只表示操作尚未返回，阶段
完成数来自真实记录，不是全曲进度估计。更换任务目录在运行时禁用，记录不会转存。
环境清单使用原有只读检查，找到 FL Studio 安装文件不等于启动、连接或验收通过。
原始身份、阶段记录、异常及当前产物路径保留在“来源与诊断”中。

Windows 离屏插件不会自动发现系统字体；初始化在其字体库为空时只读注册现有系统
微软雅黑／Segoe UI，不下载或打包字体。Linux 离屏检查使用可用系统字体；中文显示
需要系统安装中文字体，Windows 是本产品的交付平台。CI 记录字形可用性，不把截图
成功替代中文实际交互、宿主重开或试听验收。

Linux CI 实际复现 QtWidgets 导入缺少 `libEGL.so.1`；离屏模式仍需该共享库。
工作流仅在 Linux 临时 runner 从系统仓库安装 `libegl1`，并记录实际包版本；没有
跳过 GUI 测试或改变四个必需检查名称。[Qt Linux 依赖说明](https://doc.qt.io/qt-6/linux-requirements.html)
描述了图形系统依赖；此项是在当前 wheel／runner 上取得的实际运行前提，不是对
所有 Linux 桌面依赖的完整清单，也不在用户电脑安装系统库。

仍未实现：压缩音频解码／分离／转写 worker、自动 FLP、结果试听、质量问题定位、模型
准备及独立安装版。未实现阶段明确阻断，现有 MIDI 与宿主写入限制继续有效。
