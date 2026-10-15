# 复盘文档结构与 review.json 规范

出文档前必读。本文件定义两件事：**复盘文档的结构**，以及**喂给 `scripts/build_doc.py`（Markdown）与 `scripts/build_html.py`（网页）的 `review.json` 字段 schema**。模型只负责产出 `review.json`，渲染、命名、落盘、统计交给脚本。

- 模型**不要**手写最终 md（除脚本不可用时的降级情形）。
- 每个字段都可能有缺失；缺失时按"省略规则"整块跳过，不要留空标题。

---

## 一、复盘文档结构（脚本渲染出的结果）

```
# <公司> <岗位> <轮次> 面试复盘
> 日期：… ｜ 公司：… ｜ 岗位：… ｜ 轮次：… ｜ 面试官：… ｜ 材料类型：… ｜ 结果：…

## 0. 材料与背景
## 1. 本轮考察脉络
## 2. 反问环节情报
## 3. 我的整体表现评价        ← 条件章节
## 4. 问题复盘清单            ← 逐题展开
## 5. 汇总与分类统计          ← 脚本自动计算
```

### 各章节说明与省略规则

| 章节 | 内容 | 缺失时 |
|---|---|---|
| 0. 材料与背景 | 材料类型 + 从材料提取的、或用户补充的背景线索（公司/部门/业务/面试官身份） | `background` 为空 → 整节省略 |
| 1. 本轮考察脉络 | 整体意图：这轮在筛什么人、关注哪些能力 | `agenda` 为空 → 整节省略 |
| 2. 反问环节情报 | 面试官给的意见 / 部门团队业务介绍 / 其他情报，逐条列 | `reverse_qa` 为空 → 整节省略 |
| 3. 我的整体表现评价 | 总体短评 + 亮点 + 短板 | **材料无回答 → 整节省略**；`overall` 为空 → 省略 |
| 4. 问题复盘清单 | 逐题：分类 → 面试官意图 → 我的回答 → 评价 → 更好的答法 | `questions` 为空 → 报错，不允许 |
| 5. 汇总与分类统计 | 题量、分类分布、评价分布 | 脚本自动生成，无需提供 |

**条件章节的判定是本技能的核心约束之一**：面经类材料（只有问题、没有回答）**没有第 3 节**，且第 4 节的「我的回答」「评价」两个子块对每题都省略。

---

## 二、review.json 字段 schema

顶层：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `meta` | object | 是 | 场次元信息 |
| `background` | string | 否 | 材料与背景，支持 markdown 段落 |
| `agenda` | string | 否 | 本轮考察脉络 |
| `reverse_qa` | array | 否 | 反问环节情报 |
| `overall` | object \| null | 否 | 整体评价；材料无回答时给 `null` |
| `questions` | array | 是 | 问答复盘列表 |
| `notes` | array | 否 | 其他备注，追加在文末 |

`meta`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | string | `YYYY-MM-DD`；缺省时脚本用当天日期 |
| `company` | string | 公司名或代号；缺省可空 |
| `role` | string | 岗位；缺省可空 |
| `round` | string | 轮次（一面/二面/HR面…）；缺省可空 |
| `interviewer` | string | 面试官身份（用人经理/HR…），不要写真实姓名 |
| `material_type` | string | `转写文本` / `面经文字` / `面经图片` |
| `result` | string | 待定 / 已进下一轮 / 已挂 / 未提供 |

`reverse_qa[]` 每项：

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 小标题，如"面试官给的意见""部门/团队/业务介绍" |
| `content` | string | 正文，支持 markdown |

`overall`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `summary` | string | 总体短评 |
| `strengths` | array[string] | 亮点 |
| `weaknesses` | array[string] | 短板 |

`questions[]` 每项：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | string | 是 | 问题原文（已语境还原） |
| `category` | string | 是 | 分类主类，见 SKILL.md 分类锚点 |
| `subcategory` | string | 否 | 细分，如 `Agent 审计`、`网络·TCP` |
| `answer_kind` | string | **是** | `standard`（有公认标准答案）/ `directional`（只给方向） |
| `intent` | object | 是 | 面试官意图，见下（`core` 必填 / `extra` 选填） |
| `answer` | string | 否 | 我的回答；**无回答时留空** |
| `review` | object \| null | 否 | 评价；**无回答时给 `null`** |
| `better_answer` | object | 是 | 更好的答法 |

