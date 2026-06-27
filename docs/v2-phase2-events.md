# v2 Phase 2：事件驱动月推进 — 最简设计

> 调研时间：2026-06-27
> 作者：设计调研员 agent
> 前置：Phase 1 内核已为 Crisis 增加 `cast` 字段（见"与 kernel 的对齐"节）

---

## 1. 数据形态：事件 → Crisis 的字段映射

### 现有字段够用的

| 事件字段 | → Crisis 字段 | 说明 |
|---|---|---|
| `id` | `crisis.id` | 直接复用 |
| `title` | `crisis.title` | 直接复用 |
| `summary` | `crisis.brief` | 皇帝看到的奏报，可叠加耳目迷雾（见第 4 节） |
| `resolve_condition` + `fail_condition` | `crisis.adjudicator_notes` | 拼接成 "解决条件: … 失败条件: …"，裁判 LLM 已能用 |
| `audiences` | `crisis.cast.characters` | 角色名列表，直接放入 cast |
| `interests` | `crisis.cast.factions` | 势力/群体名列表，放入 cast |
| `urgency` | 入池优先级排序 | 不进 Crisis 对象，用于选择逻辑 |
| `credibility` | 迷雾系数 | 不进 Crisis 对象，注入时决定 brief 模糊程度 |

### 必须新增的字段（在事件 JSON 里补）

| 新字段 | 类型 | 说明 |
|---|---|---|
| `truth` | str | 真相，只喂裁判。这是核心内容资产，**必须人工撰写**，无法从现有字段推导 |

Phase 2 不需要对全部 25 条事件补 truth；只需补进入首批切片队列的 5-6 条。

### 丢弃的字段（Phase 2 不用）

`severity`、`bar_value`、`bar_*_meaning`、`inertia`、`stage_text`、`ongoing_effects`、`effect_on_resolve`、`effect_on_fail`（来自 `opening_crises.json` 的 v1 格式）。这些是 v1 逻辑，Phase 2 只用裁判 LLM 的定性 effects，不回头。

### ⚠️ 触发门缩放问题（需与 kernel 对齐）

`seed_events.json` 中 `"国库": "<=240"` 使用了与 `state.metrics["国库"]`（0-100）不同的量纲。**Phase 2 实现时须将所有 trigger_gate 归一化到 0-100 的 METRIC\_KEYS 量纲**，否则比较永远不成立。建议在 JSON 中直接修正为 `"<=24"`（按切片初始国库22换算），并在注释里标注原始量纲。

---

## 2. 月推进改造：函数级最小改动

### 2a. `state.py` — 加一个字段

```python
@dataclass
class GameState:
    ...
    crises: list          # 危机队列（现有），active_crisis() 取首个未 resolved
    event_pool: list = field(default_factory=list)  # 尚未转化的事件 dict 列表
```

`active_crisis()` **不改**。解决了就自然推进到队列里下一个。

### 2b. `content.py` — 新增两个函数，修改切片初始化

```python
def _gate_met(gate: dict, metrics: dict) -> bool:
    """只评估 METRIC_KEYS 中的简单门；点号路径（子指标）跳过。"""
    for k, expr in gate.items():
        if "." in k or k not in metrics:
            continue
        op, num = expr[:2], int(expr[2:])
        val = metrics[k]
        if op == "<=" and not (val <= num): return False
        if op == ">=" and not (val >= num): return False
    return True


def event_to_crisis(ev: dict, state: GameState) -> Crisis:
    """把事件 dict 转成 Crisis，根据耳目低时加迷雾。"""
    brief = ev["summary"]
    low_intel = state.metrics.get("耳目", 60) < 40
    if low_intel and ev.get("credibility", 100) < 70:
        brief = "【消息语焉不详，各省塘报真假难辨】" + brief
    notes = f"解决条件:{ev.get('resolve_condition','')}\n失败条件:{ev.get('fail_condition','')}"
    cast = {
        "characters": ev.get("audiences", []),
        "factions": ev.get("interests", []),
    }
    return Crisis(
        id=ev["id"], title=ev["title"],
        brief=brief, truth=ev.get("truth", "（真相待补）"),
        adjudicator_notes=notes, cast=cast,
    )


def next_from_pool(state: GameState):
    """从 event_pool 取下一个满足触发门的最高 urgency 事件，转成 Crisis。"""
    eligible = [e for e in state.event_pool if _gate_met(e.get("trigger_gate", {}), state.metrics)]
    if not eligible:
        return None
    ev = max(eligible, key=lambda e: e.get("urgency", 0))
    state.event_pool.remove(ev)
    return event_to_crisis(ev, state)
```

