#!/usr/bin/env python3
"""Offline regressions for the H3 SEG/SHOT/MOTION contract."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import creator_markdown_check as checker


SCRIPT = """# EP001 测试
## EP001-SC001 内 · 客厅 · 日
林薇：别下。
周曼：怎么了？
"""
VISUAL = """# 视觉设定
## 人物 · 林薇
- 识别锚点：短发，白色衬衫。
## 人物 · 周曼
- 识别锚点：长发，黑色外套。
"""
STORYBOARD = """# 分镜
## SEG-EP001-001 · 试探
- 来源：EP001-SC001
- 时长：12s
- 全局时间：00:00.000–00:12.000
- 段首状态：林薇坐着，周曼站在门口。
- 段尾交接：两人对视。
- 环境声音：衣物摩擦声，无配乐。

### SHOT-EP001-001-01
- 时间：0.00–5.00s
- 景别：中景 MS
- 运镜：固定机位 Static shot
- 画面动作：林薇抬头。
- 台词：林薇（S1）：<d>[chinese] 别下。</d>

### SHOT-EP001-001-02
- 时间：5.00–12.00s
- 景别：近景 CU
- 运镜：缓慢推镜 Slow push in
- 画面动作：周曼停步。
- 台词：周曼（S2）：<d>[chinese] 怎么了？</d>
"""
PROMPT = """subject_definitions:
<Subject 1> 是 人物「林薇」，短发，白色衬衫；对应发声者（S1），声音克制。
<Subject 2> 是 人物「周曼」，长发，黑色外套；对应发声者（S2），声音冷静。
summary:
门口两人短暂试探。
retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - 仅保持林薇身份，不控制姿态与构图。
<Subject 2> (appears in [Shot 1], [Shot 2]): fully_preserved - 仅保持周曼身份，不控制姿态与构图。
detailed_description:
真人摄影，稳定造型。[Shot 1] 中景 MS，固定机位 Static shot，从 <Subject 2> 门口向 <Subject 1> 取景：<Subject 1> 坐着并抬头。<Subject 1>（S1）压低声音、克制地说：<d>[chinese] 别下。</d>
[Shot 2] At 00:05.000，近景 CU，缓慢推镜 Slow push in 框住 <Subject 2>：<Subject 2> 停步。<Subject 2>（S2）困惑地问：<d>[chinese] 怎么了？</d>两人对视。
overall_soundscape:
衣物摩擦声。
non_diegetic_music: N/A
"""
REF = "REF-LINWEI（顺序：1）· 输入/林薇.png《林薇》（用途：身份；控制：脸型、发型；不得控制：姿态、构图）"
PLAN = "PLAN-LINWEI（顺序：1）《林薇》（用途：身份；控制：脸型、发型；不得控制：姿态、构图）"


def video(ref: str = REF, state: str = "可交接", prompt: str | None = PROMPT) -> str:
    result = """# 视频提示词
Part 1 · 主题定义
preprompt_rules: 9:16，中文叙述。
style_and_tone_lock: 真人摄影，稳定造型。
story_continuity: 从进门延续对话。
subject_definitions:
<Subject 1> 是 人物「林薇」，短发，白色衬衫；对应发声者（S1），声音克制。
<Subject 2> 是 人物「周曼」，长发，黑色外套；对应发声者（S2），声音冷静。
ref_mapping:
MOTION-EP001-001 + REPLACE_ID + <Subject 1> + 1

