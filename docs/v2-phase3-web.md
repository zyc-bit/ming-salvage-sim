# v2 Phase 3 · 最小可玩网页设计

> 目标：把 `v2/play.py` 的终端闭环原样搬上浏览器，不多一行花活。

---

## 一、后端端点（8 个）

服务器侧维护一个全局 `_state: GameState | None`（MVP 单玩家，无 DB，无 auth）。
`summon_log` 和 `month_decree` 也挂在服务器内存里，随 `advance` 清空，随 `new/load` 重置。

```
POST /api/v2/game/new
  body:  { "slice_id": "dingwei" | "liaodong" }
  resp:  StatePayload            ← 见下节

POST /api/v2/saves/{slot}/load
  body:  (空)
  resp:  StatePayload

GET  /api/v2/game/state
  resp:  StatePayload

POST /api/v2/game/summon
  body:  { "name": "魏忠贤", "message": "卿以为如何？" }
  resp:  { "reply": "...奏对全文...", "energy": 2 }
  副作用: state.energy -= 1; 追加 summon_log

POST /api/v2/game/decree
  body:  { "text": "即日起褫夺魏忠贤一切职衔…" }
  resp:  { "ok": true }
  副作用: 覆写 month_decree

POST /api/v2/game/advance
  body:  (空，month_decree 已存服务器)
  resp:  AdvancePayload = { "narrative": "...", "resolved": bool,
                            "effects": [...], "notes": [...], "state": StatePayload }
  副作用: apply_effects、month+1、energy=3、summon_log=[]、month_decree=None

GET  /api/v2/saves
  resp:  { "slots": ["auto", "slot1", ...] }      ← SAVE_DIR 下 *.json 文件名去后缀

POST /api/v2/saves/{slot}
  body:  (空)
  resp:  { "slot": "auto", "saved_at": "..." }
```

### StatePayload 字段

```json
{
  "year": 1628, "month": 1, "energy": 3, "slice_id": "dingwei",
  "metrics": { "国库": 45, "皇威": 55, "民心": 60, "朝堂": 50, "耳目": 65, "边事": 40 },
  "factions": {
    "东林": { "name": "东林", "satisfaction": 62, "leverage": 68, "note": "..." }
  },
  "characters": [
    { "name": "魏忠贤", "office": "司礼监掌印太监", "faction": "阉党",
      "stance": "主动示好、探皇帝虚实", "active": true }
  ],
  "active_crisis": { "title": "九千岁去留", "brief": "魏忠贤犹掌司礼监…" },
  "month_decree": null,
  "chronicle": ["崇祯元年正月…"]
}
```

**信息不全原则**：`Character.secret` 和 `Crisis.truth` **不出现**在 StatePayload——这是 v2 铁律，前端永远看不见。

### 实现说明

- 入口文件 `v2/api.py`，用 `from fastapi import FastAPI` + `uvicorn`
- `dataclasses.asdict(state)` 直接序列化，再手动删去 `secret` / `truth` 字段后返回
- 读 `.env` 的 `OPENAI_*` 环境变量，与 `v2/llm.py` 完全共用
- 不引入 SQLite、不引入 SQLAlchemy、不引入 v1 的任何持久层

---

## 二、前端薄壳（目标 650–850 行）

### 布局：五块