切片函数（`_dingwei` 等）改动：

```python
# 原来
crises=[Crisis("wei", ...)],

# 改后：硬编码开局危机放 crises，后续事件放 event_pool
crises=[Crisis("wei", ...)],
event_pool=_load_pool_for_slice("dingwei"),  # 从 seed_events.json 过滤
```

`_load_pool_for_slice` 只是读 JSON、按 slice 筛选，5 行以内。

### 2c. `play.py` — 退朝时追加一行

```python
# 现有代码，resolved 后
if res.get("resolved"):
    cr.resolved = True
    nxt = next_from_pool(state)   # ← 新增：尝试从池子续下一个
    if nxt:
        state.crises.append(nxt)
```

终局判断（`active_crisis() is None`）保持不动——池子空且所有危机 resolved 时自然退出。

---

## 3. 选择逻辑：入池/出池

**入池**：切片初始化时把相关事件一次性放入 `event_pool`（按 `kind` 或 `slice_id` 白名单筛选）。不做动态"新事件涌入"（Phase 2 不需要）。

**出池**：`next_from_pool` 被调用时，从池中找所有满足 `trigger_gate` 的事件，取 urgency 最高者转成 Crisis 并移出池子。

**就这样**。没有权重表、没有有效期、没有优先级队列对象、没有规则引擎。

`trigger_gate` 的"评估"只是：遍历 gate 字典的每个 `metric_key: "<=N"` 或 `">=N"`，检查 `state.metrics[key]`。代码 8 行（已在上面写完）。

点号路径（`army.guanning.arrears`）的复杂子指标在 Phase 2 **静默跳过**——满足复杂门的事件相当于"门永远开着"（urgency 决定顺序）。Phase 4 地理纵深时再接入子指标。

---

## 4. 联动：一个危机的处置如何串联后续

**机制核心**：`apply_effects` 改变了 `state.metrics`，`next_from_pool` 的 trigger_gate 检查用的就是改变后的数值。不需要额外的"联动状态机"。

**具体例子**：

> 定魏→废厂卫→耳目暴跌→后续危机双重受累

1. **定魏**（Crisis `wei`）处置后，裁判 LLM 推演"尽废厂卫"的 effects：
   - `耳目 -大(-22)` → 耳目从 60 跌到 **38**
   - `皇威 +中(+12)` → 皇威上升
   - `东林.satisfaction +中` → 东林得意

2. `next_from_pool(state)` 被触发，此时 `state.metrics["耳目"] = 38`：
   - 若池中有类似"陕西逃户"（credibility=50）：`low_intel=True`（38<40），且 credibility<70，
     转出的 Crisis.brief 自动加上迷雾前缀——**玩家看到的奏报是"消息语焉不详"的降级版**。
   - 若池中有"民变苗头"类事件原本需要 `trigger_gate: {"耳目": "<=45"}`，现在直接满足，**进入队列的优先级提升**。

3. 下一月，皇帝面对的危机 brief 比实际轻得多（信息被遮蔽），但裁判 LLM 持有 truth，**代价不会减轻**。

**两条联动通道，都不加新维度**：
- **触发通道**：metrics 变化 → trigger_gate 被满足 → 新危机入队
- **信息通道**：耳目值 → event_to_crisis 时 brief 模糊程度 → 后果连锁中的"信息不全"铁律自然体现

---

## 5. 明确边界：故意不做的东西

1. **多危机并发**：不做"同时两个 active crisis"。队列是线性的，解决一个才露下一个。并发需要 UI 大改，不是 Phase 2。
2. **危机过期/超时**：不做。事件没有 deadline 计时器。"时间压力"由 adjudicator_notes 里的叙事来表达，不用代码强制。
3. **LLM 生成危机内容**：truth/brief 均由人工或预写 JSON 提供，不在运行时调 LLM 生成危机。保持"LLM 只当嘴与裁判"铁律。
4. **动态改写已入队危机**：一旦 event_to_crisis 完成，Crisis 对象不再被后续 effects 改写 brief/truth。级联只体现在"下一个新危机的注入时机和迷雾程度"。
5. **子指标 trigger_gate**：`army.X.arrears`、`region.X.unrest` 这类复杂门 Phase 2 跳过，Phase 4 再接。

**估算净增代码量**：`state.py` +1 行，`content.py` +~35 行（三个函数 + 切片修改），`play.py` +3 行。总计 ≤40 净行，远低于 150 上限。事件 JSON 需补 `truth` 字段（内容资产，不算代码）。

