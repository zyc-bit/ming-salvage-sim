# 《明末》v2 路线图:复用 v1、最终取代 v1

> 本文是 v2 开发的权威规划,综合一次多 agent 仓库测绘(db.py 持久层 / ming_sim 架构 / content 资产 / web 前端)而成。
> 一句话:**把 v1 的可复用资产重构后供 v2 使用,v2 逐阶段发育,最终完全取代 v1。**

## 0. 现状与定位

| | v1(`ming_sim/` + `web_app.py` + `web/`) | v2(`v2/`) |
|---|---|---|
| 体量 | ~1.6 万行 Python + 1724 行后端 + 4476 行前端 | ~600 行 |
| 状态 | **当前唯一可玩的网页游戏**,但巨石化(db.py 4971、session.py 上帝对象、issues.py 重规则引擎) | 最新极简重写,**仅终端原型、2 个硬编码切片、无存档、无网页** |
| LLM 用法 | 从叙事**反向抠数字**打分(score_extractor 一套) | 单层:LLM 只当"嘴"与"裁判",代码管状态机与数值 |
| 本轮处置 | **冻结为 legacy**,保持可玩,只接受无风险清理 | **投入开发**,打地基 |

**v2 三铁律**(来自 `v2/state.py`/`engine.py`,务必贯穿后续开发):
1. 极简底层:几个国势 + 几股势力 + 人物 + 危机,深度来自**联动**不来自堆维度。
2. LLM 只当嘴与裁判,代码管状态机与数值,边界清晰、单层、**不反向从叙事抠数字**。
3. 信息不全 / 君命直贯 / 没有最优解 / 后果连锁,从第一刀就缝在一起。

---

## 1. v1 → v2 可复用资产清单(salvage)

### 1.1 内容数据(最大矿藏,`content/`)— 直接复用,按梯队接入

| 梯队 | 文件 | 内容量级 | v2 价值 |
|---|---|---|---|
| 🥇 立即可用 | `characters.json` | 58 人 + 7 派系 | 人物层数据底座,有名有姓有性格 |
| | `regions.json` | 23 地区(民心/骚乱/灾) | 地图骨架,军事与事件依赖它 |
| | `armies.json` | 17 军(关宁/京营/东江…) | 军事压力模型现成 |
| | `powers.json` | 7 外部势力(后金/流寇/东林…) | "为何崇祯必输"的压力根基 |
| 🥈 叙事层 | `seed_events.json`/`events.json` | 9 + 16 条(urgency 已校准) | 开局事件池 + 历史事件库 |
| | `opening_crises.json`/`opening_legacies.json` | 3 + 4 条 | **v2 已接入** ✅ |
| | `travel_times.json` | 区域×区域天数表 | 信使/调令延迟用 |
| 🥉 可选 | `classes.json` | 社会阶级压力 | 民变严重度仪表盘用 |
| ❌ 跳过 | `skills.json`/`skill_tools.json` | agno 框架绑定 | v2 用原生 LLM,无 agno |
| | `buildings.json` | 38 建筑(v1 建设玩法) | 极简阶段无建设,后期再说 |

**加载时裁剪的"极简负担"字段**(解析时 `pop()` 掉即可,余下零改动可用):
`characters.personal_skills`(agno skill ID)、`characters.historical_death_year/month`(确定性死亡时钟,与 v2"坏结局靠涌现"冲突)、`powers.last_action`(v1 每回合覆写)、`armies.theater`(v1 战区分类)。

### 1.2 持久层 — 不照搬,只借模式

- v1 的 **38 表规范化存档**(db.py)对 v2 是过度设计,**丢弃**。
- v2 最小存档:`dataclasses.asdict(state)` → `json.dumps(ensure_ascii=False)` 存**整局一个 blob** 到 `data/v2_saves/<slot>.json`;`load` 逐层重建 dataclass;缺字段给默认值。约 **30 行**,见任务 `v2/save.py`。
- 仅借 db.py 的模式:连接管理思路、KV/单例 upsert、json 序列化套路。

### 1.3 前端 — 不套旧壳,复用设计系统

