---
name: short-drama-h3
description: 用于用户明确选择 H3 分段短剧工作流，或已有项目的 workflow_suite 为 short-drama-h3 时，初始化、继续项目、查询进度、协调创作阶段和导出资料。使用 SEG 段内多镜与五份 Markdown；普通短剧项目继续交给原 short-drama 套件。
license: MIT
---

# H3 分段短剧

基于文件与命令行管理项目。每集按需维护五份创作文档，已有实际素材后可增加《剪辑单.md》。不启动 Dashboard、展示服务或浏览器。完整职责见 [工作流](references/creator-workflow.md) 与 [分段契约](references/segmented-contract.md)。

## 路由与输入

| 当前请求 | owner 与输出 |
| --- | --- |
| 点子、改编、系列与分集 | `$short-drama-h3-develop`，按需开发 |
| 长篇原著分析 | `$short-drama-h3-novel-analyze`，可选分析工作区 |
| 单集写作或规范现成剧本 | `$short-drama-h3-write` → 剧本.md |
| 人物、造型、地点、道具、连续性 | `$short-drama-h3-assets` → 视觉设定.md |
| 人物、造型、地点、道具等资产图提示词 | `$short-drama-h3-image-prompts` → 图片提示词.md |
| 自然节拍分段、段内镜头、段首/段尾冻结关键帧 | `$short-drama-h3-storyboard` → 分镜.md |
| 中文 H3 六段式、实际视频参考绑定 | `$short-drama-h3-video-prompts` → 视频提示词.md |
| 图片生产、视频交接与结果归属 | `$short-drama-h3-produce`；视频执行使用外部 `$minimax-h3-comfyui-video` |
| 现有素材剪辑、字幕与成片 | `$short-drama-h3-edit` → 剪辑单.md 与实际成片 |
| 用户点名的审稿、结构或媒体检查 | `$short-drama-h3-review` |
| 初始化、状态、制作形态、导出 | 本技能 |

只读取当前请求的直接输入。可从现成剧本、视觉设定、分镜或实图直接进入相应阶段，不为流程补造文件。图片提示词与分镜是兄弟分支：冻结关键帧正文只保存在分镜.md；图片提示词.md 只保存资产图片配方，不复制 SEG 冻结正文。需要生产段首/段尾图时，生产任务直接从分镜 SEG 读取冻结正文，并独立绑定实际参考图。

分镜 owner 唯一拥有 SEG/SHOT 切分和时间，并在需要时保留 SEG 级「参考图占位」；视频 owner 拥有 MOTION 的实际参考选择、REF/PLAN 绑定与六段式。参考图占位描述需求和缺口，不回填分镜的「视觉依据」「图片提示词项」或真实输入路径。在用户授权的跨阶段范围内完成必要回修与下游刷新，不自动启动审查、归档或媒体生成。

## 初始化与模式

先看用户指定目录与现有 `short-drama.json`，运行命令时把 `{技能目录}` 换成本技能绝对路径：

```bash
python3 {技能目录}/scripts/project_tool.py init <project> --title "项目名" --language zh --aspect-ratio "9:16"
python3 {技能目录}/scripts/project_tool.py status <project>
```

示例画幅仅为语法示例，实际使用用户已确定的画幅。已确认的 `--prompt-language`、`--episode-count`、`--target-seconds` 同步写入；未知事实保留未决定。`init` 不预建五份空文档，不自动接受制作形态或参考方式。

初始化时还要确认项目的全局提示词风格；模板中的 `creator_authority.prompt_style.status` 初始为 `unset`。若用户已明确给出全项目主题，按 [项目全局提示词风格](references/project-prompt-style.md) 拆成视频母版、短风格锁、图片视觉锁和纯视觉负面词，并通过创作者决策流程接受后写入。图片、冻结关键帧和视频提示词都从该档案读取；不得默认将某个真人电影基线硬套给所有项目。主题未接受前可以继续不依赖风格的工作，但不能交接需要该风格的图像或视频提示词。

用户明确选择本套件后，通过原项目工具的发布、接受、`set-authority` 写入创作档案。将以下已获授权的选择写到临时输入 `输入/profile.jsonl`；`src: short-drama` 是兼容 locator，保留原拼写：

```jsonl
{"decision_id":"CD-H3","status":"accepted","target_locators":[{"src":"short-drama","field":"/creator_authority/production_profile/choices"}],"accepted_value":{"workflow_suite":"short-drama-h3","storyboard_unit":"video_segment","target_video_model":"minimax-h3","video_prompt_dialect":"minimax-h3-segmented","video_prompt_language":"zh","native_duration_seconds":{"min":4,"max":15},"audio_generation":"same_pass"}}
```

```bash
python3 {技能目录}/scripts/project_tool.py publish <project> --owner short-drama-h3 --artifact-id AR-PROFILE --output "创作者决策/production-profile.jsonl=输入/profile.jsonl"
python3 {技能目录}/scripts/project_tool.py accept <project> --artifact-id AR-PROFILE --decision accepted
python3 {技能目录}/scripts/project_tool.py set-authority <project> --field /creator_authority/production_profile/choices --decision-ref "创作者决策/production-profile.jsonl#CD-H3"
python3 {技能目录}/scripts/project_tool.py status <project>
```

修改已有档案时先读取并保留其它已接受选择，使用未占用的决策/产物 ID。已有旧 SHOT 项目不能只改档案就切换：用户明确要求迁移时先在副本转换与检查，再切换入口；本技能不要求原套件支持新模式。

新套件项目必须同时声明 `workflow_suite: short-drama-h3`、`storyboard_unit: video_segment`、中文分段方言。字段缺失、旧结构或混合结构需要明确报告，不能凭标题自动选模式。独立文档请求可先声明同样的创作选择，视频交接前补齐项目档案与画幅。

## 检查与导出

结构检查只作用于已有输入与点名范围，完整性和交接检查按 [分段契约](references/segmented-contract.md) 分层。未看真实图或视频时，不把结构结果称为质量通过。不会为查状态或导出要求生产素材。

```bash
python3 {技能目录}/scripts/creator_markdown_check.py <project>/剧集/EP001 --project-root <project>
python3 {技能目录}/scripts/project_tool.py export <project> --out <项目外目录>
```

导出已有五文档、可选剪辑单与制作成果；排除私有输入、凭据与隐藏运行状态。导出是当前内容快照，不代表审批或质量通过。安全写入见 [运行预检](references/runtime-preflight.md)。

## 按需知识

- 格式与所有权：[五文档](references/creator-documents.md)、[契约](references/contract-and-ownership.md)。
- 制作形态与可选试帧：[制作形态](references/production-form-profiles.md)、[Look Development](references/look-development.md)。
- 参考控制与信息边界：[参考角色](references/reference-roles.md)、[观众揭示](references/audience-reveal.md)、[补拍与替代](references/pickup-and-alternate.md)。
- 按问题检索方法：[规则索引](references/knowhow-index.md)。
- 维护来源、验证与暂缓能力：[迁移记录](references/migration-notes.md)。

视频生成只有用户点名时才交给 `minimax-h3-comfyui-video`，沿用当前有效授权并遵守适用的项目/工作区约定。本套件不复制视频工作流或执行器，不建立第二套视频确认账本。独立 TTS、时间线音乐生产的完整迁移，以及整集目标时长与未拍覆盖校验暂缓；不影响对白写作、H3 同次声音描述或使用已有声音素材剪辑。
