#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render an interview debrief Markdown document from review.json.

Zero third-party dependencies (Python standard library only).
Cross-platform: Windows / macOS / Linux.

Usage:
    python build_doc.py review.json [--out DIR] [--record RECORD.md] [--force]

Input : a structured review.json (schema documented in references/doc-template.md)
Output: <out>/<date>-<company>-<role>-<round>.md    the debrief document
        <out>/<date>-<company>-<role>-<round>.json  a copy of review.json
        <out>/<date>-<company>-<role>-<round>.记录.md   the confirmed record (if --record)
        Missing meta segments are omitted from the file name.
        <out> defaults to "./面试复盘" (relative to the current directory).

Before rendering, the sibling validate_review.py gate runs automatically
(structure + iron rules + coverage). Errors abort rendering unless
--no-validate is given. Warnings are printed but do not block.

Existing .md files are never overwritten unless --force is given.

Section numbers are assigned sequentially, so when a conditional section is
skipped (e.g. materials without answers have no "我的整体表现评价"), the
remaining sections stay densely numbered.

Exit codes:
    0  success (output paths are printed to stdout, one per line, tagged)
    1  input error (missing file / invalid JSON / gate failure / would overwrite)
"""

import argparse
import json
import os
import re
import sys
from datetime import date as _date

OUT_DIR_DEFAULT = "面试复盘"
ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _str(value):
    """Coerce any JSON value into a trimmed string ('' for empty/missing)."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        parts = [_str(v) for v in value]
        return "、".join(p for p in parts if p)
    return str(value).strip()


def _clean_filename_part(value):
    part = ILLEGAL_FILENAME_CHARS.sub("-", _str(value))
    return part.strip(" -.~")


def _quote(text):
    lines = [ln.rstrip() for ln in _str(text).splitlines()]
    if not lines:
        return []
    return [("> " + ln) if ln else ">" for ln in lines]


def _bullets(items):
    out = []
    for it in items or []:
        s = _str(it)
        if s:
            out.append("- " + s)
    return out


def _numbered(items):
    out = []
    n = 0
    for it in items or []:
        s = _str(it)
        if s:
            n += 1
            out.append("%d. %s" % (n, s))
    return out


def _trim(lines):
    """Drop leading/trailing blank lines."""
    out = list(lines)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


# --------------------------------------------------------------------------
# file name
# --------------------------------------------------------------------------

def make_filename(meta, today=None):
    today = today or _date.today().isoformat()
    parts = [_clean_filename_part(meta.get("date")) or today]
    for key in ("company", "role", "round"):
        seg = _clean_filename_part(meta.get(key))
        if seg:
            parts.append(seg)
    return "-".join(parts) + ".md"


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _render_question(idx, q):
    lines = []

    question = _str(q.get("question")) or "（问题缺失）"
    lines.append("")
    lines.append("### Q%d. %s" % (idx, question))
    lines.append("")

    # category
    cat = _str(q.get("category"))
    sub = _str(q.get("subcategory"))
    shown = " / ".join(p for p in (cat, sub) if p)
    if shown:
        lines.append("**分类**：" + shown)
        lines.append("")

    # interviewer intent (compact: one core sentence + optional extra)
    intent = q.get("intent") or {}
    core = _str(intent.get("core"))
    extra = _str(intent.get("extra"))
    if not core:
        # tolerate the legacy schema (fact / inference / alternative)
        core = " ".join(p for p in (_str(intent.get("fact")),
                                   _str(intent.get("inference"))) if p)
        if not extra:
            extra = _str(intent.get("alternative"))
    if core or extra:
        lines.append("**面试官意图**：" + (core or extra))
        if core and extra:
            lines.append("")
            lines.append("补充：" + extra)
        lines.append("")

    # my answer (optional)
    answer = _str(q.get("answer"))
    if answer:
        lines.append("**我的回答**")
        lines.append("")
        lines.extend(_quote(answer))
        lines.append("")

    # review (optional; only when there is an answer)
    review = q.get("review")
    if isinstance(review, dict) and answer:
        hit = _str(review.get("hit"))
        lines.append("**评价**" + ("（%s）" % hit if hit else ""))
        lines.append("")
        if _str(review.get("points")):
            lines.append("- 踩中考点：" + _str(review.get("points")))
        if _str(review.get("missing")):
            lines.append("- 遗漏：" + _str(review.get("missing")))
        if _str(review.get("delivery")):
            lines.append("- 表达与结构：" + _str(review.get("delivery")))
        if _str(review.get("top_fix")):
            lines.append("- **最该改的一处**：" + _str(review.get("top_fix")))
        lines.append("")

    # better answer — a reference answer is mandatory; guidance / outline /
    # variants are optional extras
    ba = q.get("better_answer") or {}
    sample = _str(ba.get("sample"))
    guidance = _str(ba.get("guidance")) or _str(ba.get("direction"))
    outline = _numbered(ba.get("outline"))
    variants = _bullets(ba.get("variants"))
    if sample or guidance or outline or variants:
        lines.append("**更好的答法**")
        lines.append("")
        if sample:
            lines.append("**参考答案**")
            lines.append("")
            lines.extend(_quote(sample))
            lines.append("")
        if guidance:
            lines.append("**指导**：" + guidance)
            lines.append("")
        if outline:
            lines.append("**要点骨架**")
            lines.append("")
            lines.extend(outline)
            lines.append("")
        if variants:
            lines.append("**变体 / 追问延伸**")
            lines.append("")
            lines.extend(variants)
            lines.append("")

    return _trim(lines)


