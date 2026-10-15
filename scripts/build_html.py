#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render an interview debrief HTML page from review.json.

Zero third-party dependencies (Python standard library only).
Cross-platform: Windows / macOS / Linux.

Usage:
    python build_html.py review.json [--out DIR] [--record RECORD.md] [--force]

Input : a structured review.json (same schema as build_doc.py; documented in
        references/doc-template.md)
Output: <out>/<date>-<company>-<role>-<round>.html

The page is fully self-contained: CSS and the little filtering script are
inlined, no external fonts / CDN / assets. It can be opened offline or shared
as a single file. Question cards are the centrepiece — one card per question,
with the classification, interviewer intent, your answer, the review and the
better answer stacked in a readable order.

Before rendering, the sibling validate_review.py gate runs automatically
(structure + iron rules + coverage). Errors abort rendering unless
--no-validate is given. Warnings are printed but do not block.

An existing .html file is never overwritten unless --force is given.

Exit codes:
    0  success (the output path is printed to stdout, tagged [html])
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
# small helpers (kept local so this script stays standalone)
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


def _items(value):
    """Normalise a JSON value into a list of non-empty strings."""
    out = []
    for it in value or []:
        s = _str(it)
        if s:
            out.append(s)
    return out


def _clean_filename_part(value):
    part = ILLEGAL_FILENAME_CHARS.sub("-", _str(value))
    return part.strip(" -.~")


def make_basename(meta, today=None):
    today = today or _date.today().isoformat()
    parts = [_clean_filename_part(meta.get("date")) or today]
    for key in ("company", "role", "round"):
        seg = _clean_filename_part(meta.get(key))
        if seg:
            parts.append(seg)
    return "-".join(parts)