```
┌─────────────────────────────────────────────────────┐
│  局势面板（左侧竖条，固定宽度）                        │
│  · 年月 / 精力点（⬤⬤⬤）                             │
│  · 6 国势条（名字 + 数值 + 细横条）                   │
│  · 势力满意/能量（2 行）                              │
│  · 当前危机标题 + brief                              │
│  · [存档] [读档] 按钮                                │
├──────────┬──────────────────────────────────────────┤
│ 大臣列表  │  聊天流（召对记录，可滚动）                 │
│ (大臣名   │                                          │
│  + 官职   │  ┌────────────────────────────────────┐ │
│  + 立绘   │  │ 帝：卿以为如何？                     │ │
│  thumbnail│  │ 魏忠贤：臣伏惟陛下圣明…（全文）       │ │
│  点击=召见│  └────────────────────────────────────┘ │
│           │                                          │
│           │  [输入框]  [召见]                         │
│           ├──────────────────────────────────────────┤
│           │  下旨区                                   │
│           │  [旨意 textarea]  [拟旨]  [退朝·推演]     │
│           │  推演结果：邸报 narrative + 效果 notes     │
└──────────┴──────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  LLM 设置折叠条（默认收起）                           │
│  API Key / Model / Base URL / [保存]                 │
└─────────────────────────────────────────────────────┘
```

### 原样复用清单

| 资产 | 文件 | 复用方式 |
|------|------|---------|
| CSS 设计 token（`:root`） | `web/src/styles.css` 全文 | 直接 import，无修改 |
| `.game-shell` 背景渐变 | 同上 | className 复用 |
| `.loading-screen` / `.loading-panel` | 同上 | 加载中状态 |
| SSE 客户端 `api()` | `main.tsx:392-402` | 抄 ~11 行到新文件 |
| `parseSseMessage()` | `main.tsx:404-417` | 抄 ~14 行到新文件 |
| 大臣立绘 | `web/public/portraits/minister_*.png` | `<img src="/portraits/minister_{name}.png">` |
| 背景图 | `web/public/bg_chat.webp`、`bg_state.png`、`bg_edict.png` | 面板背景 |
| Vite/React 构建配置 | `web/package.json`、`vite.config.ts` | 只新增 v2 入口，不动现有 v1 entry |

### 新写清单

| 内容 | 估计行数 |
|------|---------|
| `web/src/v2/App.tsx`（主组件树，含 5 个面板） | ~620 行 |
| `web/src/v2/api.ts`（`api()` + `parseSseMessage()` + 类型定义） | ~80 行 |
| `web/src/v2/main.tsx`（挂载点） | ~10 行 |
| CSS 新增（v2 专属组件样式，附在现有 styles.css 末尾） | ~130 行 |
| Vite 新入口配置（`vite.config.v2.ts`） | ~25 行 |
| **合计** | **~865 行** |

**React 状态**（全在 `App.tsx` 顶层 `useState`，不引入 Redux/Context）：

```ts
const [state, setState]       = useState<GameState | null>(null);
const [chatLog, setChatLog]   = useState<ChatEntry[]>([]);
const [decree, setDecree]     = useState("");
const [busy, setBusy]         = useState(false);     // LLM 请求中
const [narrative, setNarrative] = useState("");       // 上一次推演邸报
const [activeChar, setActiveChar] = useState<string | null>(null);
```

---

## 三、Salvage 纪律

### 为什么不套 `main.tsx`

`main.tsx` 4476 行，与 v1 的 `Region / Army / Power / Building / MapNode / Minister / Consort` 等 10+ 类型深度绑定。v2 的 `GameState` 只有 `metrics / factions / characters / crises`——结构差距太大，改造成本远超从零写一个 700 行的薄壳。逐字段适配会把两套 schema 的耦合藏进代码，给后续演进留下隐患。

### 具体复用决断

| v1 资产 | 决断 | 理由 |
|---------|------|------|
| `styles.css` `:root` token | **全量复用** | 颜色/字体是品牌一致性，与数据模型无关 |
| `.game-shell` 等布局 CSS | **复用 className** | 背景渐变逻辑不变 |
| `api()` fetch 包装 | **抄 11 行** | 通用到任何 JSON API，不带 v1 依赖 |
| `parseSseMessage()` | **抄 14 行** | 纯字符串解析，零依赖 |
| `streamChat()` | **不复用** | 路径硬编码 v1 端点，SSE 事件名也不同；v2 SSE 是后续增强，到时重写 |
| 大臣立绘 `/portraits/minister_*.png` | **直接引用** | 按 `name` 拼路径，无需改文件 |
| `web_app.py` 端点逻辑 | **不复用** | 深绑 `GameSession`（v1 SQLite ORM），v2 是纯内存 dataclass |
| v1 组件树（`WebGame`, `MapView`, `HaremView`…） | **不复用** | v2 无地图、无后宫、无历史浏览 |