**`answer_kind` 必须显式提供**——它是门禁判定"示范回答铁律"的唯一依据：

- `standard`：八股、概念定义、算法、协议流程这类**有公认正解**的题 → 允许给 `sample`；
- `directional`：场景题、开放题、行为题、个人经历题 → **只给方向与要点，`sample` 必须留空**。

判定拿不准时按 `directional` 处理（保守）。

`intent`（见 `answer-style.md`）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `core` | 是 | 核心意图：他大概想确认什么，一句话，可结合公司与岗位背景 |
| `extra` | 否 | 额外意图 / 另一种可能；没有意义就留空，不硬凑 |

`review`：

| 字段 | 说明 |
|---|---|
| `hit` | `命中` / `部分命中` / `偏离` |
| `points` | 踩中考点 |
| `missing` | 遗漏 |
| `delivery` | 表达与结构 |
| `top_fix` | 最该改的一处 |

`better_answer`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `direction` | string | 一句话方向 |
| `outline` | array[string] | 要点骨架 |
| `sample` | string | 示范回答；**仅当有公认标准答案时给**，否则留空 |

---

## 三、完整示例

```json
{
  "meta": {
    "date": "2026-10-11",
    "company": "A公司",
    "role": "Agent 开发",
    "round": "一面",
    "interviewer": "用人经理",
    "material_type": "转写文本",
    "result": "待定"
  },
  "background": "面试官开场自我介绍，团队负责企业内部 Agent 平台，正在做 Agent 的权限审计与行为可观测。用户自述主攻方向为 Agent 开发。",
  "agenda": "这轮重心在 Agent 工程落地能力与计算机基础，项目深挖集中在 RAG 与工具调用链路的可靠性。",
  "reverse_qa": [
    {
      "title": "面试官给的意见",
      "content": "建议补一下分布式一致性的基础，Agent 侧讲得比基础更扎实。"
    },
    {
      "title": "部门/团队/业务介绍",
      "content": "团队 8 人，做内部 Agent 平台，服务多个业务线，当前重点是把 Agent 的行为纳入审计。"
    }
  ],
  "overall": {
    "summary": "项目与 Agent 侧表达清晰、有细节；计算机基础偏弱，追问三层后明显断档。",
    "strengths": ["项目贡献归属讲得清楚", "RAG 链路的失败模式有真实踩坑"],
    "weaknesses": ["TCP/一致性哈希类问题只停在定义层", "表达略冗长，单题常超时"]
  },
  "questions": [
    {
      "question": "你们 RAG 的召回质量是怎么保证的？",
      "category": "项目经历",
      "subcategory": "RAG 召回",
      "answer_kind": "directional",
      "intent": {
        "core": "连续追问三次召回口径（怎么算、bad case 怎么归因、上线后是否回落），可能是在确认这件事是不是他本人做过、有没有量化归因的方法（该团队在做 Agent 可观测，可能对口径特别敏感）。",
        "extra": "也可能只是固定题本里的追问，与回答质量无关。"
      },
      "answer": "讲了用 rerank 提效果，召回率大概提升了百分之三十左右。",
      "review": {
        "hit": "部分命中",
        "points": "方向对，知道 rerank 是主要手段。",
        "missing": "没交代召回率的口径（分母、样本集、统计周期），也没说分母是谁。",
        "delivery": "先讲了五分钟背景，真正做的事只讲了两句。",
        "top_fix": "把口径讲清楚：在哪个评测集上、用什么指标、提升了多少。"
      },
      "better_answer": {
        "direction": "面试官想听的是「你如何度量并归因召回问题」，不是「你用了什么组件」。",
        "outline": [
          "评测集怎么构造的、多少条",
          "指标定义：recall@k 还是命中率，分母是什么",
          "主要 bad case 的归因分布",
          "改动后的对比与上线后的监控"
        ],
        "sample": ""
      }
    },
    {
      "question": "说下一致性哈希，它解决了什么问题？",
      "category": "计算机基础八股",
      "subcategory": "分布式·一致性哈希",
      "answer_kind": "standard",
      "intent": {
        "core": "单问一题、没有追问，可能是常规基础考察，判断分布式基本功是否扎实。",
        "extra": ""
      },
      "answer": "",
      "review": null,
      "better_answer": {
        "direction": "普通取模在节点增减时会导致大规模数据迁移；一致性哈希把节点和数据映射到同一个环上，只影响相邻区间。",
        "outline": [
          "普通哈希取模的问题：扩容时几乎全量重分布",
          "一致性哈希的环形结构：key 与节点同环，顺时针找第一个节点",
          "节点增减只影响相邻区间",
          "数据倾斜问题与引入虚拟节点"
        ],
        "sample": "一致性哈希解决的是分布式缓存/存储扩容时数据大规模迁移的问题。普通做法是 hash(key) % N，一旦 N 变化，绝大多数 key 的落点都会变，缓存会大面积失效。一致性哈希把 0~2^32 组织成一个环，节点和 key 都映射到环上，key 顺时针找到的第一个节点就是它的归属。这样增加或删除一个节点，只影响环上相邻的一段区间，而不是全量。它的副作用是节点少时分布不均，所以通常给每个物理节点挂多个虚拟节点来打散。"
      }
    }
  ],
  "notes": ["本场未出现场景设计题。"]
}
```

