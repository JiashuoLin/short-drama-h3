#!/usr/bin/env python3
"""Offline, scoped validation of the independent H3 creative Markdown contract.

These checks prove text structure and references only, never media quality.
The public parsers return plain dictionaries for downstream handoff tools.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Optional


SEG_FIELDS = ("来源", "时长", "全局时间", "段首状态", "段尾交接", "环境声音")
SEG_OPTIONAL_FIELDS = ("参考图占位",)
SHOT_FIELDS = ("时间", "景别", "运镜", "画面动作", "台词")
CAMERA_MOTION_TOKENS = (
    "固定机位 Static shot",
    "固定机位（Static shot）",
    "缓慢推镜 Slow push in",
    "缓慢推镜（Slow push in）",
    "缓慢拉镜 Slow pull out",
    "缓慢拉镜（Slow pull out）",
    "横移轨道平移 Dolly track side",
    "横移轨道平移（Dolly track side）",
    "环绕轨道运镜 Slow orbit",
    "环绕轨道运镜（Slow orbit）",
    "轻微手持微晃 Subtle handheld",
    "轻微手持微晃（Subtle handheld）",
    "跟拍 Tracking follow",
    "跟拍（Tracking follow）",
    "缓慢仰起 Tilt up",
    "缓慢仰起（Tilt up）",
    "缓慢下压 Tilt down",
    "缓慢下压（Tilt down）",
    "缓慢左摇 Pan left",
    "缓慢左摇（Pan left）",
    "缓慢右摇 Pan right",
    "缓慢右摇（Pan right）",
)
STATIC_MOTION_TOKENS = ("固定机位 Static shot", "固定机位（Static shot）")
STATIC_REASON_TOKENS = (
    "观察",
    "证据",
    "受困",
    "权力压迫",
    "对峙",
    "锁住",
    "锁定",
    "保持静止",
    "文字卡",
    "黑屏",
    "定格",
    "静默落点",
)
MOTION_FIELDS = ("分镜段", "时长", "生成方式", "输入参考图", "起始帧", "段首状态", "段尾交接", "成员分镜", "准备状态")
STATES = ("草稿", "待参考", "外部挂图计划", "待续接", "可交接", "待调整")
PROMPT_FIELDS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")
GLOBAL_FIELDS = ("preprompt_rules", "style_and_tone_lock", "story_continuity", "subject_definitions", "ref_mapping")
REF_PURPOSES = ("身份", "造型状态", "地理", "构图", "尺度", "效果", "起始帧", "结束帧", "风格")
PICTURE_ANCHOR_PURPOSES = frozenset(("构图", "起始帧", "结束帧"))
EXPLICIT_TEXT_TO_VIDEO = "无（创作者已明确选择文生视频）"
MEDIA_FIELDS = ("续接视频", "实际尾帧", "输入音频")
HEAD_RE = re.compile(r"^(#{1,6})[ \t]+([^\n]+?)[ \t]*$", re.MULTILINE)
ID_RE = r"[A-Z0-9]+(?:-[A-Z0-9]+)*"
NUMBER_RE = r"\d+(?:\.\d+)?"
RANGE_RE = re.compile(rf"^({NUMBER_RE})[ \t]*[–—-][ \t]*({NUMBER_RE})s$")
DIALOGUE_RE = re.compile(r"<d>\s*\[chinese\]\s*(.*?)</d>", re.DOTALL)
REF_RE = re.compile(
    r"(REF-" + ID_RE + r")（顺序：([1-9]\d*)）· "
    r"([^；\n]+?\.(?:png|jpe?g|webp))《([^》\n]+)》"
    r"（用途：([^；）\n]+)；控制：([^；）\n]+)；不得控制：([^）\n]+)）",
    re.IGNORECASE,
)
PLAN_RE = re.compile(
    r"(PLAN-" + ID_RE + r")（顺序：([1-9]\d*)）《([^》\n]+)》"
    r"（用途：([^；）\n]+)；控制：([^；）\n]+)；不得控制：([^）\n]+)）"
)
NEGATION_RE = re.compile(r"(?:不要|不得|不能|不应|不含|不出现|没有|未|避免|禁止|排除|去掉|移除)(?:出现|包含|存在|带|有)?\s*$|\b(?:no|not|without|avoid)\s*$", re.IGNORECASE)
RETENTION_MODES = {
    "Subject": {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"},
    "Picture": {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"},
    "Video": {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"},
    "Audio": {"fully_copy", "partially_copy", "reference", "weak_reference"},
}


def _plain(value: str) -> str:
    return value.strip().rstrip("。")


def _compact_camera_text(value: str) -> str:
    """Treat spacing and Chinese/ASCII parentheses as camera-label formatting."""
    return re.sub(r"[\s（）()]", "", value)


def _unfenced(document: str) -> str:
    """Hide fenced examples without changing offsets in the original document."""
    fence = None
    lines = []
    for line in document.splitlines(keepends=True):
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        hidden = fence is not None or match is not None
        if match:
            mark = match.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
        lines.append(re.sub(r"[^\n]", " ", line) if hidden else line)
    return "".join(lines)


def _fields(section: str, *, owner: str, errors: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"^\s*[-*+]\s+([^：:\n]+)[：:](.*)$", line)
        if not match:
            continue
        key, value = (part.strip() for part in match.groups())
        if key in fields:
            errors.append(f"{owner}: 字段重复: {key}")
        fields[key] = value
    return fields


def _entries(document: str, kind: str, level: int, errors: list[str]) -> list[dict]:
    heads = list(HEAD_RE.finditer(_unfenced(document)))
    result = []
    seen: set[str] = set()
    for index, head in enumerate(heads):
        title = head.group(2)
        if not title.startswith(kind + "-"):
            continue
        match = re.fullmatch(rf"({kind}-{ID_RE})(?:[ \t]+·[ \t]+([^\n]+))?", title)
        if len(head.group(1)) != level or not match:
            errors.append(f"{kind}: 标题层级或 ID 格式错误: {title}")
            continue
        entry_id, name = match.groups()
        if entry_id in seen:
            errors.append(f"{entry_id}: ID 重复")
        seen.add(entry_id)
        if kind in {"SEG", "MOTION"} and (not name or not re.search(r"[\u3400-\u9fff]", name)):
            errors.append(f"{entry_id}: 标题缺少中文名称")
        end = next((h.start() for h in heads[index + 1:] if len(h.group(1)) <= level), len(document))
        body = document[head.start():end]
        direct = re.split(rf"^#{{{level + 1},}}\s", _unfenced(body), maxsplit=1, flags=re.MULTILINE)[0]
        result.append({"id": entry_id, "name": name or "", "fields": _fields(direct, owner=entry_id, errors=errors), "body": body})
    return result


def _copyable_prompt(section: str, heading: str = r"可复制(?:通用)?提示词") -> Optional[str]:
    matches = list(re.finditer(rf"^### {heading}[ \t]*$", _unfenced(section), re.MULTILINE))
    if len(matches) != 1:
        return None
    body = re.split(r"^#{1,3}\s", section[matches[0].end():], maxsplit=1, flags=re.MULTILINE)[0]
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return None
    # Prefer a fenced text block so the prompt can be copied without Markdown
    # quote markers. Keep accepting the legacy `>` block for existing projects.
    if lines[0].strip().startswith("```"):
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            return None
        content = lines[1:-1]
        return "\n".join(content).strip() or None
    if all(line.startswith(">") for line in lines):
        return "\n".join(line[1:].lstrip() for line in lines).strip() or None
    # Current H3 projects keep the copyable body as plain Markdown text under
    # the heading. This avoids leaking either quote markers or code fences.
    return "\n".join(lines).strip() or None


def _seconds(value: str) -> Optional[Decimal]:
    if not re.fullmatch(NUMBER_RE, value):
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        return None
    return result if result.is_finite() and math.isfinite(float(result)) else None


def _duration(value: str) -> Optional[Decimal]:
    return _seconds(value[:-1]) if value.endswith("s") else None


def _timestamp(value: str) -> Optional[Decimal]:
    if not re.fullmatch(r"(?:\d+:)?\d{2}:\d{2}(?:\.\d{1,3})?", value):
        return None
    parts = [_seconds(part) for part in value.split(":")]
    if any(part is None for part in parts) or parts[-1] >= 60 or (len(parts) == 3 and parts[-2] >= 60):
        return None
    result = Decimal(0)
    for part in parts:
        result = result * 60 + part
    return result if math.isfinite(float(result)) else None


def _interval(value: str, *, global_time: bool = False) -> Optional[tuple[Decimal, Decimal]]:
    if global_time:
        parts = re.split(r"[–—-]", value)
        parsed = tuple(_timestamp(part.strip()) for part in parts)
    else:
        match = RANGE_RE.fullmatch(value.strip())
        parsed = tuple(_seconds(part) for part in match.groups()) if match else ()
    if len(parsed) != 2 or any(part is None for part in parsed) or parsed[0] >= parsed[1]:
        return None
    return parsed


def parse_storyboard(document: str, errors: Optional[list[str]] = None) -> list[dict]:
    errors = errors if errors is not None else []
    segments = _entries(document, "SEG", 2, errors)
    all_shots = _entries(document, "SHOT", 3, errors)
    owned = []
    for segment in segments:
        segment["shots"] = _entries(segment["body"], "SHOT", 3, [])
        owned.extend(shot["id"] for shot in segment["shots"])
        duration = _duration(segment["fields"].get("时长", ""))
        interval = _interval(segment["fields"].get("全局时间", ""), global_time=True)
        segment["duration"] = float(duration) if duration is not None else None
        segment["interval"] = tuple(float(x) for x in interval) if interval else None
        allowed_headings = {shot["id"] for shot in segment["shots"]}
        allowed_headings.update({"空间站位分析", "空间规格", "负面提示词", "参考图分工", "段首冻结关键帧提示词", "段尾关键帧提示词"})
        for heading in HEAD_RE.finditer(_unfenced(segment["body"])):
            if len(heading.group(1)) == 3 and heading.group(2).split(" · ")[0] not in allowed_headings:
                errors.append(f"{segment['id']}: 不支持的段内标题: {heading.group(2)}")
            elif len(heading.group(1)) > 3:
                errors.append(f"{segment['id']}: SHOT 不包含子标题或镜内冻结关键帧")
        # Accept the retired heading for older storyboards; it is no longer required or parsed.
        for heading in ("段首冻结关键帧提示词", "段尾关键帧提示词"):
            if re.search(rf"^### {heading}[ \t]*$", segment["body"], re.MULTILINE) and _copyable_prompt(segment["body"], heading) is None:
                errors.append(f"{segment['id']}: {heading} 必须是唯一非空引用正文")
        for shot in segment["shots"]:
            shot_range = _interval(shot["fields"].get("时间", ""))
            shot["interval"] = tuple(float(x) for x in shot_range) if shot_range else None
    for shot in all_shots:
        if shot["id"] not in owned:
            errors.append(f"{shot['id']}: SHOT 必须属于一个 SEG")
    return segments


def parse_motions(document: str, errors: Optional[list[str]] = None) -> list[dict]:
    errors = errors if errors is not None else []
    motions = _entries(document, "MOTION", 2, errors)
    for motion in motions:
        motion["prompt"] = _copyable_prompt(motion["body"])
    return motions


def _portable_path(value: str) -> bool:
    if not value or any(ord(c) < 32 for c in value) or re.search(r'[\\<>:"|?*]', value) or PurePosixPath(value).is_absolute():
        return False
    reserved = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)
    return all(part not in {"", ".", ".."} and part == part.rstrip(" .") and not reserved.match(part) for part in value.split("/"))


def _inside(path: Path, root: Path) -> bool:
    return path.resolve() == root.resolve() or root.resolve() in path.resolve().parents


def _file(raw: str, root: Path, owner: str, errors: list[str], check_files: bool) -> Optional[Path]:
    if not _portable_path(raw):
        errors.append(f"{owner}: 路径不是安全的项目相对路径: {raw}")
        return None
    path = root / raw
    cursor = root
    for part in PurePosixPath(raw).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            errors.append(f"{owner}: 路径不能经过符号链接: {raw}")
            return None
    if not _inside(path, root):
        errors.append(f"{owner}: 路径越出项目根目录: {raw}")
        return None
    if check_files:
        descriptor = None
        try:
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("not a regular file")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(path, flags)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode) or not os.read(descriptor, 1):
                raise ValueError("not a nonempty regular file")
        except (OSError, ValueError):
            errors.append(f"{owner}: 文件不是非空可读普通文件: {raw}")
        finally:
            if descriptor is not None:
                os.close(descriptor)
    return path.resolve()


def parse_references(value: str, project_root: Path, owner: str = "MOTION", check_files: bool = True, errors: Optional[list[str]] = None) -> list[dict]:
    errors = errors if errors is not None else []
    if not value or value.startswith("无"):
        if "REF-" in value or "PLAN-" in value:
            errors.append(f"{owner}: 无参考声明不能包含 REF 或 PLAN")
        return []
    clean = re.sub(r"；待补参考图：[^\n]+$", "", value).rstrip("。")
    matches = sorted([(match, "REF") for match in REF_RE.finditer(clean)] + [(match, "PLAN") for match in PLAN_RE.finditer(clean)], key=lambda item: item[0].start())
    refs = []
    cursor = 0
    for index, (match, kind) in enumerate(matches):
        if clean[cursor:match.start()] != ("" if index == 0 else "；"):
            errors.append(f"{owner}: 输入参考图必须使用完整 REF/PLAN 语法")
        cursor = match.end()
        groups = match.groups()
        if kind == "REF":
            ref_id, order, raw, name, purpose, allowed, prohibited = groups
        else:
            ref_id, order, name, purpose, allowed, prohibited = groups
            raw = None
        refs.append({"id": ref_id, "order": int(order), "path": raw, "name": name, "purpose": purpose, "may_control": allowed, "must_not_control": prohibited, "kind": kind})
    if not matches or cursor != len(clean):
        errors.append(f"{owner}: 输入参考图必须使用完整 REF/PLAN 语法，PLAN 不写伪造路径")
    if [ref["order"] for ref in refs] != list(range(1, len(refs) + 1)):
        errors.append(f"{owner}: REF/PLAN 顺序必须按输入行从 1 连续编号")
    ids = [ref["id"] for ref in refs]
    if len(ids) != len(set(ids)):
        errors.append(f"{owner}: REF/PLAN ID 重复")
    files: set[Path] = set()
    for ref in refs:
        if ref["purpose"] not in REF_PURPOSES:
            errors.append(f"{owner}: 参考用途不在允许集合: {ref['id']}")
        if not re.search(r"[\u3400-\u9fff]", ref["name"]):
            errors.append(f"{owner}: 参考缺少中文名称: {ref['id']}")
        allowed = {word.strip() for word in re.split(r"[、，,]", ref["may_control"])}
        prohibited = {word.strip() for word in re.split(r"[、，,]", ref["must_not_control"])}
        if "" in allowed or "" in prohibited or allowed & prohibited:
            errors.append(f"{owner}: 参考控制与不得控制范围为空或冲突: {ref['id']}")
        if ref["path"]:
            path = _file(ref["path"], project_root, owner, errors, check_files)
            if path in files:
                errors.append(f"{owner}: 同一真实图片重复绑定: {ref['path']}")
            if path is not None:
                files.add(path)
    for role in ("起始帧", "结束帧"):
        if sum(ref["purpose"] == role for ref in refs) > 1:
            errors.append(f"{owner}: 同段只能有一个{role}参考")
    return refs


def check_picture_reference_bindings(prompt: str, refs: list[dict], owner: str, errors: list[str]) -> set[int]:
    """Bind H3 Picture labels only to real frame or composition anchor inputs.

    Attribute references remain Subject-only in the short-drama dialect. A
    confirmed first/last frame or composition anchor must be explicitly named
    as Picture N, where N is that REF's 1-based input order.
    """
    raw_tags = re.findall(r"<Picture\b[^>]*>", prompt, flags=re.IGNORECASE)
    picture_orders: set[int] = set()
    for tag in raw_tags:
        match = re.fullmatch(r"<Picture ([1-9]\d*)>", tag)
        if match is None:
            errors.append(f"{owner}: Picture 标签格式无效: {tag}")
        else:
            picture_orders.add(int(match.group(1)))
    anchor_orders = {
        int(ref["order"]) for ref in refs
        if ref.get("kind") == "REF" and ref.get("purpose") in PICTURE_ANCHOR_PURPOSES
    }
    if picture_orders - anchor_orders:
        invalid = ", ".join(f"<Picture {number}>" for number in sorted(picture_orders - anchor_orders))
        errors.append(f"{owner}: {invalid} 必须对应真实 REF 的构图、起始帧或结束帧用途")
    if anchor_orders - picture_orders:
        missing = ", ".join(f"<Picture {number}>" for number in sorted(anchor_orders - picture_orders))
        errors.append(f"{owner}: 已声明的画面锚点必须在正文中使用对应标签: {missing}")
    return picture_orders


def _dialogues(
    value: str,
    owner: str,
    errors: list[str],
    speaker_names: Optional[dict[str, str]] = None,
    subject_names: Optional[dict[str, str]] = None,
) -> list[tuple[str, str, str]]:
    result = []
    matches = list(DIALOGUE_RE.finditer(value))
    if value.count("<d>") != len(matches) or value.count("</d>") != len(matches):
        errors.append(f"{owner}: 台词必须使用完整 <d>[chinese] 原文</d> 标签")
    for match in matches:
        prefix = value[:match.start()]
        if subject_names is None:
            speaker = re.search(r"([\w\u3400-\u9fff·]+)[（(](S[1-9]\d*)(?:[^）)]*)[）)]\s*[：:]?\s*$", prefix)
            if speaker:
                name, sid = speaker.groups()
            else:
                token = re.search(r"[（(](S[1-9]\d*)[）)][^<>。！？；\n]{0,30}$", prefix)
                sid = token.group(1) if token else ""
                name = (speaker_names or {}).get(sid, "")
        else:
            canonical = re.search(
                r"<Subject ([1-9]\d*)>（(S[1-9]\d*)）([^<>。！？；\n]{0,80})[：:]\s*$",
                prefix,
            )
            if canonical:
                subject, sid, delivery = canonical.groups()
                name = (speaker_names or {}).get(sid, "")
                if subject_names.get(subject) != name:
                    errors.append(f"{owner}: Subject {subject} 与说话人 {sid} 身份不一致")
                if not delivery.strip():
                    errors.append(f"{owner}: 可见人物对白需在 <Subject N>（Sx）后直接写发声动作或语气")
            else:
                standalone = re.search(r"([\w\u3400-\u9fff·]+)（(S[1-9]\d*)）：\s*$", prefix)
                if standalone and standalone.group(1) not in set(subject_names.values()):
                    name, sid = standalone.groups()
                else:
                    errors.append(f"{owner}: 可见人物对白必须使用 <Subject N>（Sx）发声动作或语气：<d>...</d>")
                    relaxed_subject = re.search(r"<Subject ([1-9]\d*)>\s*[（(](S[1-9]\d*)(?:[^）)]*)[）)]\s*(?:[^<>。！？；\n]{0,30})?[：:]?\s*$", prefix)
                    relaxed_name = re.search(r"([\w\u3400-\u9fff·]+)[（(](S[1-9]\d*)(?:[^）)]*)[）)]\s*(?:[^<>。！？；\n]{0,30})?[：:]?\s*$", prefix)
                    if relaxed_subject:
                        subject, sid = relaxed_subject.groups()
                        name = (speaker_names or {}).get(sid, "")
                    elif relaxed_name:
                        name, sid = relaxed_name.groups()
                    else:
                        name, sid = "", ""
        if not name or not sid:
            errors.append(f"{owner}: 台词缺少可定位的说话人及 S 编号")
        text = match.group(1).strip()
        if not text or "<" in text:
            errors.append(f"{owner}: 台词为空或标签嵌套")
        result.append((name, sid, text))
    return result


def _script_scenes(document: str, errors: list[str]) -> dict[str, list[tuple[str, str]]]:
    matches = list(re.finditer(r"^## (EP\d+-SC\d+)\b[^\n]*$", _unfenced(document), re.MULTILINE))
    scenes = {}
    for index, match in enumerate(matches):
        scene = match.group(1)
        if scene in scenes:
            errors.append(f"剧本.md: 场景 ID 重复: {scene}")
        body = document[match.end():matches[index + 1].start() if index + 1 < len(matches) else None]
        dialogues = []
        pending_speaker = ""
        for line in body.splitlines():
            source = re.match(r"^\s*(?:>\s*)?(?:[-*]\s*)?(?:\[(?:VO|OS)\]\s*)?([^：:（）()\[\]\n]{1,40})(?:[（(][^）)]*[）)])?\s*[：:]\s*(.*)$", line)
            if source:
                name, words = source.groups()
                name = name.strip()
                # Screenplay speaker lines may carry a short performance cue
                # before the colon (for example, "闺蜜盯着她："). Keep the
                # stable character identity while preserving the dialogue text.
                for candidate in ("新郎父亲", "新娘", "闺蜜", "新郎"):
                    if name.startswith(candidate):
                        name = candidate
                        break
                words = words.strip()
                if words:
                    tagged = DIALOGUE_RE.fullmatch(words)
                    dialogues.append((name, tagged.group(1).strip() if tagged else words))
                    pending_speaker = ""
                else:
                    pending_speaker = name
                continue
            quoted = re.match(r"^\s*>\s*(.+)$", line)
            if quoted and pending_speaker:
                words = quoted.group(1).strip()
                tagged = DIALOGUE_RE.fullmatch(words)
                dialogues.append((pending_speaker, tagged.group(1).strip() if tagged else words))
                pending_speaker = ""
        scenes[scene] = dialogues
    return scenes


def _required(fields: dict[str, str], expected: tuple[str, ...], owner: str, errors: list[str], exact: bool = False) -> None:
    for key in expected:
        if not fields.get(key):
            errors.append(f"{owner}: 缺少非空字段: {key}")
    if exact:
        for key in fields.keys() - set(expected):
            errors.append(f"{owner}: 不允许的字段: {key}")


def _check_camera_motion(segment: dict, errors: list[str]) -> None:
    """Keep storyboard camera language aligned with the bundled H3 optimizer."""
    shots = segment["shots"]
    static_shots = 0
    for shot in shots:
        shot_id = shot["id"]
        motion = shot["fields"].get("运镜", "")
        if not any(token in motion for token in CAMERA_MOTION_TOKENS):
            errors.append(f"{shot_id}: 运镜必须使用本地 H3 优化器词表中的固定术语")
        if any(token in motion for token in STATIC_MOTION_TOKENS):
            static_shots += 1
    if shots and static_shots == len(shots):
        action_text = " ".join(shot["fields"].get("画面动作", "") for shot in shots)
        if not any(token in action_text for token in STATIC_REASON_TOKENS):
            errors.append(
                f"{segment['id']}: 动作型 SEG 不能在没有观察、证据、受困、权力压迫或文字卡职责的情况下全部使用固定机位"
            )


def _check_storyboard(segments: list[dict], scenes: dict, errors: list[str], minimum: Decimal, maximum: Decimal, selected: Optional[set[str]]) -> None:
    previous = Decimal(0)
    pointers: dict[str, int] = {}
    voices: dict[str, str] = {}
    names: dict[str, str] = {}
    expected_voices: dict[str, str] = {}
    for segment in segments:
        for shot in segment["shots"]:
            for name, _, _ in _dialogues(shot["fields"].get("台词", ""), shot["id"], []):
                if name and name not in expected_voices:
                    expected_voices[name] = f"S{len(expected_voices) + 1}"
    for segment in segments:
        if selected is not None and segment["id"] not in selected:
            earlier_interval = _interval(segment["fields"].get("全局时间", ""), global_time=True)
            previous = earlier_interval[1] if earlier_interval else None
            continue
        sid, fields = segment["id"], segment["fields"]
        _required(fields, SEG_FIELDS, sid, errors, False)
        for key in fields.keys() - set(SEG_FIELDS) - set(SEG_OPTIONAL_FIELDS):
            errors.append(f"{sid}: 不允许的字段: {key}")
        placeholder = fields.get("参考图占位", "").strip()
        if "参考图占位" in fields:
            if not placeholder:
                errors.append(f"{sid}: 参考图占位不能为空")
            if "REF-" in placeholder or "PLAN-" in placeholder:
                errors.append(f"{sid}: 参考图占位不能写真实 REF/PLAN，实际绑定归 MOTION")
        source = fields.get("来源", "")
        if source not in scenes:
            errors.append(f"{sid}: 来源必须是剧本中一个存在的场景 ID: {source}")
        duration = _duration(fields.get("时长", ""))
        if duration is None or duration <= 0 or not minimum <= duration <= maximum:
            errors.append(f"{sid}: 时长必须是 {minimum}–{maximum}s 内的有限正数，且不超过 15s")
        interval = _interval(fields.get("全局时间", ""), global_time=True)
        if not interval:
            errors.append(f"{sid}: 全局时间必须是递增有限时间区间")
        else:
            if duration is not None and interval[1] - interval[0] != duration:
                errors.append(f"{sid}: 全局时间差与段时长不一致")
            if previous is not None and interval[0] != previous:
                errors.append(f"{sid}: 全局时间必须从 0 连续，无重叠、无空洞")
            previous = interval[1]
        if not segment["shots"]:
            errors.append(f"{sid}: 至少需要一个 SHOT")
        end = Decimal(0)
        for shot in segment["shots"]:
            shot_id, shot_fields = shot["id"], shot["fields"]
            if re.search(r"冻结关键帧提示词|图片提示词", shot["body"]):
                errors.append(f"{shot_id}: SHOT 不得包含图片提示词或冻结关键帧；请移到 SEG 的段首冻结关键帧提示词")
            _required(shot_fields, SHOT_FIELDS, shot_id, errors, True)
            local = _interval(shot_fields.get("时间", ""))
            if local is None:
                errors.append(f"{shot_id}: 时间必须是递增有限秒数区间")
            else:
                if local[0] != end:
                    errors.append(f"{shot_id}: 时间必须从 0 连续，无重叠、无空洞")
                end = local[1]
            words = shot_fields.get("台词", "")
            lines = _dialogues(words, shot_id, errors)
            if words != "无" and not lines:
                errors.append(f"{shot_id}: 台词必须写带说话人的 <d> 原句，无台词写 无")
            shot["dialogues"] = lines
            for name, voice, text in lines:
                if expected_voices.get(name) != voice:
                    errors.append(
                        f"{shot_id}: 说话人编号必须按目标视频首次发声顺序排列；"
                        f"{name} 应为 {expected_voices.get(name)}，当前为 {voice}"
                    )
                if voice in voices and voices[voice] != name or name in names and names[name] != voice:
                    errors.append(f"{shot_id}: 台词说话人与 S 编号身份不稳定")
                voices[voice], names[name] = name, voice
                source_lines = scenes.get(source, [])
                pointer = pointers.get(source, 0)
                found = next((i for i in range(pointer, len(source_lines)) if source_lines[i] == (name, text)), None)
                if found is None:
                    errors.append(f"{shot_id}: 台词说话人、原句、次数或顺序与来源场次不一致: {name}：{text}")
                else:
                    pointers[source] = found + 1
        if duration is not None and end != duration:
            errors.append(f"{sid}: SHOT 时间总和/末尾必须严格等于段时长")
        _check_camera_motion(segment, errors)


def _prompt_parts(prompt: str, owner: str, errors: list[str]) -> dict[str, str]:
    matches = list(re.finditer(r"^([a-z_]+):[ \t]*", prompt, re.MULTILINE))
    if [match.group(1) for match in matches] != list(PROMPT_FIELDS):
        errors.append(f"{owner}: 六段式字段必须齐备、唯一且顺序正确")
    parts = {}
    for index, match in enumerate(matches):
        parts[match.group(1)] = prompt[match.end():matches[index + 1].start() if index + 1 < len(matches) else None].strip()
    if matches and prompt[:matches[0].start()].strip():
        errors.append(f"{owner}: 六段式之前不能夹入说明")
    for field in PROMPT_FIELDS:
        if not parts.get(field):
            errors.append(f"{owner}: 六段式缺少非空内容: {field}")
        elif field != "non_diegetic_music" and not re.search(r"[\u3400-\u9fff]", parts[field]):
            errors.append(f"{owner}: {field} 缺少中文正文")
    return parts


def _subject_map(text: str, visuals: dict[str, str], owner: str, errors: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    subjects, voices = {}, {}
    # Independent voice declarations must not be absorbed into the last
    # visual Subject's multiline description.
    standalone = re.compile(r"^[ \t]*(?:[-*+]\s+)?([\w\u3400-\u9fff·]+)[ \t]*[（(](S[1-9]\d*)[）)]([^\n]*)$", re.MULTILINE)
    for voice_match in standalone.finditer(text):
        name, voice, description = voice_match.groups()
        if voice in voices:
            errors.append(f"{owner}: 说话人 {voice} 身份重复或冲突")
        if not re.search(r"[\u3400-\u9fff]", description):
            errors.append(f"{owner}: 独立说话人 {voice} 缺少稳定声音描述")
        voices[voice] = name
    text = standalone.sub(lambda match: " " * len(match.group(0)), text)
    # Standalone Picture definition lines are frame anchors, not Subject
    # identity text; drop them before resolving Subject identity names.
    text = re.sub(r"^<Picture [1-9]\d*>.*$", "", text, flags=re.MULTILINE)
    definitions = list(re.finditer(r"<Subject ([1-9]\d*)>", text))
    for index, match in enumerate(definitions):
        body = text[match.end():definitions[index + 1].start() if index + 1 < len(definitions) else None]
        exact_pairs = re.findall(r"(人物|造型|地点|道具)「([^」]+)」", body)
        exact = [name for _, name in exact_pairs]
        names = exact or [name for name in visuals if name in body]
        if len(names) != 1 or names[0] not in visuals:
            errors.append(f"{owner}: Subject {match.group(1)} 身份无法唯一定位到视觉设定条目")
            continue
        if any(visuals.get(name) != category for category, name in exact_pairs):
            errors.append(f"{owner}: Subject {match.group(1)} 视觉设定类别不一致")
        subject, name = match.group(1), names[0]
        if subject in subjects or name in subjects.values():
            errors.append(f"{owner}: Subject 身份重复或冲突")
        subjects[subject] = name
        for voice in re.findall(r"[（(](S[1-9]\d*)[）)]", body):
            if voice in voices:
                errors.append(f"{owner}: 说话人 {voice} 身份重复或冲突")
            voices[voice] = name
    if not definitions and not voices:
        errors.append(f"{owner}: subject_definitions 缺少 Subject 或独立声音定义")
    return subjects, voices


def _global_parts(head: str, errors: list[str]) -> dict[str, str]:
    matches = list(re.finditer(r"^(" + "|".join(GLOBAL_FIELDS) + r"):[ \t]*", head, re.MULTILINE))
    result = {}
    for index, match in enumerate(matches):
        key = match.group(1)
        if key in result:
            errors.append(f"视频提示词.md: 全局主题定义字段重复: {key}")
        result[key] = head[match.end():matches[index + 1].start() if index + 1 < len(matches) else None].strip()
    return result


def _check_retention(value: str, owner: str, *, subjects: dict[str, str], refs: list[dict], fields: dict[str, str], shot_count: int, errors: list[str]) -> None:
    no_external = not refs and not any(_has_media(fields.get(key, "")) for key in MEDIA_FIELDS)
    if fields.get("生成方式") == "文生视频" and no_external and not re.search(r"<(?:Subject|Picture|Video|Audio)\b", value):
        # Text-only requests may describe accepted text facts without claiming
        # that they preserve a supplied image or sound.
        return
    pattern = re.compile(r"<(Subject|Picture|Video|Audio) ([1-9]\d*)> \(appears in (\[Shot [1-9]\d*\](?:, \[Shot [1-9]\d*\])*)\): ([a-z_]+) - (.+)")
    seen = set()
    for line in value.splitlines():
        if not line.strip():
            continue
        match = pattern.fullmatch(line.strip())
        if not match:
            errors.append(f"{owner}: retention_analysis 必须逐行包含引用、出现镜次、固定保留枚举与说明")
            continue
        kind, number, shots, mode, description = match.groups()
        key = (kind, number)
        if key in seen:
            errors.append(f"{owner}: retention 引用重复: {kind} {number}")
        seen.add(key)
        if mode not in RETENTION_MODES[kind]:
            errors.append(f"{owner}: retention 的 {kind} 保留枚举无效: {mode}")
        numbers = [int(number) for number in re.findall(r"\[Shot ([1-9]\d*)\]", shots)]
        if len(numbers) != len(set(numbers)) or numbers != sorted(numbers) or any(number > shot_count for number in numbers):
            errors.append(f"{owner}: retention 出现镜次重复、越界或顺序错误")
        known = number in subjects if kind == "Subject" else int(number) in {ref["order"] for ref in refs} if kind == "Picture" else number == "1" and _has_media(fields.get("续接视频" if kind == "Video" else "输入音频", ""))
        if not known:
            errors.append(f"{owner}: retention 指向未定义的 {kind} {number}")
        if not re.search(r"[\u3400-\u9fff]", description) or re.search(r"[（(]S[1-9]\d*[）)]", description):
            errors.append(f"{owner}: retention 需中文职责说明，且不得使用说话人 S 标签")


def _check_shot_subject_binding(body: str, owner: str, subjects: dict[str, str], errors: list[str]) -> None:
    """Require H3 shot prose to bind visible actions directly to Subject labels."""
    visual = DIALOGUE_RE.sub("", body)
    if re.search(r"(?:画面主体为|画面主体[：:]|本镜主体[：:]|画面动作[：:]|台词[：:])", visual):
        errors.append(f"{owner}: SHOT 不能先写主体清单；应把 <Subject N> 直接写入构图、动作和发声句")

    first_sentence = re.split(r"[。！？\n]", visual, maxsplit=1)[0]
    non_subject_frame = re.search(r"(?:黑屏|纯黑|文字卡|定帧)", first_sentence)
    if not non_subject_frame and not re.search(r"<Subject [1-9]\d*>", first_sentence):
        errors.append(f"{owner}: SHOT 开头必须用 <Subject N> 建立具体构图或动作锚点")

    for number, name in subjects.items():
        if name and name in visual:
            errors.append(
                f"{owner}: SHOT 内不得用身份名称“{name}”代替 <Subject {number}>；"
                "动作、位置和视线关系必须直接绑定 Subject"
            )


def _carries_surface(text: str, surface: str) -> bool:
    for match in re.finditer(re.escape(surface), text, re.IGNORECASE):
        if not NEGATION_RE.search(text[:match.start()]):
            return True
    return False


def _locks(visual: str, segments: list[dict], selected: Optional[set[str]], prompts: dict[str, dict], errors: list[str]) -> None:
    seg_by_id = {seg["id"]: seg for seg in segments}
    shot_parent = {shot["id"]: seg for seg in segments for shot in seg["shots"]}
    seen = set()
    for line in visual.splitlines():
        if not re.match(r"^\s*[-*+]\s*连续性锁[：:]", line):
            continue
        match = re.fullmatch(r"\s*[-*+]\s*连续性锁：(LOCK-[A-Z0-9-]+)《[^》]+》（镜头：([^；）]+)(?:；图片提示词项：[^）]+)?）· 锁面：(.+)", line)
        if not match:
            errors.append("视觉设定.md: 连续性锁语法不完整")
            continue
        lock_id, scope, surface = match.groups()
        if lock_id in seen:
            errors.append(f"{lock_id}: 连续性锁 ID 重复")
        seen.add(lock_id)
        targets = list(seg_by_id) if scope == "全集" else [item.strip() for item in re.split(r"[、,，]", scope)]
        for target in targets:
            segment = seg_by_id.get(target) or shot_parent.get(target)
            if segment is None:
                errors.append(f"{lock_id}: 连续性锁范围不存在: {target}")
                continue
            if selected is not None and segment["id"] not in selected:
                continue
            shots = segment["shots"] if target in seg_by_id else [shot for shot in segment["shots"] if shot["id"] == target]
            first = segment["shots"][:1]
            if any(shot in first for shot in shots):
                freeze = _copyable_prompt(segment["body"], "段首冻结关键帧提示词")
                if freeze is not None and bool(re.search(r"[\u3400-\u9fff]", freeze)) == bool(re.search(r"[\u3400-\u9fff]", surface)) and not _carries_surface(freeze, surface.rstrip("。")):
                    errors.append(f"{lock_id}: {segment['id']} 段首冻结正文缺少锁面")
            motion_parts = prompts.get(segment["id"], {})
            for shot in shots:
                projected = motion_parts.get(shot["id"])
                if projected is not None and re.search(r"[\u3400-\u9fff]", surface) and not _carries_surface(projected, surface.rstrip("。")):
                    errors.append(f"{lock_id}: {shot['id']} 对应视频正文缺少锁面")


def _read(path: Path, errors: list[str], required: bool = True) -> str:
    descriptor = None
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("not a regular non-symlink document")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("not a regular document")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            return stream.read()
    except (OSError, UnicodeError, ValueError) as exc:
        if required:
            errors.append(f"{path.name}: 文档缺失或不可读: {exc}")
        return ""
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _has_media(value: str) -> bool:
    return value.strip() not in {"", "无", "N/A"}


def _profile(root: Path, level: str, errors: list[str]) -> tuple[Decimal, Decimal, str]:
    path = root / "short-drama.json"
    if not path.is_file():
        if level == "handoff":
            errors.append("交接需要 short-drama.json 中已接受的新套件档案与画幅")
        return Decimal(0), Decimal(15), ""


    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        authority = data.get("creator_authority", {})
        profile = authority.get("production_profile", {})
        choices = profile.get("choices", {})
        aspect = data.get("format", {}).get("aspect_ratio", "")
        if not isinstance(choices, dict) or not isinstance(aspect, str):
            raise ValueError("档案形状错误")
        expected = {"workflow_suite": "short-drama-h3", "storyboard_unit": "video_segment", "video_prompt_language": "zh", "target_video_model": "minimax-h3", "video_prompt_dialect": "minimax-h3-segmented"}
        for key, value in expected.items():
            if key in choices and choices[key] != value or level == "handoff" and choices.get(key) != value:
                errors.append(f"项目档案模式冲突或缺项: {key} 应为 {value}")
        if level == "handoff" and (profile.get("status") != "accepted" or not aspect):
            errors.append("交接需要已接受的新套件档案及非空画幅")
        duration = choices.get("native_duration_seconds", {})
        low, high = _seconds(str(duration.get("min", 0))), _seconds(str(duration.get("max", 15)))
        if low is None or high is None or low > high or high <= 0:
            raise ValueError("native_duration_seconds 必须为有限递增范围")
        return low, min(high, Decimal(15)), aspect
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
        errors.append(f"short-drama.json: 档案不可读或无效: {exc}")
        return Decimal(0), Decimal(15), ""


def _prompt_style_profile(root: Path, errors: list[str]) -> tuple[bool, bool, dict[str, Any]]:
    path = root / "short-drama.json"
    if not path.is_file():
        return False, False, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        authority = data.get("creator_authority", {})
        if not isinstance(authority, dict) or "prompt_style" not in authority:
            return False, False, {}
        profile = authority.get("prompt_style")
        if not isinstance(profile, dict):
            raise ValueError("prompt_style must be an object")
        if profile.get("status") != "accepted":
            return True, False, {}
        choices = profile.get("choices")
        if not isinstance(choices, dict):
            raise ValueError("prompt_style choices must be an object")
        for field in ("style_and_tone_lock", "preprompt_rules", "image_prompt_lock"):
            if not isinstance(choices.get(field), str) or not choices[field].strip():
                raise ValueError(f"prompt_style.{field} is missing")
        negative_rules = choices.get("negative_visual_rules")
        if not isinstance(negative_rules, list) or any(
            not isinstance(item, str) or not item.strip() for item in negative_rules
        ):
            raise ValueError("prompt_style.negative_visual_rules must be a list")
        return True, True, choices
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
        errors.append(f"short-drama.json: 全局提示词风格档案无效: {exc}")
        return True, False, {}


def check_episode(episode: Path, project_root: Optional[Path] = None, *, stage: str = "all", level: str = "structure", motion: Optional[str] = None) -> dict:
    if stage not in {"storyboard", "video", "all"} or level not in {"structure", "complete", "handoff"}:
        raise ValueError("stage/level 不在支持的范围")
    episode = Path(episode).resolve()
    root = Path(project_root).resolve() if project_root else episode.parent.parent
    errors: list[str] = []
    gaps: list[str] = []
    if not _inside(episode, root):
        errors.append("剧集目录必须位于项目根目录内")
    minimum, maximum, aspect = _profile(root, level, errors)
    has_prompt_style, prompt_style_accepted, prompt_style = _prompt_style_profile(root, errors)
    if (
        has_prompt_style
        and not prompt_style_accepted
        and level in {"complete", "handoff"}
        and stage in {"video", "all"}
    ):
        errors.append("视频提示词交接需要已接受的 creator_authority.prompt_style")
    storyboard = _read(episode / "分镜.md", errors)
    script = _read(episode / "剧本.md", errors)
    visual = _read(episode / "视觉设定.md", errors, stage != "storyboard" and level != "structure")
    segments = parse_storyboard(storyboard, errors)
    scenes = _script_scenes(script, errors)
    if not segments:
        errors.append("分镜.md: 没有 SEG 条目；H3 套件不接受旧 H2 SHOT 结构")
    video = _read(episode / "视频提示词.md", errors, stage == "video" or level != "structure") if stage != "storyboard" else ""
    motions = parse_motions(video, errors)
    selected_motions = [item for item in motions if motion is None or item["id"] == motion]
    selected_segments = {item["fields"].get("分镜段", "") for item in selected_motions} if motion else None
    if motion and not selected_motions:
        errors.append(f"视频提示词.md: 点名 MOTION 不存在: {motion}")
    _check_storyboard(segments, scenes, errors, minimum, maximum, selected_segments)
    seg_by_id = {item["id"]: item for item in segments}
    motion_targets: dict[str, list[str]] = {}
    for item in motions:
        motion_targets.setdefault(item["fields"].get("分镜段", ""), []).append(item["id"])
    for target, items in motion_targets.items():
        if len(items) > 1 and (selected_segments is None or target in selected_segments):
            errors.append(f"{target}: 一个 SEG 被多个 MOTION 引用: {', '.join(items)}")
    if stage != "storyboard" and level != "structure":
        for seg in segments:
            if (selected_segments is None or seg["id"] in selected_segments) and not motion_targets.get(seg["id"]):
                errors.append(f"{seg['id']}: 缺少对应 MOTION")
    if stage != "storyboard" and not motions:
        (gaps if level == "structure" else errors).append("视频提示词.md: 没有 MOTION 条目")
    head = re.split(r"^## MOTION-", video, maxsplit=1, flags=re.MULTILINE)[0]
    visuals = {match.group(2).strip(): match.group(1) for match in re.finditer(r"^## (人物|造型|地点|道具) · (.+)$", visual, re.MULTILINE)}
    global_subjects: dict[str, str] = {}
    global_voices: dict[str, str] = {}
    global_parts = _global_parts(head, errors)
    if prompt_style_accepted and stage != "storyboard":
        for field in ("preprompt_rules", "style_and_tone_lock"):
            if global_parts.get(field, "") != prompt_style[field]:
                errors.append(f"视频提示词.md: {field} 必须逐字复用已接受的项目 prompt_style")
    if global_parts.get("subject_definitions"):
        global_subjects, global_voices = _subject_map(global_parts["subject_definitions"], visuals, "主题定义", errors)
    mapping_pattern = re.compile(
        r"^(MOTION-[A-Z0-9-]+) \+ ((?:REF|PLAN)-[A-Z0-9-]+) \+ "
        r"((?:<Subject [1-9]\d*>(?:, )?)+) \+ ([1-9]\d*)[ \t]*$",
        re.MULTILINE,
    )
    mappings = []
    for match in mapping_pattern.finditer(head):
        owner, ref_id, subject_text, order = match.groups()
        subjects = tuple(int(number) for number in re.findall(r"<Subject ([1-9]\d*)>", subject_text))
        mappings.append((owner, ref_id, subjects, order))
    # Read the pre-migration Picture mapping so existing projects can still be
    # reviewed. New projects use the Subject mapping above and are strict.
    legacy_mappings = re.findall(
        r"^(MOTION-[A-Z0-9-]+) \+ ((?:REF|PLAN)-[A-Z0-9-]+) \+ "
        r"([1-9]\d*) \+ <Picture ([1-9]\d*)>[ \t]*$",
        head, re.MULTILINE,
    )
    prompt_shots: dict[str, dict[str, str]] = {}
    for item in selected_motions:
        owner, fields, prompt = item["id"], item["fields"], item["prompt"]
        _required(fields, ("分镜段", "准备状态"), owner, errors)
        for key in set(fields) & {"分镜", "图片提示词项", "视觉依据", "提交状态", "输入参考视频", "输入参考音频"}:
            errors.append(f"{owner}: 不支持旧契约字段: {key}")
        segment = seg_by_id.get(fields.get("分镜段", ""))
        if segment is None:
            errors.append(f"{owner}: 分镜段必须引用存在的 SEG")
            continue
        state = re.split(r"[（(;；]", fields.get("准备状态", ""), maxsplit=1)[0].strip()
        if state not in STATES:
            errors.append(f"{owner}: 未知准备状态: {state}")
        full = level != "structure" or state == "可交接"
        if full:
            _required(fields, MOTION_FIELDS, owner, errors)
        else:
            for key in MOTION_FIELDS:
                if not fields.get(key):
                    gaps.append(f"{owner}: 待补 {key}")
        if state != "可交接":
            gaps.append(f"{owner}: 准备状态 {state}，尚不可交接")
            if level == "handoff":
                errors.append(f"{owner}: 只有 可交接 状态可交接，当前为 {state}")
        if level == "complete" and state not in {"可交接", "外部挂图计划"}:
            errors.append(f"{owner}: 当前准备状态仍有待补内容: {state}")
        if "时长" in fields and _duration(fields["时长"]) != _duration(segment["fields"].get("时长", "")):
            errors.append(f"{owner}: 时长与 SEG 不一致")
        for key in ("段首状态", "段尾交接"):
            if key in fields and fields[key] != segment["fields"].get(key):
                errors.append(f"{owner}: {key} 与 SEG 不一致")
        if "成员分镜" in fields:
            members = re.findall(r"(SHOT-[A-Z0-9-]+)（([^）]+)）", fields["成员分镜"])
            leftover = re.sub(r"SHOT-[A-Z0-9-]+（[^）]+）", "", fields["成员分镜"]).strip("； ")
            expected = [(shot["id"], _interval(shot["fields"].get("时间", ""))) for shot in segment["shots"]]
            if leftover or [(sid, _interval(timing)) for sid, timing in members] != expected:
                errors.append(f"{owner}: 成员分镜的数量、顺序或时间与 SEG 不一致")
        reference_value = fields.get("输入参考图", "")
        refs = parse_references(reference_value, root, owner, full, errors)
        if not full:
            for ref in refs:
                if ref["path"]:
                    reference_gaps: list[str] = []
                    _file(ref["path"], root, owner, reference_gaps, True)
                    gaps.extend(reference_gaps)
        planned = any(ref["kind"] == "PLAN" for ref in refs)
        missing = "待补参考图" in reference_value
        if planned:
            gaps.append(f"{owner}: PLAN 外部挂图计划尚无真实素材")
            if state != "外部挂图计划" or level == "handoff":
                errors.append(f"{owner}: PLAN 只能保留为外部挂图计划，不能交接")
        if missing:
            gaps.append(f"{owner}: {reference_value}")
            if prompt is not None or full:
                errors.append(f"{owner}: 缺少必要参考图时不能给出最终可复制提示词")
        mode = fields.get("生成方式", "")
        if mode and mode not in {"图生视频", "文生视频"}:
            errors.append(f"{owner}: 生成方式应表达图生视频或明确文生视频意图")
        if mode == "文生视频":
            anchor = fields.get("静态视觉锚点", "")
            if reference_value != EXPLICIT_TEXT_TO_VIDEO or refs:
                errors.append(f"{owner}: 文生视频必须记录创作者已明确选择，不能静默降级")
            if full and (not anchor or not prompt or anchor not in prompt):
                errors.append(f"{owner}: 文生视频缺少完整投影的静态视觉锚点")
        elif full and not refs and not (_has_media(fields.get("续接视频", "")) and _has_media(fields.get("实际尾帧", ""))):
            errors.append(f"{owner}: 图生视频需要真实 REF 或外部 PLAN，不能静默改文生")
        if _has_media(fields.get("续接视频", "")) != _has_media(fields.get("实际尾帧", "")):
            missing_media = "实际尾帧" if _has_media(fields.get("续接视频", "")) else "续接视频"
            message = f"{owner}: 续接视频与实际尾帧必须成对声明，待补{missing_media}"
            (gaps if not full and state == "待续接" else errors).append(message)
        for key in MEDIA_FIELDS:
            if _has_media(fields.get(key, "")):
                _file(fields[key], root, f"{owner} {key}", errors, full)
        start = fields.get("起始帧", "")
        start_refs = [ref for ref in refs if ref["purpose"] == "起始帧"]
        if start_refs and start_refs[0]["id"] not in start:
            errors.append(f"{owner}: 起始帧字段必须指向已列的起始帧参考")
        for ref_id in re.findall(r"(?:REF|PLAN)-[A-Z0-9-]+", start):
            if ref_id not in {ref["id"] for ref in start_refs}:
                errors.append(f"{owner}: 起始帧指向不存在或用途错误的参考: {ref_id}")
        if prompt is None:
            (errors if full else gaps).append(f"{owner}: 缺少唯一且非空的可复制提示词")
            continue
        parts = _prompt_parts(prompt, owner, errors)
        for field in GLOBAL_FIELDS:
            if not re.search(rf"^{field}:", head, re.MULTILINE):
                errors.append(f"视频提示词.md: 全局主题定义缺少 {field}")
        if aspect and aspect not in head:
            errors.append("视频提示词.md: preprompt 未包含项目画幅")
        check_picture_reference_bindings(prompt, refs, owner, errors)
        for tag, field in (("Video", "续接视频"), ("Audio", "输入音频")):
            tokens = re.findall(rf"<{tag} ([^>]+)>", prompt)
            if any(number != "1" for number in tokens) or tokens and not _has_media(fields.get(field, "")):
                errors.append(f"{owner}: {tag} 标签只允许 1，且必须绑定实际{field}")
        local_subjects, local_voices = _subject_map(parts.get("subject_definitions", ""), visuals, owner, errors)
        actual_map = [row for row in mappings if row[0] == owner]
        expected_map = [(owner, ref["id"], str(ref["order"])) for ref in refs]
        if not actual_map:
            legacy_map = [row for row in legacy_mappings if row[0] == owner]
            expected_legacy = [(owner, ref["id"], str(ref["order"]), str(ref["order"])) for ref in refs]
            if legacy_map != expected_legacy:
                errors.append(f"{owner}: 全局 ref_mapping 必须为每个 REF/PLAN 提供一条 Subject 生产映射")
        else:
            if len(actual_map) != len(expected_map):
                errors.append(f"{owner}: 全局 ref_mapping 必须为每个 REF/PLAN 提供一条 Subject 生产映射")
            for actual, expected in zip(actual_map, expected_map):
                _, ref_id, subject_numbers, order = actual
                expected_owner, expected_ref, expected_order = expected
                if ref_id != expected_ref or order != expected_order or not subject_numbers:
                    errors.append(f"{owner}: 全局 ref_mapping 的 REF/PLAN 顺序或 Subject 映射不一致")
                elif any(str(number) not in local_subjects for number in subject_numbers):
                    errors.append(f"{owner}: ref_mapping 指向了本段未定义的 Subject")
        _check_retention(parts.get("retention_analysis", ""), owner, subjects=local_subjects, refs=refs, fields=fields, shot_count=len(segment["shots"]), errors=errors)
        if not set(re.findall(r"<Subject ([1-9]\d*)>", prompt)).issubset(local_subjects):
            errors.append(f"{owner}: 提示词使用了未定义的 Subject 身份")
        for number, name in local_subjects.items():
            if global_subjects.get(number) != name:
                errors.append(f"{owner}: Subject {number} 与全局身份不一致")
        for number, name in local_voices.items():
            if global_voices.get(number) != name:
                errors.append(f"{owner}: 说话人 {number} 与全局身份不一致")
        for subject, voice in re.findall(r"<Subject ([1-9]\d*)>\s*[（(](S[1-9]\d*)[）)]", prompt):
            if local_subjects.get(subject) != local_voices.get(voice):
                errors.append(f"{owner}: Subject {subject} 与说话人 {voice} 身份不一致")
        expected_dialogues = [dialogue for shot in segment["shots"] for dialogue in shot.get("dialogues", [])]
        detailed = parts.get("detailed_description", "")
        for number, name in local_subjects.items():
            if re.search(rf"<Subject {number}>\s+{re.escape(name)}", detailed):
                errors.append(f"{owner}: SHOT 内 Subject 标签后不得重复角色或资产名称: <Subject {number}> {name}")
        actual_dialogues = _dialogues(prompt, owner, errors, local_voices, local_subjects)
        if actual_dialogues != expected_dialogues:
            errors.append(f"{owner}: 台词说话人、原句、次数或顺序与 SEG 不一致")
        for dialogue, expected_count in Counter(text for _, _, text in expected_dialogues).items():
            if prompt.count(dialogue) != expected_count:
                errors.append(f"{owner}: 台词原句在正文中被重复抄写或丢失: {dialogue}")
        for name, voice, _ in actual_dialogues:
            if local_voices.get(voice) != name:
                errors.append(f"{owner}: 台词说话人与 subject_definitions 不一致")
        style_lock = global_parts.get("style_and_tone_lock", "")
        if full and (not style_lock or not detailed.startswith(style_lock)):
            errors.append(f"{owner}: detailed_description 开头必须逐字复用全局 style_and_tone_lock")
        shot_marks = list(re.finditer(r"\[Shot ([1-9]\d*)\]", detailed))
        if [int(mark.group(1)) for mark in shot_marks] != list(range(1, len(segment["shots"]) + 1)):
            errors.append(f"{owner}: Shot 数量、编号、位置与成员分镜不一致")
        projected = {}
        for index, (mark, shot) in enumerate(zip(shot_marks, segment["shots"])):
            body = detailed[mark.end():shot_marks[index + 1].start() if index + 1 < len(shot_marks) else None]
            projected[shot["id"]] = body
            _check_shot_subject_binding(body, f"{owner} Shot {index + 1}", local_subjects, errors)
            cut = re.match(r"\s*At\s+([\d:.]+)", body)
            shot_interval = _interval(shot["fields"].get("时间", ""))
            if shot_interval and (index > 0 and cut is None or cut is not None and _timestamp(cut.group(1)) != shot_interval[0]):
                errors.append(f"{owner}: Shot {index + 1} 切点与 SHOT 时间不一致")
            for key in ("景别", "运镜"):
                expected = shot["fields"].get(key, "")
                present = expected in body
                if key == "景别" and not present:
                    present = _compact_camera_text(expected) in _compact_camera_text(body)
                if not present:
                    errors.append(f"{owner}: Shot {index + 1} 缺少对应{key}")
            if _dialogues(body, f"{owner} Shot {index + 1}", errors, local_voices, local_subjects) != shot.get("dialogues", []):
                errors.append(f"{owner}: Shot {index + 1} 台词被移动、改写或重复")
        prompt_shots[segment["id"]] = projected
    _locks(visual, segments, selected_segments, prompt_shots, errors)
    errors = list(dict.fromkeys(errors))
    return {
        "ok": not errors, "stage": stage, "level": level, "scope": {"motion": motion},
        "errors": errors, "gaps": list(dict.fromkeys(gaps)),
        "unchecked": ["表演时长、动作可生成性与镜头语言质量", "参考图片的真实内容、身份、造型、控制范围及适用性", "跨段语义连续性、冻结画面时态与锁面冲突", "连续性锁的跨语言等义投影", "实际媒体质量与外部视频生成预检", "整集目标时长及未拍场景覆盖（首版暂缓）"],
        "segments": segments, "motions": selected_motions,
    }


def validate_episode(episode: Path, project_root: Optional[Path] = None) -> list[str]:
    """Compatibility API: return deterministic errors, allowing in-progress work."""
    return check_episode(episode, project_root)["errors"]


def main(argv: Optional[list[str]] = None, *, default_stage: str = "all") -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path, help="剧集 Markdown 目录")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--stage", choices=("storyboard", "video", "all"), default=default_stage)
    parser.add_argument("--level", choices=("structure", "complete", "handoff"), default="structure")
    parser.add_argument("--motion", help="只检查点名 MOTION 及其来源 SEG")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    result = check_episode(args.episode, args.project_root, stage=args.stage, level=args.level, motion=args.motion)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("OK: 机械检查通过" if result["ok"] else "ERROR: 机械检查未通过")
        for key, prefix in (("errors", "ERROR"), ("gaps", "GAP"), ("unchecked", "UNCHECKED")):
            for message in result[key]:
                print(f"{prefix}: {message}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