---

## 四、构建顺序（4 步最小路径）

### Step 1：非流式后端 + 最简前端（闭环优先）

目标：能在浏览器里走完「开局 → 召见 → 下旨 → 退朝」一个月。

- 写 `v2/api.py`（8 个端点，全非流式）
- 写 `web/src/v2/App.tsx`（5 块粗布局，无美术）
- `api()` 调 `/api/v2/game/summon` → 等待 → 渲染纯文字回复
- `api()` 调 `/api/v2/game/advance` → 渲染邸报 narrative + effects notes
- **交付物**：`uvicorn v2.api:app` + `vite --config vite.config.v2.ts` 可跑通闭环

### Step 2：流式召对 + 存读档 UI

目标：召对体验流畅；存档/读档按钮可用。

- 在后端加 `POST /api/v2/game/summon/stream`（SSE，`delta` event 流字符）
- 前端 `parseSseMessage()` 接流，边收边渲染
- 加存档列表下拉 + [存档] [读档] 按钮，调 `/api/v2/saves`

### Step 3：美术贴图

目标：视觉达到 v1 水准。

- 局势面板用 `bg_state.png` 背景
- 聊天区用 `bg_chat.webp`
- 下旨区用 `bg_edict.png`
- 大臣列表加立绘 thumbnail（`/portraits/minister_{name}.png`，找不到则默认图）
- 调整 `:root` token 已有的颜色类名与边距

### Step 4：LLM 设置持久化

目标：玩家能在浏览器里配 API Key，不必改 `.env`。

- 后端加 `GET/POST /api/v2/llm_config`，读写本地 `data/v2_llm.json`
- 前端设置折叠条写入并即时生效

---

## 五、净行数估算

| 文件 | 行数 |
|------|------|
| `v2/api.py` | ~200 |
| `web/src/v2/App.tsx` | ~620 |
| `web/src/v2/api.ts` | ~80 |
| `web/src/v2/main.tsx` | ~10 |
| `web/src/styles.css`（新增 v2 组件样式段） | ~130 |
| `vite.config.v2.ts` | ~25 |
| **总计新增** | **~1065 行** |

已有代码零修改：`v2/state.py`、`v2/llm.py`、`v2/save.py`、`v2/engine.py`、`web/src/styles.css`（追加，不改现有行）。

---

## 六、明确不做清单（Phase 3 一律不做）

- 地图 / 地区面板（无 `Region` / `Army` 数据渲染）
- 后宫系统（`HaremView`、妃嫔数据）
- 历史浏览器（回溯某月详情）
- 密令 / 秘密处置（`SecretOrder`）
- 朝议流程（大臣 propose_directive → pending → 准/驳）
- 多玩家 / 用户账户 / JWT
- 地理计算 / 兵力战役模拟
- 建筑 / 财政流水详表
- 手机端适配（桌面宽屏优先）
- Docker / 打包发布流程

---

## 附：Phase 2 事件池兼容说明

Phase 2 正在给月推进加事件池。影响：`engine.apply_effects` 的调用方可能从一个变多个（推演 + 随机事件），`GameState` 可能多几个字段（如 `pending_events`）。

网页操作面（召见 / 下旨 / 退朝）对这些内部机制**完全透明**：

- `POST /api/v2/game/advance` 永远返回 `AdvancePayload`，后端内部调用几次 `apply_effects` 是实现细节
- `StatePayload` 新增字段时，前端只需在局势面板末尾加一段渲染，不影响其余五块
- SSE 流式接口与事件池无交叉