---

## 四、落盘产物与命名

**默认输出目录**：当前工作目录下的 `面试复盘/`（脚本自动创建）。每场产出四个文件：

| 文件 | 由谁产出 | 内容 |
|---|---|---|
| `<基名>.md` | `build_doc.py` | 复盘文档（存档、检索用） |
| `<基名>.html` | `build_html.py` | 网页版复盘——问答题卡片化，自包含单文件，阅读 / 分享用 |
| `<基名>.json` | `build_doc.py` | `review.json` 副本（可重渲染、可机器统计） |
| `<基名>.记录.md` | `build_doc.py`（传了 `--record` 时） | 确认后的面试记录 |

**基名** = `<日期>-<公司>-<岗位>-<轮次>`；缺失的段直接省略，全缺时退化为 `<日期>`。

- 例：`2026-10-11-A公司-Agent开发-一面.md`

**覆盖保护**：目标文件已存在时脚本**默认拒绝写入**并报错，需显式加 `--force`（`.md` 与 `.html` 各自独立判断）。

**隐私**：公司名建议用代号（A公司 / B公司），同一公司前后代号保持一致；不写入面试官真实姓名与联系方式。文件名中的非法字符（`\ / : * ? " < > |`）会被脚本替换为 `-`。

## 五、门禁校验

`scripts/validate_review.py` 在渲染前检查结构与铁律，**由 `build_doc.py` 自动调用**（可用 `--no-validate` 跳过）。

**错误（阻断渲染）**

| 编号 | 规则 |
|---|---|
| E1 | `questions` 缺失或为空 |
| E2 | 每题缺 `question` / `category` / `intent.core` / `better_answer.direction` |
| E3 | **没有回答却给了评价**（无回答不评价） |
| E4 | **给了 `sample` 但 `answer_kind` 不是 `standard`**（场景/开放题不得给示范答案） |
| E5 | 传了 `--record` 时，题干在确认后的记录里找不到（疑似改写或编造） |

**警告（打印但不阻断）**：有回答却无评价、`hit` 取值非法、声明 `standard` 却无示范回答、记录里有疑问句未进入复盘清单（疑似漏题）、`meta` 关键字段缺失。

## 六、调用

```bash
# Markdown + 结构化数据 + 记录归档（脚本内部先跑门禁再渲染）
python scripts/build_doc.py review.json --record 确认后的记录.md

# 网页版（问答题卡片化，自包含单文件）
python scripts/build_html.py review.json

# 覆盖已存在的产物（.md 与 .html 各自判断）
python scripts/build_doc.py review.json --force
python scripts/build_html.py review.json --force

# 只跑门禁
python scripts/validate_review.py review.json --record 确认后的记录.md
```

脚本把产物路径打印到标准输出，每行带 `[md]` / `[html]` / `[json]` / `[record]` 标签，便于后续向用户展示。

**脚本不可用时的降级**：直接按上面的结构手写 md 落盘，并说明未使用脚本。