def _render_stats(questions):
    total = len(questions)
    answered = sum(1 for q in questions if _str(q.get("answer")))
    reviewed = sum(1 for q in questions
                   if isinstance(q.get("review"), dict) and _str(q.get("answer")))

    counts = {}
    order = []
    for q in questions:
        cat = _str(q.get("category")) or "未分类"
        if cat not in counts:
            counts[cat] = 0
            order.append(cat)
        counts[cat] += 1
    order.sort(key=lambda c: (-counts[c], c))

    lines = []
    lines.append("- 本场共 **%d** 题" % total)
    lines.append("- 有回答 **%d** 题（已评价 %d 题），无回答 **%d** 题"
                 % (answered, reviewed, total - answered))
    lines.append("")
    lines.append("| 分类 | 题量 | 占比 |")
    lines.append("|------|------|------|")
    for cat in order:
        n = counts[cat]
        lines.append("| %s | %d | %.0f%% |" % (cat, n, 100.0 * n / total))

    hits = {}
    for q in questions:
        review = q.get("review")
        if isinstance(review, dict) and _str(q.get("answer")):
            hit = _str(review.get("hit")) or "未标注"
            hits[hit] = hits.get(hit, 0) + 1
    if hits:
        lines.append("")
        lines.append("**评价分布**（仅有回答的题）："
                     + " ｜ ".join("%s %d" % (k, hits[k]) for k in hits))
    return lines


def render(data, today=None):
    meta = data.get("meta") or {}
    questions = data.get("questions") or []
    if not questions:
        raise ValueError("review.json 缺少 questions（至少需要一道题）")

    today = today or _date.today().isoformat()
    company = _str(meta.get("company"))
    role = _str(meta.get("role"))
    round_ = _str(meta.get("round"))

    title_bits = [p for p in (company, role, round_) if p]
    title = " ".join(title_bits) if title_bits else "面试"

    lines = ["# %s 面试复盘" % title, ""]

    meta_pairs = [
        ("日期", _str(meta.get("date")) or today),
        ("公司", company),
        ("岗位", role),
        ("轮次", round_),
        ("面试官", _str(meta.get("interviewer"))),
        ("材料类型", _str(meta.get("material_type"))),
        ("结果", _str(meta.get("result"))),
    ]
    meta_line = " ｜ ".join("%s：%s" % (k, v) for k, v in meta_pairs if v)
    if meta_line:
        lines.append("> " + meta_line)

    # collect sections in order; empty ones are skipped entirely
    sections = []

    background = _str(data.get("background"))
    if background:
        sections.append(("材料与背景", [background]))

    agenda = _str(data.get("agenda"))
    if agenda:
        sections.append(("本轮考察脉络", [agenda]))

    rqa_block = []
    for item in data.get("reverse_qa") or []:
        if not isinstance(item, dict):
            continue
        t = _str(item.get("title"))
        c = _str(item.get("content"))
        if not (t or c):
            continue
        if rqa_block:
            rqa_block.append("")
        if t:
            rqa_block.append("### " + t)
            rqa_block.append("")
        if c:
            rqa_block.extend(_str(c).splitlines())
    if rqa_block:
        sections.append(("反问环节情报", _trim(rqa_block)))

    overall = data.get("overall")
    ov_block = []
    if isinstance(overall, dict):
        summary = _str(overall.get("summary"))
        strengths = _bullets(overall.get("strengths"))
        weaknesses = _bullets(overall.get("weaknesses"))
        if summary:
            ov_block.append(summary)
        if strengths:
            if ov_block:
                ov_block.append("")
            ov_block.append("**亮点**")
            ov_block.append("")
            ov_block.extend(strengths)
        if weaknesses:
            if ov_block:
                ov_block.append("")
            ov_block.append("**短板**")
            ov_block.append("")
            ov_block.extend(weaknesses)
    if ov_block:
        sections.append(("我的整体表现评价", _trim(ov_block)))

    q_block = []
    for i, q in enumerate(questions, 1):
        if q_block:
            q_block.append("")
        q_block.extend(_render_question(i, q if isinstance(q, dict) else {}))
    sections.append(("问题复盘清单", _trim(q_block)))

    sections.append(("汇总与分类统计", _render_stats(questions)))

    for idx, (title_i, body) in enumerate(sections):
        lines.append("")
        lines.append("## %d. %s" % (idx, title_i))
        lines.append("")
        lines.extend(body)

    notes = _bullets(data.get("notes"))
    if notes:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**备注**")
        lines.append("")
        lines.extend(notes)

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
# optional gate
# --------------------------------------------------------------------------