---

## 与 kernel Phase 1 的对齐说明

**cast 字段 schema**：本文假定 `Crisis.cast` 是一个 dict：`{"characters": [...名字列表...], "factions": [...群体列表...]}`。`event_to_crisis` 从 `ev["audiences"]`→characters、`ev["interests"]`→factions 派生。

**⚠️ 潜在冲突**：若 kernel 决定 cast 只存 id（而非名字），或加了 `regions` 子键，`event_to_crisis` 的 cast 构造行需同步调整。**建议 kernel 在 state.py 的 Crisis dataclass 注释里固定 cast 的 schema**，或在 Phase 1 PR 中给一个示例实例，Phase 2 再对齐实现。

---

## Worked Example：从 seed_event 到"入池→active→处置→resolved→触发下一个"

### 场景设定

切片：`dingwei`，崇祯元年十一月。初始 `event_pool` 含：
- `grain`（urgency=70，trigger_gate: `{"民心": "<=44"}`）
- `deficit`（urgency=82，trigger_gate: `{"国库": "<=24"}`，已归一化）
- `shaanxi`（urgency=68，trigger_gate: `{"region.shaanxi.unrest": ">=70"}`，点号跳过=门恒开）

初始指标：国库 22，民心 45，耳目 60。初始 `state.crises = [Crisis("wei", "如何处置魏忠贤", ...)]`。

---

### Step 1 — 危机 "wei" active

`active_crisis()` → Crisis(wei)。

皇帝召见王承恩、魏忠贤，得到模糊信号。最终下旨：「魏忠贤流放凤阳，厂卫大部裁撤，东厂并入兵部管辖」。

---

### Step 2 — adjudicate 推演

裁判 LLM 持有 truth（魏党外强中干，但厂卫是耳目命根）。

返回 JSON：
```json
{
  "narrative": "魏忠贤于十一月末奉旨就道，仅携数名仆从，出正阳门，望凤阳而去……东厂各档房人心惶惶，缴印者踉跄，各省镇守太监闻风辞别，情报网骤然稀疏……",
  "resolved": true,
  "effects": [
    {"target": "皇威", "direction": "+", "magnitude": "中", "reason": "新君定魏快刀，朝野见其决断"},
    {"target": "耳目", "direction": "-", "magnitude": "大", "reason": "厂卫瓦解，各省情报渠道断绝"},
    {"target": "东林.satisfaction", "direction": "+", "magnitude": "轻", "reason": "清流得志，弹劾目标落网"},
    {"target": "民心", "direction": "-", "magnitude": "微", "reason": "流放非株连，百姓无额外怨"}
  ]
}
```

`apply_effects` 执行：耳目 60 → **38**，皇威 28 → 40，民心 45 → 44。

---

### Step 3 — `cr.resolved = True`，调用 `next_from_pool(state)`

此刻指标：国库 22，民心 **44**，耳目 **38**。

评估 event_pool：
- `grain`：gate `{"民心": "<=44"}` → `44 <= 44` → **满足** ✓，urgency=70
- `deficit`：gate `{"国库": "<=24"}` → `22 <= 24` → **满足** ✓，urgency=82
- `shaanxi`：gate 含点号路径，**跳过**（视为满足），urgency=68

三者均满足，取 urgency 最高 → **`deficit`（urgency=82）**。

移出 pool，调用 `event_to_crisis(deficit, state)`：
- `耳目=38 < 40`，但 deficit.credibility=70（边界值），**不加迷雾**
- brief = deficit.summary（"户部称太仓银两不足…"）
- truth = deficit.truth（需补写："太仓实存约 220 万两，但江南积欠与宗禄虚报吃了大头，毕自严哭穷八分真……"）
- adjudicator_notes = "解决条件: 毕自严裁冗与开源并施… 失败条件: 国库见底致刚性支出违约…"
- cast = `{"characters": ["毕自严","韩爌","王承恩"], "factions": ["户部","边镇","百姓","士绅"]}`

返回 Crisis(deficit, "户部报亏空", brief=..., truth=..., cast=...)。

`state.crises.append(crisis_deficit)`。

---

### Step 4 — 新月开始

`active_crisis()` → Crisis(deficit，"户部报亏空")。

皇帝看到的 brief 如实呈现（耳目刚好没触发迷雾）。若上一步耳目跌到 35，而 credibility=68<70，下一个危机的 brief 就会带上"【消息语焉不详】"前缀——后果连锁落在信息层，不用新加任何维度。
