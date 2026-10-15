#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gatekeeper for review.json — validate structure and the skill's iron rules.

Zero third-party dependencies (Python standard library only).
Cross-platform: Windows / macOS / Linux.

Usage:
    python validate_review.py review.json [--record CONFIRMED_RECORD.md] [--quiet]

Returns exit code 0 when there are no errors (warnings are allowed) and 1 when
any error is found. `build_doc.py` and `build_html.py` import this module and run
the same checks automatically before rendering.

Iron rules enforced here (only the machine-checkable ones):
    E1  questions must be a non-empty list
    E2  each question needs question / category / intent.core / better_answer.sample
        (参考答案是必给的 -- 每道题都要有一段可以直接说出口的作答)
    E3  no answer  ->  no review        (面经类材料只有问题没有回答，不得评价)
    E4  (with --record) question text must be traceable to the confirmed record
"""

import argparse
import difflib
import json
import os
import re
import sys

VALID_HITS = ("命中", "部分命中", "偏离")

_PUNCT_CHARS = " \t\r\n，。、；：？！,.;:?!\"'“”‘’（）()[]【】《》〈〉—…·-~～"
_PUNCT = re.compile("[" + re.escape(_PUNCT_CHARS) + "]+")
_SENT_SPLIT = re.compile(r"(?<=[？?])")


def _norm(text):
    return _PUNCT.sub("", str(text or ""))


def _s(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _has_review_content(review):
    if not isinstance(review, dict):
        return False
    return any(_s(review.get(k)) for k in
               ("hit", "points", "missing", "delivery", "top_fix"))


def _too_similar(a, b, threshold=0.9):
    """True when the two texts are practically the same answer."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if min(len(na), len(nb)) < 12:
        return False
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


# --------------------------------------------------------------------------
# record-based coverage helpers
# --------------------------------------------------------------------------

def _record_lines(record_text):
    lines = []
    for ln in str(record_text or "").replace("\r\n", "\n").split("\n"):
        n = _norm(ln)
        if n:
            lines.append(n)
    return lines


def _record_question_sentences(record_text):
    """Extract question-looking clauses from the confirmed record."""
    text = str(record_text or "").replace("\r\n", "\n")
    out = []
    for seg in _SENT_SPLIT.split(text):
        seg = seg.strip()
        if not seg or not (seg.endswith("？") or seg.endswith("?")):
            continue
        cut = max(seg.rfind("。", 0, len(seg) - 1),
                  seg.rfind("？", 0, len(seg) - 1),
                  seg.rfind("?", 0, len(seg) - 1),
                  seg.rfind("\n", 0, len(seg) - 1))
        clause = seg[cut + 1:].strip()
        # drop a leading speaker label such as "面试官：" / "我："
        clause = re.sub(r"^[^：:？?]{1,10}[：:]\s*", "", clause) or clause
        if len(_norm(clause)) >= 4:
            out.append(clause)
    return out