- ❌ **不要**把 v1 的 4476 行 `main.tsx` 套到 v2:它与 v1 `state_payload` schema 深绑,胶水适配比重写更贵。
- ✅ 另起 **~600–900 行薄壳**,只做"局势面板 + 大臣列表 + 聊天流 + 退朝按钮 + LLM 设置"五块。
- ✅ 原样复用:CSS 设计 token(`styles.css` `:root` 颜色/字体变量)、背景图、立绘库、SSE 客户端(`api()` + `parseSseMessage()`,约 75 行)。

### 1.4 领域原语 — 选择性借鉴(概念,非照搬代码)

`flows.py`(省级财政结算,纯函数、内聚)、`communications.py`(驿传天数)、`matching.py`(地名/军名模糊匹配);`content/prompts/*.md`(game_world / minister_agent / season_simulator / decree_writer …)是叙事素材,v2 可参考裁剪。

### 1.5 明确不复用(anti-salvage)

db.py 38 表规范化、`session.py` 上帝对象、`issues.py` 重规则引擎、`score_extractor` 从叙事抠数字打分法、agno skills/tools 框架、`memories.py` 死代码(~273 行)。

---

## 2. content-bridge 实现要点(地基关键件)

目标:v2 切片从"内联写死人物"升级为"**引用 `content/` 真实数据 + 仅覆盖切片专有字段**"。

- **主路径**:新增 `v2/world.py`(或扩展 `v2/content.py`),复刻 v1 `content.GameContent.load()`(`content.py:444`)聚合逻辑的**极简子集**——只读 v2 需要的 characters/regions/armies/powers。
- **3 个旁路别漏**(v1 的加载不是单点):
  1. `travel_times.json` 由 `communications.py:22` 读,不走 GameContent;
  2. `opening_crises.json` 被 **`db.py:1410`** 直读;
  3. `opening_gazette.md` 被 **`db.py:1262`** 直读(⚠️ 此文件**并非孤儿**,早先误判已纠正)。
- **字段映射** `characters.json → v2 Character`:name/office/faction/loyalty/ability 直取;integrity/courage/style 折入 `persona` 或丢;personal_skills、historical_death_* 丢。切片只保留 stance/secret/loyalty 的**覆盖值**。
- **平滑迁移**:dingwei/liaodong 两切片先**新旧并存**——保留现有硬编码作回归基准,新增"从 content/ 构建"的等价路径,逐步切换,**文案与数值不变**。

---

## 3. 分阶段路线图(v2 → 完全取代 v1)

- **Phase 0 · 地基(本轮)** ✅ 进行中
  v2 升级为正式 package;最小存档 `v2/save.py`;content-bridge(加载 characters/regions 样板);本路线图。
- **Phase 1 · 富内容内核**
  接入 🥇 tier1(characters/regions/armies/powers),切片改为数据驱动;多人物、多势力盘面。
- **Phase 2 · 事件驱动**
  接入 seed_events/events,月推进由事件池驱动;多危机**串联联动**(不是堆维度)。
- **Phase 3 · 最小可玩网页**
  7 组端点 + 薄壳前端,复用 v1 CSS/资产;v2 首次"能在网页玩"。
- **Phase 4 · 经济与地理纵深**
  借鉴 `flows.py` 做省级财政、`travel_times` 做调令延迟;让数值有落点。
- **Phase 5 · 对等与超越**
  按 v2 理念**重做**(非移植)v1 的后宫/历史回顾/密令等;达成核心玩法对等。
- **退役 v1**
  当 v2 覆盖"日循环 + 召见 + 结算 + 存档 + 网页"核心闭环并稳定后,把 `ming_sim/`/`web_app.py`/`web/` 移入 `legacy/` 或归档,README 主入口切到 v2。

---

## 4. v1 冻结期纪律

- 不深度重构 v1;**不删 v1 存量死代码**(`memories.py` ~273 行 + `context.py:128` 共 ~286 行虽确证死,留待退役时一并清,除非另行指示——遵 CLAUDE.md"不删既有死码")。
- v1 只接受**无风险垃圾清理**:`.gitignore` 已补;~47MB 二进制冗余图(`*.wm.png`/`*.original.png`/被 webp 取代的 `bg_chat.png`/无引用的 `bg_court.png`)与悬空 `redundancy-cleanup` worktree 的删除**待用户授权**(不可逆,需本人拍板)。
- 已知封装气味(冻结期不动,记录在案):`web_app.py:33` 引用 `issues._format_issue_ongoing` 私有符号;`session ⇄ issues` 循环依赖(`issues.py:1019/1112` 延迟 import)。