## MOTION-EP001-001 · 试探
- 分镜段：SEG-EP001-001
- 时长：12s
- 生成方式：图生视频
- 输入参考图：REPLACE_REF
- 起始帧：无独立实图；开场按 SEG-EP001-001 的段首状态实现
- 段首状态：林薇坐着，周曼站在门口。
- 段尾交接：两人对视。
- 成员分镜：SHOT-EP001-001-01（0.00–5.00s）；SHOT-EP001-001-02（5.00–12.00s）
- 准备状态：REPLACE_STATE
""".replace("REPLACE_ID", "PLAN-LINWEI" if "PLAN-" in ref else "REF-LINWEI").replace("REPLACE_REF", ref).replace("REPLACE_STATE", state)
    if prompt is not None:
        result += "\n### 可复制提示词\n" + prompt + "\n"
    return result


class ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.episode = self.root / "剧集" / "EP001"
        self.episode.mkdir(parents=True)
        (self.root / "输入").mkdir()
        (self.root / "输入" / "林薇.png").write_bytes(b"fixture: media inspection intentionally not performed")
        (self.root / "short-drama.json").write_text(json.dumps({
            "format": {"aspect_ratio": "9:16"},
            "creator_authority": {"production_profile": {"status": "accepted", "choices": {
                "workflow_suite": "short-drama-h3", "storyboard_unit": "video_segment",
                "video_prompt_language": "zh", "target_video_model": "minimax-h3",
                "video_prompt_dialect": "minimax-h3-segmented",
                "native_duration_seconds": {"min": 4, "max": 15},
            }}},
        }), encoding="utf-8")
        self.write("剧本.md", SCRIPT)
        self.write("视觉设定.md", VISUAL)
        self.write("分镜.md", STORYBOARD)
        self.write("视频提示词.md", video())

    def write(self, name: str, text: str) -> None:
        (self.episode / name).write_text(text, encoding="utf-8")

    def set_prompt_style(self, status: str, preprompt: str = "9:16，中文叙述。", lock: str = "真人摄影，稳定造型。") -> None:
        manifest_path = self.root / "short-drama.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["creator_authority"]["prompt_style"] = {
            "status": status,
            "choices": {
                "style_and_tone_lock": lock,
                "preprompt_rules": preprompt,
                "image_prompt_lock": "自然光线，真实材质。",
                "negative_visual_rules": [],
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def test_handoff_requires_initialized_project_style_to_be_accepted(self):
        self.set_prompt_style("unset")
        self.assert_error("prompt_style", level="handoff")

    def test_video_global_theme_must_match_accepted_project_style(self):
        self.set_prompt_style("accepted", preprompt="完全不同的视频母版。", lock="动画风格锁。")
        self.assert_error("preprompt_rules", level="handoff")
        self.assert_error("style_and_tone_lock", level="handoff")

    def test_matching_accepted_project_style_passes_video_theme_check(self):
        self.set_prompt_style("accepted")
        result = self.check(level="handoff")
        self.assertTrue(result["ok"], result)

    def test_shot_image_prompt_is_rejected(self):
        invalid = STORYBOARD.replace(
            "- 台词：林薇（S1）：<d>[chinese] 别下。</d>",
            "- 台词：林薇（S1）：<d>[chinese] 别下。</d>\n- 图片提示词：林薇坐在画面左侧。",
            1,
        )
        self.write("分镜.md", invalid)
        self.assert_error("SHOT 不得包含图片提示词", stage="storyboard")

    def check(self, **kwargs):
        return checker.check_episode(self.episode, self.root, **kwargs)

    def assert_error(self, marker: str, **kwargs) -> None:
        result = self.check(**kwargs)
        self.assertFalse(result["ok"], result)
        self.assertIn(marker, "\n".join(result["errors"]))

    def test_valid_segment_does_not_require_image_document(self):
        self.assertEqual(checker.validate_episode(self.episode, self.root), [])

    def test_storyboard_stage_does_not_require_video_document(self):
        (self.episode / "视频提示词.md").unlink()
        self.assertTrue(self.check(stage="storyboard")["ok"])
        result = self.check(stage="all", level="structure")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["gaps"])
        self.assert_error("视频提示词", stage="all", level="complete")

    def test_valid_handoff_is_scoped_and_explicitly_not_media_review(self):
        result = self.check(stage="video", level="handoff", motion="MOTION-EP001-001")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["unchecked"])

    def test_timing_gap_and_nonfinite_duration_are_rejected(self):
        self.write("分镜.md", STORYBOARD.replace("5.00–12.00s", "6.00–12.00s"))
        self.assert_error("连续", stage="storyboard")
        self.write("分镜.md", STORYBOARD.replace("时长：12s", "时长：NaNs"))
        self.assert_error("时长", stage="storyboard")

    def test_h3_camera_terms_and_static_default_are_rejected(self):
        self.write("分镜.md", STORYBOARD.replace("缓慢推镜 Slow push in", "自由摇摆镜头"))
        self.assert_error("本地 H3 优化器词表", stage="storyboard")
        all_static = STORYBOARD.replace("缓慢推镜 Slow push in", "固定机位 Static shot")
        self.write("分镜.md", all_static)
        self.assert_error("动作型 SEG 不能", stage="storyboard")

    def test_shots_have_exact_fields_and_scene_exists(self):
        self.write("分镜.md", STORYBOARD.replace("- 时间：0.00", "- 视觉依据：旧字段\n- 时间：0.00"))
        self.assert_error("视觉依据", stage="storyboard")
        self.write("分镜.md", STORYBOARD.replace("来源：EP001-SC001", "来源：EP001-SC999"))
        self.assert_error("SC999", stage="storyboard")

    def test_segment_reference_placeholder_is_allowed_but_real_binding_is_not(self):
        placeholder = "- 参考图占位：待补参考图：林薇身份图、客厅地理图、段首构图图\n"
        self.write("分镜.md", STORYBOARD.replace("- 来源：EP001-SC001\n", "- 来源：EP001-SC001\n" + placeholder))
        self.assertTrue(self.check(stage="storyboard")["ok"])
        self.write("分镜.md", STORYBOARD.replace("- 来源：EP001-SC001\n", "- 来源：EP001-SC001\n- 参考图占位：REF-LINWEI\n"))
        self.assert_error("真实 REF/PLAN", stage="storyboard")

    def test_dialogue_speaker_change_and_duplicate_are_rejected(self):
        self.write("分镜.md", STORYBOARD.replace("林薇（S1）：<d>", "周曼（S2）：<d>"))
        self.assert_error("台词", stage="storyboard")
        self.write("分镜.md", STORYBOARD)
        self.write("视频提示词.md", video(prompt=PROMPT.replace("衣物摩擦声。", "衣物摩擦声。<Subject 1>（S1）：<d>[chinese] 别下。</d>")))
        self.assert_error("台词", level="handoff")

    def test_speaker_ids_follow_first_actual_vocal_event(self):
        swapped = STORYBOARD.replace("（S1）", "（TMP）").replace("（S2）", "（S1）").replace("（TMP）", "（S2）")
        self.write("分镜.md", swapped)
        self.assert_error("首次发声顺序", stage="storyboard")

    def test_external_plan_is_complete_but_not_ready(self):
        self.write("视频提示词.md", video(PLAN, "外部挂图计划"))
        self.assertTrue(self.check(stage="video", level="complete")["ok"])
        self.assert_error("PLAN", stage="video", level="handoff")

    def test_missing_prompt_is_normal_draft_but_not_complete(self):
        self.write("视频提示词.md", video("无（待补参考图：林薇身份图）", "待参考", None))
        result = self.check(stage="video", level="structure")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["gaps"])
        self.assert_error("可复制", stage="video", level="complete")

    def test_repeated_file_and_traversal_are_rejected(self):
        second = REF.replace("REF-LINWEI", "REF-LINWEI-OTHER").replace("顺序：1", "顺序：2").replace("用途：身份", "用途：造型状态")
        self.write("视频提示词.md", video(REF + "；" + second))
        self.assert_error("重复", stage="video")
        self.write("视频提示词.md", video(REF.replace("输入/林薇.png", "../林薇.png")))
        self.assert_error("路径", stage="video")

    def test_picture_numbers_and_shot_times_match(self):
        self.write("视频提示词.md", video(prompt=PROMPT.replace("<Subject 1> (appears", "<Picture 1> (appears", 1)))
        self.assertTrue(self.check(stage="video", level="handoff")["ok"])
        self.write("视频提示词.md", video(prompt=PROMPT.replace("<Subject 1> 坐着", "<Subject 1> 坐着，外观来自 <Picture 2>")))
        self.assert_error("Picture", stage="video", level="handoff")
        self.write("视频提示词.md", video(prompt=PROMPT.replace("At 00:05.000", "At 00:06.000")))
        self.assert_error("切点", stage="video", level="handoff")

    def test_no_silent_text_fallback(self):
        self.write("视频提示词.md", video("无", "可交接").replace("生成方式：图生视频", "生成方式：文生视频"))
        self.assert_error("文生", stage="video", level="handoff")

    def test_canonical_subject_speaker_and_retention_shot_mentions(self):
        self.write("视频提示词.md", video(prompt=PROMPT))
        self.assertTrue(self.check(level="handoff")["ok"])

    def test_visible_speaker_name_and_subject_identity_suffix_are_rejected(self):
        named = PROMPT.replace("<Subject 1>（S1）压低声音、克制地说：<d>", "林薇（S1）压低声音、克制地说：<d>")
        self.write("视频提示词.md", video(prompt=named))
        self.assert_error("可见人物对白必须使用", level="handoff")
        repeated = PROMPT.replace("<Subject 1> 坐着", "<Subject 1> 林薇坐着")
        self.write("视频提示词.md", video(prompt=repeated))
        self.assert_error("不得重复角色或资产名称", level="handoff")

    def test_shot_rejects_subject_inventory_and_requires_inline_delivery(self):
        inventory = PROMPT.replace(
            "中景 MS，固定机位 Static shot，从 <Subject 2> 门口向 <Subject 1> 取景：<Subject 1> 坐着并抬头。",
            "中景 MS，固定机位 Static shot：画面主体为<Subject 1>、<Subject 2>；她坐着并抬头。",
        )
        self.write("视频提示词.md", video(prompt=inventory))
        self.assert_error("主体清单", level="handoff")

        no_delivery = PROMPT.replace("<Subject 1>（S1）压低声音、克制地说：<d>", "<Subject 1>（S1）：<d>")
        self.write("视频提示词.md", video(prompt=no_delivery))
        self.assert_error("发声动作或语气", level="handoff")

    def test_plain_duplicate_dialogue_and_wrong_subject_speaker(self):
        self.write("视频提示词.md", video(prompt=PROMPT.replace("衣物摩擦声。", "衣物摩擦声。别下。")))
        self.assert_error("重复抄写", level="handoff")
        self.write("视频提示词.md", video(prompt=PROMPT.replace("<Subject 1>（S1）压低声音、克制地说：<d>", "<Subject 2>（S1）压低声音、克制地说：<d>")))
        self.assert_error("身份不一致", level="handoff")

    def test_ghost_subject_and_visual_category_mismatch(self):
        self.write("视频提示词.md", video(prompt=PROMPT.replace("<Subject 1> 坐着并抬头。", "<Subject 99> 坐着并抬头。")))
        self.assert_error("未定义", level="handoff")
        self.write("视频提示词.md", video(prompt=PROMPT.replace("人物「林薇」", "地点「林薇」")))
        self.assert_error("类别", level="handoff")

    def test_handoff_requires_segmented_profile(self):
        path = self.root / "short-drama.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["creator_authority"]["production_profile"]["choices"]["video_prompt_dialect"] = "minimax-h3"
        path.write_text(json.dumps(profile), encoding="utf-8")
        self.assert_error("video_prompt_dialect", level="handoff")

    def test_selected_motion_ignores_unrelated_draft_but_complete_covers_all(self):
        second_segment = STORYBOARD.replace("EP001-001", "EP001-002").replace("00:00.000–00:12.000", "00:12.000–00:24.000")
        self.write("分镜.md", STORYBOARD + second_segment.removeprefix("# 分镜\n"))
        self.write("剧本.md", SCRIPT + "林薇：别下。\n周曼：怎么了？\n")
        self.write("视频提示词.md", video() + "\n## MOTION-EP001-002 · 尚未完成\n- 分镜段：SEG-EP001-002\n- 准备状态：草稿\n")
        result = self.check(stage="video", level="handoff", motion="MOTION-EP001-001")
        self.assertTrue(result["ok"], result)
        self.assert_error("MOTION-EP001-002", stage="video", level="complete")
        self.assert_error("不存在", stage="video", level="handoff", motion="MOTION-EP001-999")

    def test_same_file_has_local_order_in_two_motions(self):
        (self.root / "输入" / "周曼.png").write_bytes(b"fixture reference B, no content validation")
        ref_b = REF.replace("REF-LINWEI", "REF-ZHOUMAN").replace("林薇", "周曼")
        first_refs = REF + "；" + ref_b.replace("顺序：1", "顺序：2")
        second_refs = ref_b + "；" + REF.replace("顺序：1", "顺序：2")
        prompt = PROMPT
        first_video = video(first_refs, prompt=prompt)
        mappings = "\n".join([
            "MOTION-EP001-001 + REF-LINWEI + <Subject 1> + 1",
            "MOTION-EP001-001 + REF-ZHOUMAN + <Subject 2> + 2",
            "MOTION-EP001-002 + REF-ZHOUMAN + <Subject 2> + 1",
            "MOTION-EP001-002 + REF-LINWEI + <Subject 1> + 2",
        ])
        first_video = first_video.replace("MOTION-EP001-001 + REF-LINWEI + <Subject 1> + 1", mappings)
        second_video = "## MOTION-" + video(second_refs, prompt=prompt).partition("## MOTION-")[2]
        self.write("视频提示词.md", first_video + second_video.replace("EP001-001", "EP001-002"))
        self.write("分镜.md", STORYBOARD + STORYBOARD.removeprefix("# 分镜\n").replace("EP001-001", "EP001-002").replace("00:00.000–00:12.000", "00:12.000–00:24.000"))
        self.write("剧本.md", SCRIPT + "林薇：别下。\n周曼：怎么了？\n")
        result = self.check(stage="video", level="handoff")
        self.assertTrue(result["ok"], result)

    def test_reference_symlink_reserved_path_and_fifo_are_rejected(self):
        (self.root / "输入" / "alias.png").symlink_to(self.root / "输入" / "林薇.png")
        self.write("视频提示词.md", video(REF.replace("输入/林薇.png", "输入/alias.png")))
        self.assert_error("符号链接", level="handoff")
        self.write("视频提示词.md", video(REF.replace("输入/林薇.png", "输入/CON.png")))
        self.assert_error("路径", level="handoff")
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.root / "输入" / "pipe.png")
            self.write("视频提示词.md", video(REF.replace("输入/林薇.png", "输入/pipe.png")))
            self.assert_error("普通文件", level="handoff")

    def test_long_duration_duplicate_ids_and_global_gap(self):
        self.write("分镜.md", STORYBOARD.replace("时长：12s", "时长：16s"))
        self.assert_error("15s", stage="storyboard")
        self.write("分镜.md", STORYBOARD.replace("SHOT-EP001-001-02", "SHOT-EP001-001-01"))
        self.assert_error("ID 重复", stage="storyboard")
        self.write("分镜.md", STORYBOARD.replace("00:00.000–00:12.000", "00:01.000–00:13.000"))
        self.assert_error("全局时间必须从 0 连续", stage="storyboard")
        self.assert_error("全局时间必须从 0 连续", stage="video", level="handoff", motion="MOTION-EP001-001")

    def test_midsegment_lock_does_not_leak_into_start_frame(self):
        lock = "- 连续性锁：LOCK-GLOVES《手套》（镜头：SHOT-EP001-001-02）· 锁面：白色手套\n"
        self.write("视觉设定.md", VISUAL + lock)
        self.write("分镜.md", STORYBOARD + "\n### 段首冻结关键帧提示词\n> 林薇坐着，周曼站在门口。\n")
        self.write("视频提示词.md", video(prompt=PROMPT.replace("<Subject 2> 停步。", "<Subject 2> 停步，白色手套可见。")))
        result = self.check(level="handoff")
        self.assertTrue(result["ok"], result)
        self.write("视频提示词.md", video())
        self.assert_error("缺少锁面", level="handoff")

    def test_external_media_are_explicit_and_paired(self):
        self.write("视频提示词.md", video().replace("- 起始帧：", "- 续接视频：无\n- 实际尾帧：N/A\n- 输入音频：无\n- 起始帧："))
        self.assertTrue(self.check(level="handoff")["ok"])
        self.write("视频提示词.md", video(prompt=PROMPT.replace("门口两人", "<Video 1> 中门口两人")))
        self.assert_error("Video", level="handoff")
        self.write("视频提示词.md", video().replace("- 起始帧：", "- 续接视频：输入/前段.mp4\n- 起始帧："))
        self.assert_error("成对", level="handoff")
        self.write("视频提示词.md", video().replace("- 起始帧：", "- 输入参考视频：输入/前段.mp4\n- 起始帧："))
        self.assert_error("输入参考视频", level="handoff")

    def test_real_continuation_does_not_require_duplicate_tail_picture(self):
        (self.root / "输入" / "前段.mp4").write_bytes(b"fixture video, no decoding")
        prompt = PROMPT.replace("<Subject 1> (appears", "<Video 1> (appears", 1).replace("仅保持林薇身份", "与实际尾帧保持当前人物身份")
        document = video("无（续接使用实际视频与尾帧）", prompt=prompt)
        document = document.replace("MOTION-EP001-001 + REF-LINWEI + <Subject 1> + 1", "无独立 Subject 参考")
        document = document.replace("- 起始帧：", "- 续接视频：输入/前段.mp4\n- 实际尾帧：输入/林薇.png\n- 起始帧：")
        self.write("视频提示词.md", document)
        result = self.check(level="handoff")
        self.assertTrue(result["ok"], result)

    def test_style_lock_must_prefix_handoff_detailed_description(self):
        self.write("视频提示词.md", video().replace("style_and_tone_lock: 真人摄影，稳定造型。", "style_and_tone_lock: 手绘二维动画，保留明确线条和块面。"))
        self.assert_error("style_and_tone_lock", stage="video", level="handoff", motion="MOTION-EP001-001")
        late = PROMPT.replace("真人摄影，稳定造型。", "") + "真人摄影，稳定造型。"
        self.write("视频提示词.md", video(prompt=late))
        self.assert_error("style_and_tone_lock", level="handoff")

    def test_retention_requires_typed_mode_and_valid_shots(self):
        for mutation in (
            PROMPT.replace("fully_preserved", "BANANA"),
            PROMPT.replace("fully_preserved", "fully_copy"),
            PROMPT.replace("(appears in [Shot 1], [Shot 2])", ""),
            PROMPT.replace("(appears in [Shot 1], [Shot 2])", "(appears in [Shot 1], [Shot 99])"),
        ):
            with self.subTest(retention=mutation):
                self.write("视频提示词.md", video(prompt=mutation))
                self.assert_error("retention", level="handoff")
        (self.root / "输入" / "声音.wav").write_bytes(b"fixture audio, no decoding")
        audio_prompt = PROMPT.replace("detailed_description:\n", "<Audio 1> (appears in [Shot 1]): fully_copy - 保留已提供的声音片段。\ndetailed_description:\n")
        document = video(prompt=audio_prompt).replace("- 起始帧：", "- 输入音频：输入/声音.wav\n- 起始帧：")
        self.write("视频提示词.md", document)
        self.assertTrue(self.check(level="handoff")["ok"])
        self.write("视频提示词.md", document.replace("fully_copy - 保留", "fully_preserved - 保留"))
        self.assert_error("retention", level="handoff")

    def test_narrator_identity_does_not_require_visible_subject(self):
        self.write("剧本.md", SCRIPT.replace("周曼：怎么了？", "[VO] 旁白：怎么了？"))
        self.write("分镜.md", STORYBOARD.replace("周曼（S2）", "旁白（S2，旁白）"))
        definition = "旁白 (S2)，稳定低沉中性声音，无可见主体。"
        visual_definition = "<Subject 2> 是 人物「周曼」，长发，黑色外套；对应发声者（S2），声音冷静。"
        unvoiced_visual_definition = "<Subject 2> 是 人物「周曼」，长发，黑色外套。"
        for position in ("before", "after"):
            with self.subTest(position=position):
                prompt = PROMPT.replace(visual_definition, unvoiced_visual_definition).replace("<Subject 2>（S2）困惑地问：<d>", "旁白（S2）：<d>")
                if position == "before":
                    prompt = prompt.replace("subject_definitions:\n", "subject_definitions:\n" + definition + "\n")
                else:
                    prompt = prompt.replace("summary:\n", definition + "\nsummary:\n")
                doc = video(prompt=prompt).replace(visual_definition, unvoiced_visual_definition + "\n" + definition)
                self.write("视频提示词.md", doc)
                result = self.check(stage="video", level="handoff", motion="MOTION-EP001-001")
                self.assertTrue(result["ok"], result)
        self.write("视频提示词.md", doc.replace(definition, "陈父 (S2)，稳定低沉中性声音，无可见主体。"))
        self.assert_error("说话人", level="handoff")

    def test_pending_continuation_can_register_one_available_file(self):
        (self.root / "输入" / "前段.mp4").write_bytes(b"fixture video, no decoding")
        document = video(state="待续接", prompt=None).replace("- 起始帧：", "- 续接视频：输入/前段.mp4\n- 实际尾帧：无\n- 起始帧：")
        self.write("视频提示词.md", document)
        result = self.check(stage="video", level="structure")
        self.assertTrue(result["ok"], result)
        self.assertTrue(any("实际尾帧" in gap for gap in result["gaps"]))
        self.assert_error("成对", stage="video", level="complete")
        self.assert_error("成对", stage="video", level="handoff")
        self.write("视频提示词.md", document.replace("准备状态：待续接", "准备状态：可交接"))
        self.assert_error("成对", stage="video", level="structure")
        self.write("视频提示词.md", document.replace("输入/前段.mp4", "../前段.mp4"))
        self.assert_error("路径", stage="video", level="structure")


if __name__ == "__main__":
    unittest.main()