def _esc(text):
    return (_str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _para(text):
    """Escaped text rendered as a paragraph (newlines preserved by CSS)."""
    s = _str(text)
    return '<p class="body">%s</p>' % _esc(s) if s else ""


def _ul(items):
    lis = "".join("<li>%s</li>" % _esc(i) for i in _items(items))
    return '<ul class="bullets">%s</ul>' % lis if lis else ""


def _ol(items):
    lis = "".join("<li>%s</li>" % _esc(i) for i in _items(items))
    return '<ol class="outline">%s</ol>' % lis if lis else ""


HIT_CLASS = {
    "命中": "hit-good",
    "部分命中": "hit-warn",
    "偏离": "hit-bad",
}


# --------------------------------------------------------------------------
# styles + page shell (no .format() / f-string: CSS braces stay untouched)
# --------------------------------------------------------------------------

CSS = """*{box-sizing:border-box}
:root{
  --bg:#f4f5f7; --card:#ffffff; --ink:#1f2430; --muted:#5b6472;
  --line:#e5e8ee; --accent:#2563eb; --accent-soft:#eff4ff;
  --good:#0f766e; --good-soft:#e6f4f1; --warn:#b45309; --warn-soft:#fdf3e3;
  --bad:#b91c1c; --bad-soft:#fdeceb; --radius:12px;
}
*,*::before,*::after{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:15px; line-height:1.78; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:940px; margin:0 auto; padding:36px 20px 72px}
.hero{margin-bottom:24px}
.hero h1{margin:0 0 14px; font-size:26px; line-height:1.4; font-weight:650; letter-spacing:.2px}
.chips{display:flex; flex-wrap:wrap; gap:8px}
.chip{background:var(--card); border:1px solid var(--line); border-radius:999px;
  padding:3px 12px; font-size:13px; color:var(--muted)}
.chip b{color:var(--ink); font-weight:600}
.card{background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:20px 22px; margin-bottom:16px; box-shadow:0 1px 2px rgba(16,24,40,.04)}
.card > h2{margin:0 0 12px; font-size:16px; font-weight:650; color:var(--ink)}
.card > h2 .idx{color:var(--accent); margin-right:8px; font-variant-numeric:tabular-nums}
.body{margin:0 0 10px; white-space:pre-wrap; color:#2b3340}
.body:last-child{margin-bottom:0}
.subhead{margin:16px 0 6px; font-size:13px; font-weight:650; color:var(--muted);
  text-transform:uppercase; letter-spacing:.6px}
.subhead:first-child{margin-top:0}
.bullets{margin:0; padding-left:20px}
.bullets li{margin:3px 0}
.outline{margin:0; padding-left:22px}
.outline li{margin:4px 0}
.stats{display:flex; flex-wrap:wrap; gap:18px; align-items:baseline; margin:0 0 14px}
.stat{font-size:14px; color:var(--muted)}
.stat b{font-size:20px; color:var(--ink); margin-right:4px}
.dist{display:flex; flex-wrap:wrap; gap:10px}
.dist-item{background:var(--accent-soft); color:#1e40af; border-radius:8px;
  padding:6px 11px; font-size:13px}
.dist-item b{font-variant-numeric:tabular-nums}
.filters{display:flex; flex-wrap:wrap; gap:8px; margin:22px 0 14px}
.filter-btn{appearance:none; cursor:pointer; font:inherit; font-size:13px;
  background:var(--card); color:var(--muted); border:1px solid var(--line);
  border-radius:999px; padding:5px 14px; transition:.15s}
.filter-btn:hover{border-color:#c9d3e6; color:var(--ink)}
.filter-btn.active{background:var(--accent); border-color:var(--accent); color:#fff}
.qa{background:var(--card); border:1px solid var(--line); border-left:3px solid var(--accent);
  border-radius:var(--radius); padding:20px 22px; margin-bottom:16px;
  box-shadow:0 1px 2px rgba(16,24,40,.04)}
.qa-head{display:flex; flex-wrap:wrap; align-items:baseline; gap:10px; margin-bottom:14px}
.qnum{background:var(--accent); color:#fff; font-size:12px; font-weight:650;
  border-radius:6px; padding:2px 8px; font-variant-numeric:tabular-nums}
.qtext{margin:0; font-size:16px; font-weight:620; line-height:1.6; flex:1 1 260px}
.cat{font-size:12px; color:#1e40af; background:var(--accent-soft);
  border-radius:6px; padding:2px 9px}
.block{margin-top:14px}
.block > .label{font-size:12px; font-weight:650; color:var(--muted);
  letter-spacing:.5px; margin-bottom:6px}
.intent{border-left:2px solid #c9d3e6; padding:2px 0 2px 12px; color:#2b3340}
.intent .extra{display:block; color:var(--muted); font-size:14px; margin-top:4px}
blockquote{margin:0; background:#fafbfc; border:1px solid var(--line);
  border-radius:10px; padding:12px 14px; color:#2b3340; white-space:pre-wrap}
.review-list{margin:0; padding-left:0; list-style:none}
.review-list li{margin:5px 0; padding-left:14px; position:relative}
.review-list li::before{content:""; position:absolute; left:2px; top:11px;
  width:4px; height:4px; border-radius:50%; background:#c3cbd9}
.review-list li.fix{color:var(--ink); font-weight:600}
.review-list li.fix::before{background:var(--warn)}
.hit{display:inline-block; font-size:12px; border-radius:999px;
  padding:1px 10px; margin-left:8px; font-weight:600}
.hit-good{background:var(--good-soft); color:var(--good)}
.hit-warn{background:var(--warn-soft); color:var(--warn)}
.hit-bad{background:var(--bad-soft); color:var(--bad)}
.sample{background:#f8fbff; border:1px solid #d9e6fb; border-radius:10px;
  padding:14px 16px; color:#233; white-space:pre-wrap}
.variant{margin-top:8px; color:#2b3340}
.notes{margin-top:26px; color:var(--muted); font-size:14px}
.notes ul{margin:6px 0 0; padding-left:20px}
footer{margin-top:34px; color:#8b93a1; font-size:12.5px; text-align:center}
.placeholder{display:none}
@media (max-width:600px){
  .wrap{padding:24px 14px 56px}
  .hero h1{font-size:21px}
  .qa, .card{padding:16px 15px}
}
"""

JS = """(function(){
  var buttons = document.querySelectorAll('.filter-btn');
  var cards = document.querySelectorAll('.qa');
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function(){
      var cat = this.getAttribute('data-cat');
      for (var j = 0; j < buttons.length; j++) {
        buttons[j].classList.toggle('active', buttons[j] === this);
      }
      for (var k = 0; k < cards.length; k++) {
        cards[k].style.display =
          (cat === '__all__' || cards[k].getAttribute('data-cat') === cat) ? '' : 'none';
      }
    });
  }
})();
"""

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
__CSS__</style>
</head>
<body>
<div class="wrap">
__HERO__
__BODY__
<footer>由 interview-debrief 生成 · 推断部分为合理推测，请结合实际情况判断</footer>
</div>
<script>
__JS__</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# html fragments
# --------------------------------------------------------------------------

def _hero(title, meta, today):
    chips = []
    for label, value in (("日期", _str(meta.get("date")) or today),
                         ("公司", _str(meta.get("company"))),
                         ("岗位", _str(meta.get("role"))),
                         ("轮次", _str(meta.get("round"))),
                         ("面试官", _str(meta.get("interviewer"))),
                         ("材料类型", _str(meta.get("material_type"))),
                         ("结果", _str(meta.get("result")))):
        if value:
            chips.append('<span class="chip">%s：<b>%s</b></span>' % (_esc(label), _esc(value)))
    return ('<header class="hero">\n<h1>%s</h1>\n<div class="chips">%s</div>\n</header>'
            % (_esc(title), "".join(chips)))


def _card(idx, title, inner):
    if not inner:
        return ""
    return ('<section class="card">\n<h2><span class="idx">%d</span>%s</h2>\n%s\n</section>'
            % (idx, _esc(title), inner))


def _qa_card(idx, q):
    question = _esc(_str(q.get("question")) or "（问题缺失）")
    cat = _str(q.get("category"))
    sub = _str(q.get("subcategory"))
    cat_line = " / ".join(p for p in (cat, sub) if p)

    parts = ['<article class="qa" data-cat="%s">' % _esc(cat or "未分类")]
    parts.append('<header class="qa-head">')
    parts.append('<span class="qnum">Q%d</span>' % idx)
    parts.append('<h3 class="qtext">%s</h3>' % question)
    if cat_line:
        parts.append('<span class="cat">%s</span>' % _esc(cat_line))
    parts.append('</header>')

    # interviewer intent
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
        inner = _esc(core or extra)
        if core and extra:
            inner += '<span class="extra">补充：%s</span>' % _esc(extra)
        parts.append('<div class="block"><div class="label">面试官意图</div>'
                     '<div class="intent">%s</div></div>' % inner)

    # my answer (optional)
    answer = _str(q.get("answer"))
    if answer:
        parts.append('<div class="block"><div class="label">我的回答</div>'
                     '<blockquote>%s</blockquote></div>' % _esc(answer))

    # review (optional; only when there is an answer)
    review = q.get("review")
    if isinstance(review, dict) and answer:
        hit = _str(review.get("hit"))
        hit_html = ('<span class="hit %s">%s</span>'
                    % (HIT_CLASS.get(hit, "hit-warn"), _esc(hit))) if hit else ""
        lis = []
        if _str(review.get("points")):
            lis.append("<li>踩中考点：%s</li>" % _esc(review.get("points")))
        if _str(review.get("missing")):
            lis.append("<li>遗漏：%s</li>" % _esc(review.get("missing")))
        if _str(review.get("delivery")):
            lis.append("<li>表达与结构：%s</li>" % _esc(review.get("delivery")))
        if _str(review.get("top_fix")):
            lis.append('<li class="fix">最该改的一处：%s</li>' % _esc(review.get("top_fix")))
        if lis:
            parts.append('<div class="block"><div class="label">评价%s</div>'
                         '<ul class="review-list">%s</ul></div>'
                         % (hit_html, "".join(lis)))

    # better answer — a reference answer is mandatory; guidance / outline /
    # variants are optional extras
    ba = q.get("better_answer") or {}
    sample = _str(ba.get("sample"))
    guidance = _str(ba.get("guidance")) or _str(ba.get("direction"))
    outline = _items(ba.get("outline"))
    variants = _items(ba.get("variants"))
    ba_parts = []
    if sample:
        ba_parts.append('<div class="subhead">参考答案</div>'
                        '<div class="sample">%s</div>' % _esc(sample))
    if guidance:
        ba_parts.append('<div class="subhead">指导</div><p class="body">%s</p>'
                        % _esc(guidance))
    if outline:
        ba_parts.append('<div class="subhead">要点骨架</div>%s' % _ol(outline))
    if variants:
        ba_parts.append('<div class="subhead">变体 / 追问延伸</div>%s' % _ul(variants))
    if ba_parts:
        parts.append('<div class="block"><div class="label">更好的答法</div>%s</div>'
                     % "".join(ba_parts))

    parts.append('</article>')
    return "\n".join(parts)


def _stats(questions):
    total = len(questions)
    answered = sum(1 for q in questions if _str(q.get("answer")))
    counts = {}
    order = []
    for q in questions:
        cat = _str(q.get("category")) or "未分类"
        if cat not in counts:
            counts[cat] = 0
            order.append(cat)
        counts[cat] += 1
    order.sort(key=lambda c: (-counts[c], c))

    head = ('<div class="stats">'
            '<span class="stat"><b>%d</b>题</span>'
            '<span class="stat"><b>%d</b>题有回答</span>'
            '<span class="stat"><b>%d</b>题无回答</span>'
            '</div>' % (total, answered, total - answered))
    dist = "".join('<span class="dist-item">%s <b>%d</b></span>' % (_esc(c), counts[c])
                   for c in order)
    return head + ('<div class="dist">%s</div>' % dist if dist else "")


def _filters(questions):
    seen = []
    for q in questions:
        cat = _str(q.get("category")) or "未分类"
        if cat not in seen:
            seen.append(cat)
    if len(seen) < 2:
        return ""
    btns = ['<button class="filter-btn active" data-cat="__all__">全部</button>']
    for cat in seen:
        btns.append('<button class="filter-btn" data-cat="%s">%s</button>'
                    % (_esc(cat), _esc(cat)))
    return '<div class="filters">%s</div>' % "".join(btns)


def _reverse_qa(data):
    blocks = []
    for item in data.get("reverse_qa") or []:
        if not isinstance(item, dict):
            continue
        title = _str(item.get("title"))
        content = _str(item.get("content"))
        if not (title or content):
            continue
        if title:
            blocks.append('<div class="subhead">%s</div>' % _esc(title))
        if content:
            blocks.append('<p class="body">%s</p>' % _esc(content))
    return "".join(blocks)


def _overall(data):
    overall = data.get("overall")
    if not isinstance(overall, dict):
        return ""
    blocks = []
    if _str(overall.get("summary")):
        blocks.append('<p class="body">%s</p>' % _esc(overall.get("summary")))
    if _items(overall.get("strengths")):
        blocks.append('<div class="subhead">亮点</div>%s' % _ul(overall.get("strengths")))
    if _items(overall.get("weaknesses")):
        blocks.append('<div class="subhead">短板</div>%s' % _ul(overall.get("weaknesses")))
    return "".join(blocks)


def render(data, today=None):
    meta = data.get("meta") or {}
    questions = data.get("questions") or []
    if not questions:
        raise ValueError("review.json 缺少 questions（至少需要一道题）")

    today = today or _date.today().isoformat()
    title_bits = [p for p in (_str(meta.get("company")), _str(meta.get("role")),
                              _str(meta.get("round"))) if p]
    title = (" ".join(title_bits) if title_bits else "面试") + " 面试复盘"

    body = []

    idx = 0
    for name, inner in (("材料与背景", _para(data.get("background"))),
                        ("本轮考察脉络", _para(data.get("agenda"))),
                        ("反问环节情报", _reverse_qa(data)),
                        ("我的整体表现评价", _overall(data))):
        if inner:
            body.append(_card(idx, name, inner))
            idx += 1

    body.append(_card(idx, "汇总与分类统计", _stats(questions)))
    idx += 1

    qa_html = [""]  # placeholder replaced by filter bar + cards
    cards = "\n".join(_qa_card(i, q if isinstance(q, dict) else {})
                      for i, q in enumerate(questions, 1))
    body.append('<div class="qa-section">\n%s\n%s\n</div>'
                % (_filters(questions), cards))

    notes = _items(data.get("notes"))
    if notes:
        body.append('<section class="notes"><div class="subhead">备注</div>%s</section>'
                    % _ul(notes))

    page = PAGE
    page = page.replace("__TITLE__", _esc(title))
    page = page.replace("__CSS__", CSS)
    page = page.replace("__JS__", JS)
    page = page.replace("__HERO__", _hero(title, meta, today))
    page = page.replace("__BODY__", "\n".join(body))
    return page


# --------------------------------------------------------------------------
# optional gate
# --------------------------------------------------------------------------

def _load_validator():
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
        description="Render an interview debrief HTML page from review.json.")
    parser.add_argument("json_path", help="path to review.json")
    parser.add_argument("--out", default=None,
                        help="output directory (default: ./%s)" % OUT_DIR_DEFAULT)
    parser.add_argument("--record", default=None,
                        help="path to the confirmed interview record; used only for "
                             "the coverage check in the gate")
    parser.add_argument("--force", action="store_true",
                        help="overwrite the target .html if it already exists")
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

    if not args.no_validate:
        validator = _load_validator()
        if validator is None:
            print("warning: validate_review.py not found next to build_html.py, "
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
        html = render(data)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    out_dir = os.path.abspath(args.out or OUT_DIR_DEFAULT)
    os.makedirs(out_dir, exist_ok=True)

    out_html = os.path.join(out_dir, make_basename(data.get("meta") or {}) + ".html")
    if os.path.exists(out_html) and not args.force:
        print("error: 目标文件已存在：%s\n       确认要覆盖时加 --force" % out_html,
              file=sys.stderr)
        return 1

    with open(out_html, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("[html] %s" % out_html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
