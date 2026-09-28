#!/usr/bin/env python3
"""Exercise H3 profile propagation and optional editing exports offline."""
import json
import tempfile
import unittest
from pathlib import Path

import project_tool as project


class H3ProjectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "project"
        project.initialize_project(self.root, title="H3 test", language="zh", aspect_ratio="9:16")

    def test_profile_published_accepted_and_visible_in_status(self):
        choices = {"workflow_suite": "short-drama-h3", "storyboard_unit": "video_segment",
                   "target_video_model": "minimax-h3", "video_prompt_language": "zh",
                   "video_prompt_dialect": "minimax-h3-segmented"}
        decision = {"decision_id": "CD-H3", "status": "accepted",
                    "target_locators": [{"src": "short-drama", "field": "/creator_authority/production_profile/choices"}],
                    "accepted_value": choices}
        relative = "创作者决策/profile.jsonl"
        project.publish_candidate(self.root, owner="short-drama-h3", artifact_id="PROFILE",
                                  outputs={relative: json.dumps(decision, ensure_ascii=False) + "\n"})
        project.record_creator_acceptance(self.root, artifact_id="PROFILE", decision="accepted")
        project.set_creator_authority(self.root, field="/creator_authority/production_profile/choices",
                                      decision_path=relative, decision_id="CD-H3")
        self.assertEqual(project.project_status(self.root)["video_model_profile"], choices)

    def test_init_has_an_unset_project_wide_prompt_style_slot(self):
        manifest = json.loads((self.root / "short-drama.json").read_text(encoding="utf-8"))
        style = manifest["creator_authority"]["prompt_style"]
        self.assertEqual(style["status"], "unset")
        self.assertEqual(style["choices"]["style_and_tone_lock"], None)
        self.assertEqual(style["choices"]["preprompt_rules"], None)
        self.assertEqual(style["choices"]["image_prompt_lock"], None)
        self.assertEqual(style["choices"]["negative_visual_rules"], [])
        self.assertEqual(project.project_status(self.root)["prompt_style_status"], "unset")

    def test_accepted_prompt_style_can_be_written_through_creator_authority(self):
        choices = {
            "style_and_tone_lock": "Warm, restrained, live-action film realism; consistent throughout.",
            "preprompt_rules": "Video-wide camera, lighting, sound, and negative rules.",
            "image_prompt_lock": "Use the same restrained color, natural light, and tactile materials.",
            "negative_visual_rules": ["No plastic skin", "No text overlays"],
        }
        decision = {
            "decision_id": "CD-STYLE",
            "decision_kind": "prompt_style",
            "status": "accepted",
            "target_locators": [{
                "src": "short-drama",
                "field": "/creator_authority/prompt_style/choices",
            }],
            "accepted_value": choices,
        }
        relative = "创作者决策/prompt-style.jsonl"
        project.publish_candidate(
            self.root,
            owner="short-drama-h3",
            artifact_id="PROMPT-STYLE",
            outputs={relative: json.dumps(decision, ensure_ascii=False) + "\n"},
        )
        project.record_creator_acceptance(
            self.root, artifact_id="PROMPT-STYLE", decision="accepted"
        )
        project.set_creator_authority(
            self.root,
            field="/creator_authority/prompt_style/choices",
            decision_path=relative,
            decision_id="CD-STYLE",
        )
        manifest = json.loads((self.root / "short-drama.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["creator_authority"]["prompt_style"]["choices"], choices
        )
        self.assertEqual(project.project_status(self.root)["prompt_style_status"], "accepted")

    def test_prompt_style_requires_both_modality_locks(self):
        incomplete = {
            "style_and_tone_lock": "Consistent project-wide look.",
            "preprompt_rules": "Complete video rules.",
            "negative_visual_rules": [],
        }
        decision = {
            "decision_id": "CD-STYLE-INCOMPLETE",
            "decision_kind": "prompt_style",
            "status": "accepted",
            "target_locators": [{
                "src": "short-drama",
                "field": "/creator_authority/prompt_style/choices",
            }],
            "accepted_value": incomplete,
        }
        relative = "创作者决策/prompt-style-incomplete.jsonl"
        project.publish_candidate(
            self.root,
            owner="short-drama-h3",
            artifact_id="PROMPT-STYLE-INCOMPLETE",
            outputs={relative: json.dumps(decision, ensure_ascii=False) + "\n"},
        )
        project.record_creator_acceptance(
            self.root, artifact_id="PROMPT-STYLE-INCOMPLETE", decision="accepted"
        )
        with self.assertRaisesRegex(ValueError, "image_prompt_lock"):
            project.set_creator_authority(
                self.root,
                field="/creator_authority/prompt_style/choices",
                decision_path=relative,
                decision_id="CD-STYLE-INCOMPLETE",
            )

    def test_prompt_style_cannot_conflict_with_project_aspect_ratio(self):
        choices = {
            "style_and_tone_lock": "Consistent project-wide look.",
            "preprompt_rules": "Real live-action film, 16:9 widescreen.",
            "image_prompt_lock": "Use the same restrained color and natural light.",
            "negative_visual_rules": [],
        }
        decision = {
            "decision_id": "CD-STYLE-RATIO",
            "decision_kind": "prompt_style",
            "status": "accepted",
            "target_locators": [{
                "src": "short-drama",
                "field": "/creator_authority/prompt_style/choices",
            }],
            "accepted_value": choices,
        }
        relative = "创作者决策/prompt-style-ratio.jsonl"
        project.publish_candidate(
            self.root,
            owner="short-drama-h3",
            artifact_id="PROMPT-STYLE-RATIO",
            outputs={relative: json.dumps(decision, ensure_ascii=False) + "\n"},
        )
        project.record_creator_acceptance(
            self.root, artifact_id="PROMPT-STYLE-RATIO", decision="accepted"
        )
        with self.assertRaisesRegex(ValueError, "aspect_ratio"):
            project.set_creator_authority(
                self.root,
                field="/creator_authority/prompt_style/choices",
                decision_path=relative,
                decision_id="CD-STYLE-RATIO",
            )

    def test_existing_edit_document_is_exported_but_not_required(self):
        episode = self.root / "剧集/EP001"
        episode.mkdir(parents=True)
        (episode / "剧本.md").write_text("# EP001\n", encoding="utf-8")
        first = self.base / "first-export"
        project.build_creator_export(self.root, out=first)
        self.assertFalse(any(p.name == "剪辑单.md" for p in first.rglob("*")))
        edit = "# EP001 剪辑单\n"
        (episode / "剪辑单.md").write_text(edit, encoding="utf-8")
        second = self.base / "second-export"
        project.build_creator_export(self.root, out=second)
        exported = list(second.rglob("剪辑单.md"))
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0].read_text(encoding="utf-8"), edit)
        self.assertFalse(any(p.name == ".short-drama" for p in second.rglob("*")))


if __name__ == "__main__":
    unittest.main()