def _find_in_record(question, record_lines, record_norm, threshold=0.75):
    nq = _norm(question)
    if not nq:
        return True
    if nq in record_norm:
        return True
    for ln in record_lines:
        if abs(len(ln) - len(nq)) > max(len(nq), 20):
            continue
        if difflib.SequenceMatcher(None, nq, ln).ratio() >= threshold:
            return True
    return False


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(data, record_text=None, threshold=0.75):
    """Return (errors, warnings) as lists of strings."""
    errors = []
    warnings = []

    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"], []

    meta = data.get("meta")
    if not isinstance(meta, dict):
        warnings.append("缺少 meta 对象（日期/公司/岗位/轮次等）")
        meta = {}
    if not _s(meta.get("date")):
        warnings.append("meta.date 缺失，脚本会回退为当天日期")
    if not _s(meta.get("material_type")):
        warnings.append("meta.material_type 缺失（建议标注 转写文本 / 面经文字 / 面经图片）")

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append("E1 questions 缺失或为空（至少需要一道题）")
        return errors, warnings

    record_norm = ""
    record_lines = []
    if record_text:
        record_norm = _norm(record_text)
        record_lines = _record_lines(record_text)

    for i, q in enumerate(questions, 1):
        tag = "Q%d" % i
        if not isinstance(q, dict):
            errors.append("%s 不是对象" % tag)
            continue

        question = _s(q.get("question"))
        if not question:
            errors.append("E2 %s 缺少 question（问题原文）" % tag)
        if not _s(q.get("category")):
            errors.append("E2 %s 缺少 category（分类）" % tag)

        intent = q.get("intent")
        if not isinstance(intent, dict):
            errors.append("E2 %s 缺少 intent（面试官意图）" % tag)
        else:
            core = (_s(intent.get("core")) or _s(intent.get("inference"))
                    or _s(intent.get("fact")))  # accept the legacy 3-layer schema
            if not core:
                errors.append("E2 %s 的意图缺少 core（核心意图，一句话即可）" % tag)

        ba = q.get("better_answer")
        if not isinstance(ba, dict):
            errors.append("E2 %s 缺少 better_answer（更好的答法）" % tag)
            ba = {}
        if not _s(ba.get("sample")):
            errors.append("E2 %s 缺少 better_answer.sample（参考答案必给，"
                          "要能直接说出口）" % tag)

        answer = _s(q.get("answer"))
        review = q.get("review")

        if not answer and _has_review_content(review):
            errors.append("E3 %s 没有回答，却给了评价（无回答不评价）" % tag)
        if answer and not _has_review_content(review):
            warnings.append("%s 有回答但没有评价" % tag)

        hit = _s(review.get("hit")) if isinstance(review, dict) else ""
        if _has_review_content(review) and hit and hit not in VALID_HITS:
            warnings.append("%s 的 hit「%s」不在 命中/部分命中/偏离 之内" % (tag, hit))

        sample = _s(ba.get("sample"))
        if sample and answer and _too_similar(sample, answer):
            warnings.append("%s 的参考答案与「我的回答」几乎一模一样，"
                            "确认这是在示范更好的答法、而不是复述原话？" % tag)

        if record_text and question and \
                not _find_in_record(question, record_lines, record_norm, threshold):
            errors.append("E4 %s 的题干在确认后的面试记录里找不到"
                          "（疑似改写或编造）：%s" % (tag, question))

    if record_text:
        covered = [_s(q.get("question")) for q in questions if isinstance(q, dict)]
        uncovered = []
        for clause in _record_question_sentences(record_text):
            nq = _norm(clause)
            if not nq:
                continue
            hit = False
            for cq in covered:
                ncq = _norm(cq)
                if not ncq:
                    continue
                if nq in ncq or ncq in nq:
                    hit = True
                    break
                if difflib.SequenceMatcher(None, nq, ncq).ratio() >= threshold:
                    hit = True
                    break
            if not hit:
                uncovered.append(clause)
        if uncovered:
            shown = uncovered[:10]
            warnings.append("记录里有 %d 个疑问句未进入复盘清单（疑似漏题）：%s"
                            % (len(uncovered), " ／ ".join(shown)))
            if len(uncovered) > len(shown):
                warnings.append("（其余 %d 个已省略）" % (len(uncovered) - len(shown)))

    return errors, warnings


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate review.json structure and iron rules.")
    parser.add_argument("json_path", help="path to review.json")
    parser.add_argument("--record", default=None,
                        help="path to the confirmed interview record (markdown/text) "
                             "for coverage checking")
    parser.add_argument("--quiet", action="store_true",
                        help="only print errors and warnings")
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

    errors, warnings = validate(data, record_text)

    for w in warnings:
        print("warning: %s" % w)
    for e in errors:
        print("error: %s" % e, file=sys.stderr)

    if errors:
        print("门禁：未通过（%d 个错误，%d 个警告）" % (len(errors), len(warnings)),
              file=sys.stderr)
        return 1

    if not args.quiet:
        print("门禁：通过（%d 个警告）" % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
