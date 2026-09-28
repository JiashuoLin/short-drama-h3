# short-drama-h3

面向 Codex 的 H3 分段短剧创作技能。它把短剧项目按文件和命令行组织成可追溯的创作链：剧本、视觉设定、图片提示词、分镜和视频提示词，并以 `SEG`（视频段）、`SHOT`（段内镜头）和 `MOTION`（视频交接单）保持各阶段的边界。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> English summary: `short-drama-h3` is a filesystem-first Codex skill for segmented short-drama production. It provides routing, project contracts, Markdown validation, project state, and export helpers for H3-style video segments.

## 这套技能解决什么问题

- 将每个视频段作为唯一生产单位：一个 `SEG` 对应一个 `MOTION` 和一次逻辑视频生成请求。
- 用五份按需维护的 Markdown 文档承载创作事实，避免在不同阶段复制出互相冲突的版本。
- 明确 owner：剧本、资产、分镜、图片提示词、视频提示词和剪辑各自有唯一修改方。
- 提供离线项目工具、结构检查、完整性检查和导出命令，方便在 Git 中审阅和回溯。
- 保持视频执行边界：本仓库不复制 ComfyUI 工作流或视频 runner；视频生产交接给外部的 `minimax-h3-comfyui-video` 技能。

## 工作流路由

| 请求 | 负责阶段 | 主要输出 |
| --- | --- | --- |
| 点子、改编、系列与分集 | `short-drama-h3-develop` | 开发资料 |
| 长篇原著分析 | `short-drama-h3-novel-analyze` | 原著分析 |
| 单集写作或现成剧本规范化 | `short-drama-h3-write` | `剧本.md` |
| 人物、造型、地点、道具与连续性 | `short-drama-h3-assets` | `视觉设定.md` |
| 资产图提示词 | `short-drama-h3-image-prompts` | `图片提示词.md` |
| 自然节拍分段、段内镜头与冻结帧 | `short-drama-h3-storyboard` | `分镜.md` |
| H3 六段式视频提示词 | `short-drama-h3-video-prompts` | `视频提示词.md` |
| 图片生产、视频交接和结果归属 | `short-drama-h3-produce` | 生产记录 |
| 素材剪辑、字幕与成片 | `short-drama-h3-edit` | `剪辑单.md` 与成片 |
| 审稿、结构或媒体检查 | `short-drama-h3-review` | 审查记录 |

## 安装

将仓库目录复制到 Codex 的 skills 目录，并保留目录名 `short-drama-h3`：

```bash
git clone https://github.com/JiashuoLin/short-drama-h3.git
mkdir -p ~/.codex/skills
cp -R short-drama-h3 ~/.codex/skills/short-drama-h3
```

在支持 Codex skills 的环境中使用 `$short-drama-h3`。各子阶段的 skill 名称、参考资料和脚本都在仓库中，路径按当前安装位置解析，不依赖本机绝对路径。

## 快速开始

### 1. 初始化项目

```bash
python3 ~/.codex/skills/short-drama-h3/scripts/project_tool.py init ./my-project \
  --title "我的 H3 短剧" \
  --language zh \
  --aspect-ratio "9:16"
```

`init` 只建立项目状态，不预建空的五份创作文档。画幅、集数、目标时长和提示词语言应以创作者已确认的选择为准。

### 2. 声明 H3 制作形态

在项目的临时输入中写入已接受的生产选择，再使用项目工具发布、接受并写入 authority。最小选择见 `SKILL.md` 的“初始化与模式”一节；核心字段包括：

- `workflow_suite: short-drama-h3`
- `storyboard_unit: video_segment`
- `target_video_model: minimax-h3`
- 中文分段提示词方言
- 原生段长 4–15 秒

### 3. 运行离线检查

```bash
python3 ~/.codex/skills/short-drama-h3/scripts/creator_markdown_check.py \
  ./my-project/剧集/EP001 \
  --project-root ./my-project \
  --level structure
```

检查结果只说明 Markdown 结构和引用是否满足契约，不代表图片或视频的媒体质量通过。

### 4. 查看状态与导出

```bash
python3 ~/.codex/skills/short-drama-h3/scripts/project_tool.py status ./my-project
python3 ~/.codex/skills/short-drama-h3/scripts/project_tool.py export ./my-project --out ./handoff
```

导出是当前内容快照，会排除私有输入、凭据和隐藏运行状态。

## 核心契约

- `SEG` 是计划生成单位；一个 `SEG` 可以包含多个 `SHOT`。
- `SHOT` 只描述段内切镜和时间，不拥有独立视频 job、参考图或视频提示词。
- `MOTION` 只在 `视频提示词.md` 中建立，负责实际参考图选择、六段式提示词和视频交接状态。
- `分镜.md` 唯一拥有 `SEG/SHOT` 切分、计划时长和段首/段尾冻结正文。
- `图片提示词.md` 保存资产图片配方，不复制分镜中的冻结正文。
- 真实参考图、视频和音频路径必须来自项目中的实际素材；缺失时记录缺口，不伪造路径。

完整规则请阅读：

- [SKILL.md](SKILL.md)：路由、初始化、检查与导出入口
- [分段共同契约](references/segmented-contract.md)：SEG、SHOT、MOTION 和参考图边界
- [创作者工作流](references/creator-workflow.md)：阶段顺序、owner 和变更回传
- [五份创作文档](references/creator-documents.md)：每集文档的职责
- [运行预检](references/runtime-preflight.md)：安全写入与运行约束

## 仓库结构

```text
SKILL.md
agents/openai.yaml
assets/                  # 决策、观察记录与项目模板示例
references/              # 契约、工作流、风格卡和迁移说明
scripts/project_tool.py  # 项目初始化、状态、发布、接受与导出
scripts/creator_markdown_check.py
scripts/validate_installation.py
scripts/selftest.py
scripts/test_h3_contract.py
scripts/test_project_h3.py
```

## 验证安装

在仓库根目录运行：

```bash
python3 scripts/validate_installation.py
python3 scripts/selftest.py
python3 scripts/test_h3_contract.py
python3 scripts/test_project_h3.py
```

这些脚本只使用本地文件和 Python 标准库，不会启动 Dashboard、展示服务或浏览器。

## 视频生产边界

当用户明确要求生成视频时，按项目授权把已准备好的 `MOTION` 交给外部 `minimax-h3-comfyui-video` 技能。该外部技能负责工作流预检、上传、提交、等待、超时恢复和输出选择；本仓库不建立第二套执行器，也不替代外部视频工作流的参数约定。

## 贡献

欢迎提交问题、契约修订和可复现的结构检查改进。请：

1. 保持 `SEG`、`SHOT`、`MOTION` 的 owner 边界。
2. 不把个人项目、真实媒体、凭据或本机绝对路径加入仓库。
3. 为契约或脚本变更补充对应的离线检查。
4. 在 Pull Request 中说明兼容性影响和迁移方式。

## 许可证

本项目采用 [MIT License](LICENSE)。第三方模型、ComfyUI 工作流、字体、图片、音频和视频素材不包含在本仓库中，各自遵循其原始许可证。
