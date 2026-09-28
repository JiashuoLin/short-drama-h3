# 项目全局提示词风格

项目级提示词风格保存在 `short-drama.json#/creator_authority/prompt_style/choices`，作为视频与图片提示词的共同来源。新项目初始化时该块为 `unset`；首次编写视觉资产提示词、冻结关键帧或视频提示词前，必须在项目初始化阶段确认并接受风格决策。创作者明确把本轮给出的规则指定为全项目主题时，可直接将其整理入决策，不必重复询问。

## 固定字段

| 字段 | 用途 |
| --- | --- |
| `style_and_tone_lock` | 所有视频段复用的短风格锁；图片锁需表达相同的视觉方向 |
| `preprompt_rules` | 完整视频全局母版，可包含摄影、声音、文字、字幕、配乐和视频负面约束 |
| `image_prompt_lock` | 图片提示词使用的固定视觉规则，按 `format.prompt_language` 编写；不得包含声音、配乐、帧率、快门、运镜或时间动作规则 |
| `negative_visual_rules` | 按 `format.prompt_language` 编写的纯视觉排除项数组；无排除项时写空数组 |

保留创作者原意。由一段混合文字整理成这些字段时，不能把声音要求塞入图片规则，也不能把“不要文字”扩成禁止已接受的剧情招牌、证据文字或其他可读文字。若文字需求与负面项冲突，先按《视觉设定.md》的资产文字政策限定作用范围；必要文字在其指定承载面上优先。

项目画幅只由 `short-drama.json#/format/aspect_ratio` 决定。接受主题前，将视频母版中的画幅与档案核对；不一致时先请创作者确定，再接受决策。不要把视频画幅机械加到人物转面板、道具板等需要其他版式的图片提示词。真人、动画、定格等媒介必须与制作形态一致；摄影机、胶片、皮肤和材质规则按该媒介条件化，不得把真人基线硬套给非真人项目。

## 接受与回写

在 `创作者决策/` 保存接受记录，`target_locators` 指向 `/creator_authority/prompt_style/choices`，再使用项目工具的 `publish`、`accept` 和 `set-authority` 写入。决策 ID 按项目取未占用值：

```json
{
  "decision_id": "CD-STYLE-001",
  "decision_kind": "prompt_style",
  "status": "accepted",
  "scope": "series",
  "target_locators": [{
    "src": "short-drama",
    "field": "/creator_authority/prompt_style/choices"
  }],
  "accepted_value": {
    "style_and_tone_lock": "<已确认的简短全局视觉风格句>",
    "preprompt_rules": "<完整视频母版>",
    "image_prompt_lock": "<图片专用固定视觉规则>",
    "negative_visual_rules": []
  }
}
```

后续任何阶段要改锁，创建 supersedes 原决策的新版本；不可只改某一份文档。换锁后刷新所有已存在且受影响的资产图提示词、SEG 冻结关键帧和 MOTION 视频提示词。已接受的角色、造型、地点、道具、剧本文字和连续性事实不会因全局风格决策自动改写。

## 阶段投影

| 阶段 | 必须复用 | 不得复制/覆盖 |
| --- | --- | --- |
| 视频提示词 | `preprompt_rules`、`style_and_tone_lock` 原文进入 Part 1；每个可交接 MOTION 逐字重复风格锁 | 不得另编同义母版；项目文字政策确认允许的证据文字、对白/VO/OS优先于泛化负面规则 |
| 资产图片提示词 | 每条可复制正文都加入完整 `image_prompt_lock`，并在负面约束处应用 `negative_visual_rules` | 不加声音、配乐、帧率、快门、运镜、动态动作或不适用的输出画幅 |
| SEG 冻结关键帧 | 在段首/段尾实际可见画面描述中加入 `image_prompt_lock`，并应用适用的视觉负面项 | 不能让风格要求改变机位可见性、遮挡、资产身份或该帧的剧情状态 |

图片正文先说明对象和用途，再紧接固定 `image_prompt_lock`，然后写该图独有的身份锚点、状态、静态机位/观看角度、构图和背景；负面视觉规则放在末尾。若接受的风格规则与具体资产事实、可见文字、分镜冻结状态或构图用途互相矛盾，先解决冲突，不得机械拼接。

旧项目没有 `prompt_style` 字段时，继续遵从已接受的旧视频主题母版与视觉方向，不伪称新档案已接受；不要为兼容而改写旧项目。新初始化项目若风格状态仍为 `unset`，可继续不依赖风格的文字工作，但不可把资产图片、冻结关键帧或视频提示词标成可交接。
