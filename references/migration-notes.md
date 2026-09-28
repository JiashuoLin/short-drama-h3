# 迁移来源与维护边界

本套件使用独立的 `short-drama-h3*` 目录，不回读原技能目录。项目协议仍保留 `short-drama.json`、`.short-drama/` 和决策 locator 的 `src: short-drama`，它们不是旧技能运行依赖。

## 来源

| 来源 | 保留内容 | 定向适配 |
| --- | --- | --- |
| Codex `short-drama` 与 creator-first 子技能 | 项目安全写入、状态与导出；开发、原著分析、剧本、资产、图片和审查方法 | 新 owner 路由、SEG 档案、可选剪辑单导出与按阶段检查 |
| `short-drama-h3-storyboard/references/h3-15s-prompt-optimizer/` | 自然节拍、15 秒上限、段内多镜、景别/运镜、中文六段式 | 文档已内置于 storyboard；SEG/SHOT 结构仍归 storyboard，参考图与六段式正文仍归 MOTION；项目事实只约束画幅/形态/连续性 |
| `short-drama-h3-storyboard/references/h3-prompt-writing/` | H3 标签、局部切点、说话人及 retention 写法 | 需要的语法资料已复制到 storyboard；运行时不调用来源技能 |
| `.dsh/skills/short-drama-edit` | CUT 来源、实测入出点、字幕、声音处理与渲染工具 | 逐段素材可拆多个 CUT，使用具体版本文件 |

原 short-drama 系列的 MIT 标记保留在各技能 frontmatter。迁移源文件摘要与取舍记录见 [来源清单](migration-sources.json)；此清单只服务维护，不是项目创作数据。

## 排除与暂缓

- 不携带 Dashboard、展示服务、静态前端和自动打开浏览器逻辑。剪辑的可选无头字幕渲染是输出工具，不是展示页面。
- 视频执行独立依赖 `minimax-h3-comfyui-video`。不复制 ComfyUI 工作流、参数、上传、预检、runner、轮询或视频 adapter；本套件只做当前输入交接与实际结果归属。
- 完整的独立 TTS/时间线音乐生产迁移、整集目标时长与未拍场景覆盖检查暂缓，不作本版门槛。剧本声音、H3 同次声音和已有音频剪辑仍保留。
- 旧资产、图片规格与审查 JSON 示例/校验器没有进入创作主链；原著分析、剧本派生分析、项目安全写入和实际生产所需的结构化工具按用途保留。
- 不自动迁移旧 SHOT 项目，不修改原技能，不运行真实媒体生产来证明安装完成。

## 离线维护

```bash
python3 <core>/scripts/validate_installation.py
python3 <core>/scripts/selftest.py
python3 <core>/scripts/test_project_h3.py
python3 <core>/scripts/test_h3_contract.py
python3 <produce>/scripts/selftest.py
python3 <edit>/scripts/selftest.py
```

分镜与视频检查使用总入口的新分层检查器；图片生产和视频交接的测试在 produce 技能中。每项输出必须区分结构结果与未做的语义、参考内容、表演及媒体质量核对。真实生成切点可能偏离计划，剪辑以实际文件测量为准。

基线行为测试已复现旧系统的逐镜产物、分镜层参考绑定和 H3 一镜一次生成假设；新契约改为 H2 SEG / H3 SHOT 与一段一 MOTION。迁移初版误删了旧分镜中的“待补参考图”需求占位，造成下游看不到人物、场景、道具和段首图缺口；现已恢复为 SEG 级 `参考图占位`，只记录需求类别和缺口，真实图片仍由视频提示词阶段核对并绑定。项目工具回归已验证 accepted 档案中的套件/分段标识可被 status 读取，且已有剪辑单会导出、缺少剪辑单不阻断导出。

## 首版验证记录

首版包含总入口和十个阶段 owner，共 11 个技能。开发、原著分析、写作的既有 selftest，以及项目状态/导出、SEG/SHOT/MOTION 契约、图片双来源失效、视频请求/返回来源和多 CUT 剪辑的离线回归已执行。元数据、相对文档链接、Python 语法与旧套件路由残留使用安装检查器核对。

配套示例位于 `short-drama-h3-storyboard/assets/12s-two-shots/`：12 秒、两镜、一个 MOTION，没有强制 IMG 或独立首帧。示例使用 PLAN，完整性检查可通过，实际交接必须拒绝；用于验证真实文件交接的测试素材仅证明路径、摘要与归属逻辑，不代表真实媒体质量。

没有执行真实图片或视频生产，也没有访问 ComfyUI。真实表演、生成切点、参考内容与跨段画面质量仍需在具体项目中审查；不将它们计入离线通过结果。迁移来源摘要核对与安装后路径验证记录以融合方案的首版实施记录为准。
