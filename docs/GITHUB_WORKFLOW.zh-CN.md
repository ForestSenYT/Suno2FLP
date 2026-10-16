# GitHub 分支与自动合并路线

`main` 保存通过代码检查的研发集成版本；可发布版本另按
[交付目标](superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
验收。代码合入不等于宿主、音频转写或音乐质量已经达标。

## 每个切片的流程

1. 读取目标、当前里程碑和阻塞证据，确认本次唯一可验收结果。
2. 从最新 `origin/main` 新建 `codex/<milestone>-<slice>`。不继续累积已经合并的旧 PR，
   不在 main 上实现，不把私有证据复制进分支。需要隔离时使用受管理工作区。
3. 行为变化用原创小型合成数据先复现失败，再实现；同步文档和溯源。
4. 按变更验证单元／集成、静态检查、类型和安装流程；宿主／真实素材仍只在本地。
5. 一次全新上下文的独立审查，绑定被审查的完整 head SHA，记录问题处置和未验证
   范围；不伪造批准状态。新增提交即使只有修复也使旧审查失效，需要复核新 head。
6. 推送当前切片并创建一个 PR，说明问题、结果、验证和保留限制。绑定里程碑或问题；
   只上传公开源代码、原创测试、配置与可分发文档。
7. 审查完成、无未解决问题、预期文件清单正确，且当前 head 的全部 CI 已完成通过、
   主线最新后，才用 `--match-head-commit` 执行 squash 自动合并，不提前排队等待。
   失败则修复并重跑；任何推送前先取消可能存在的自动合并，重新核对新 head。
8. 回读实际合并 SHA 和状态，再从新 main 开始下个切片；保留本地私有记录和旧实验。
   若命令未合入而留下待合并状态，立即取消自动合并并核对原因，不能留待审 head 排队。

当前每个任务可使用：

```powershell
git fetch origin main
git switch -c codex/m1-job-contracts origin/main
git push -u origin codex/m1-job-contracts
# 创建 PR 后，审查、当前提交所有 CI、主线与预期文件均通过，再执行：
gh pr merge <PR号> --auto --squash --match-head-commit <已核对的完整SHA>
```

示例名称不表示对应功能已经实现。所有写入和推送只发生在当前获授权的仓库。

## 已配置的 GitHub 门槛

- 仓库启用 `allow_auto_merge`。这不会替所有未来 PR 自动排队；每个 PR 在完成
  独立审查和文件核对后再启用，不能根据分支名前缀盲目合并外部内容。
- main 要求 PR、最新基线、线性历史及解决审查讨论，管理员也不能绕过。
- 必需检查固定到 GitHub Actions 应用 ID `15368`：
  `checks (windows-latest, 3.11)`、`checks (windows-latest, 3.14)`、
  `checks (ubuntu-latest, 3.11)`、`checks (ubuntu-latest, 3.14)`。
- 当前工作流同时响应 push 和 pull_request，所以一个 PR 提交通常有八项检查。
  四个不同的矩阵名称是服务器强制门槛；执行者另外确认当前 head 的所有检查均通过。
- 禁止 main 强推和删除；没有打开管理员 bypass，没有自动删除旧分支或实验记录。
- 目前只有一个 GitHub 维护身份，所需 GitHub approving review 数为 0，避免无法
  自我批准造成永久等待。独立代理审查是开发规则，尚未由专用 GitHub review check
  强制执行。不得把这描述为“服务器强制第二人审批”。若引入第二维护者再升级该门槛。

修改检查名称或工作流时，必须同时更新保护规则，先证明新检查真实存在，再切换
旧要求；不能留下永久等待的检查，也不能临时清空要求来合并。更新工作流或许可／
模型／写入门槛属于需重点审查的变更，不能以“纯配置”为由跳过验证。

## 初始整合记录

PR #1 长期累计 18 个提交、194 个公开文件，作为早期研发基线已合入 main，
squash 提交 `0cd221524524c85b18c87c57b3561bb15130f352`。其最后实现提交
`f3b592f2bca8ccb75f1c8a1223cac062cdb06565` 的八项 CI 全部通过，讨论列表为空，
本地对比确认 squash 后的文件树完全一致；私有文件不在这 194 个文件中。
原分支保留，不把该合并视为完整软件可用。

仓库自动合并开关先启用；第一版分支保护请求因并列使用旧／新检查参数被 GitHub
拒绝，PR #1 在八项已通过后先合并；随后改用单一检查配置完成保护并回读验证。
后续 PR 必须在保护生效后合并，不能把 PR #1 说成已受新规则保护的历史证据。
配置前后、失败请求和修正后的响应保存在本地忽略目录，未上传私有记录。

GitHub 参考：[自动合并](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository)、
[分支保护 API](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection)。