def _load_validator():
    """Import the sibling validate_review module, or return None if unavailable."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import validate_review
        return validate_review
    except Exception:
        return None


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render an interview debrief Markdown document from review.json.")
    parser.add_argument("json_path", help="path to review.json")
    parser.add_argument("--out", default=None,
                        help="output directory (default: ./%s)" % OUT_DIR_DEFAULT)
    parser.add_argument("--record", default=None,
                        help="path to the confirmed interview record; it is archived "
                             "next to the document and used for coverage checking")
    parser.add_argument("--force", action="store_true",
                        help="overwrite the target .md if it already exists")
    parser.add_argument("--no-validate", action="store_true",
                        help="skip the review.json gate")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.json_path):
        print("error: input file not found: %s" % args.json_path, file=sys.stderr)
        return 1

    try:
        with open(args.json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("error: failed to read/parse JSON: %s" % exc, file=sys.stderr)
        return 1

    record_text = None
    if args.record:
        if not os.path.isfile(args.record):
            print("error: record file not found: %s" % args.record, file=sys.stderr)
            return 1
        with open(args.record, "r", encoding="utf-8") as fh:
            record_text = fh.read()

    # --- gate (structure + iron rules + coverage) -------------------------
    if not args.no_validate:
        validator = _load_validator()
        if validator is None:
            print("warning: validate_review.py not found next to build_doc.py, "
                  "gate skipped", file=sys.stderr)
        else:
            errors, warnings = validator.validate(data, record_text)
            for w in warnings:
                print("warning: %s" % w)
            for e in errors:
                print("error: %s" % e, file=sys.stderr)
            if errors:
                print("error: 门禁未通过，已中止渲染"
                      "（修正 review.json 后重试，或用 --no-validate 跳过）",
                      file=sys.stderr)
                return 1

    try:
        markdown = render(data)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    out_dir = os.path.abspath(args.out or OUT_DIR_DEFAULT)
    os.makedirs(out_dir, exist_ok=True)

    base = make_filename(data.get("meta") or {})
    if base.endswith(".md"):
        base = base[:-3]

    out_md = os.path.join(out_dir, base + ".md")
    if os.path.exists(out_md) and not args.force:
        print("error: 目标文件已存在：%s\n       确认要覆盖时加 --force" % out_md,
              file=sys.stderr)
        return 1

    with open(out_md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(markdown)
    print("[md] %s" % out_md)

    out_json = os.path.join(out_dir, base + ".json")
    with open(out_json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("[json] %s" % out_json)

    if record_text is not None:
        out_rec = os.path.join(out_dir, base + ".记录.md")
        with open(out_rec, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(record_text)
            if not record_text.endswith("\n"):
                fh.write("\n")
        print("[record] %s" % out_rec)

    return 0


if __name__ == "__main__":
    sys.exit(main())
