import React, { useEffect, useRef, useState } from "react";
import { api, GameState, AdvanceResult, LlmConfig } from "./api";

type ChatEntry = { who: string; text: string; k: number };
let _key = 0;
const ck = () => ++_key;

const METRIC_KEYS = ["国库", "皇威", "民心", "朝堂", "耳目", "边事"];
const METRIC_COLOR: Record<string, string> = {
  国库: "var(--gold)", 皇威: "var(--red)", 民心: "var(--jade)",
  朝堂: "var(--blue)", 耳目: "var(--muted)", 边事: "#7a5430",
};

// ── 局势面板 ────────────────────────────────────────────────────────────────
function StatusPanel({
  gs, saves, saveSlot, setSaveSlot, onSave, onLoad, onNewGame, busy,
}: {
  gs: GameState; saves: string[]; saveSlot: string;
  setSaveSlot: (s: string) => void;
  onSave: () => void; onLoad: (slot: string) => void;
  onNewGame: (sliceId: string) => void; busy: boolean;
}) {
  const cr = gs.active_crisis;

  return (
    <div className="v2-status-panel">
      <div className="v2-status-header">
        <div className="v2-year-month">{gs.year}年{gs.month}月</div>
      </div>

      <div className="v2-section-label">国势</div>
      {METRIC_KEYS.map(k => (
        <div key={k} className="v2-metric-row">
          <span className="v2-metric-name">{k}</span>
          <div className="v2-metric-track">
            <div
              className="v2-metric-fill"
              style={{ width: `${gs.metrics[k] ?? 0}%`, background: METRIC_COLOR[k] }}
            />
          </div>
          <span className="v2-metric-val">{gs.metrics[k] ?? 0}</span>
        </div>
      ))}

      <div className="v2-section-label" style={{ marginTop: 12 }}>朝局势力</div>
      {gs.factions.map(f => (
        <div key={f.name} className="v2-faction-row">
          <span className="v2-faction-name">{f.name}</span>
          <span className="v2-faction-stat">满{f.satisfaction}</span>
          <span className="v2-faction-stat">势{f.leverage}</span>
        </div>
      ))}

      {cr && (
        <>
          <div className="v2-section-label" style={{ marginTop: 12 }}>当前大事</div>
          <div className="v2-crisis-title">◆ {cr.title}</div>
          <div className="v2-crisis-brief">{cr.brief}</div>
        </>
      )}

      {gs.month_decree && (
        <div className="v2-decree-badge">旨：{gs.month_decree}</div>
      )}

      <div className="v2-save-row">
        <select
          className="v2-save-select"
          value={saveSlot}
          onChange={e => setSaveSlot(e.target.value)}
        >
          {saves.length === 0 && <option value="auto">auto</option>}
          {saves.map(s => <option key={s} value={s}>{s}</option>)}
          {!saves.includes(saveSlot) && <option value={saveSlot}>{saveSlot}</option>}
        </select>
        <button className="v2-btn-sm" onClick={onSave} disabled={busy}>存档</button>
        <button className="v2-btn-sm" onClick={() => onLoad(saveSlot)} disabled={busy}>读档</button>
      </div>

      <div className="v2-newgame-row">
        <button className="v2-btn-sm" onClick={() => onNewGame("dingwei")} disabled={busy}>定魏</button>
        <button className="v2-btn-sm" onClick={() => onNewGame("liaodong")} disabled={busy}>辽东</button>
      </div>
    </div>
  );
}

// ── 大臣列表 ────────────────────────────────────────────────────────────────
function CharacterList({
  gs, activeChar, onSelect,
}: {
  gs: GameState; activeChar: string | null; onSelect: (name: string) => void;
}) {
  return (
    <div className="v2-char-panel">
      <div className="v2-section-label">召见臣工</div>
      {gs.characters.filter(c => c.active).map(c => (
        <button
          key={c.name}
          className={`v2-char-card ${activeChar === c.name ? "v2-char-active" : ""}`}
          onClick={() => onSelect(c.name)}
        >
          <img
            className="v2-portrait"
            src={`/portraits/minister_${c.name}.png`}
            alt={c.name}
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
          <div className="v2-char-info">
            <div className="v2-char-name">{c.name}</div>
            <div className="v2-char-office">{c.office}</div>
            <div className="v2-char-stance">{c.stance.slice(0, 24)}{c.stance.length > 24 ? "…" : ""}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

// ── 聊天记录 ────────────────────────────────────────────────────────────────
function ChatLog({ entries }: { entries: ChatEntry[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [entries]);
  return (
    <div className="v2-chat-log" ref={ref}>
      {entries.length === 0 && (
        <div className="v2-chat-empty">（点击左侧大臣可召见奏对）</div>
      )}
      {entries.map(e => (
        <div key={e.k} className={`v2-chat-entry ${e.who === "帝" ? "v2-chat-emperor" : "v2-chat-minister"}`}>
          <span className="v2-chat-who">{e.who}：</span>
          <span className="v2-chat-text">{e.text}</span>
        </div>
      ))}
    </div>
  );
}

// ── 下旨与推演 ────────────────────────────────────────────────────────────
function ActionArea({
  gs, decree, setDecree, activeChar, input, setInput,
  onSummon, onSetDecree, onAdvance, busy, narrative, notes, error,
}: {
  gs: GameState; decree: string; setDecree: (s: string) => void;
  activeChar: string | null; input: string; setInput: (s: string) => void;
  onSummon: (name: string, msg: string) => void;
  onSetDecree: (text: string) => void;
  onAdvance: () => void;
  busy: boolean; narrative: string; notes: string[]; error: string;
}) {
  const handleSummon = () => {
    if (!activeChar || !input.trim() || busy) return;
    onSummon(activeChar, input.trim());
    setInput("");
  };

  return (
    <div className="v2-action-area">
      {activeChar && (
        <div className="v2-summon-row">
          <input
            className="v2-summon-input"
            placeholder={`问${activeChar}…`}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSummon(); } }}
            disabled={busy}
          />
          <button
            className="v2-btn"
            onClick={handleSummon}
            disabled={busy || !input.trim()}
          >
            {busy ? "…" : "召见"}
          </button>
        </div>
      )}

      <div className="v2-decree-row">
        <textarea
          className="v2-decree-textarea"
          placeholder="拟旨……（留空则留中观望）"
          value={decree}
          onChange={e => setDecree(e.target.value)}
          rows={2}
          disabled={busy}
        />
        <div className="v2-decree-buttons">
          <button
            className="v2-btn"
            onClick={() => onSetDecree(decree)}
            disabled={busy || !decree.trim()}
          >
            拟旨
          </button>
          <button
            className="v2-btn v2-btn-advance"
            onClick={onAdvance}
            disabled={busy}
          >
            {busy ? "…推演中…" : "退朝·推演"}
          </button>
        </div>
      </div>

      {error && <div className="v2-error">{error}</div>}

      {narrative && (
        <div className="v2-narrative">
          <div className="v2-narrative-title">【邸报】</div>
          <div className="v2-narrative-text">{narrative}</div>
          {notes.length > 0 && (
            <div className="v2-notes">〔档房〕{notes.join("；  ")}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── LLM 设置折叠条 ──────────────────────────────────────────────────────────
function SettingsBar({
  llm, show, setShow,
}: {
  llm: LlmConfig | null; show: boolean; setShow: (b: boolean) => void;
}) {
  const [form, setForm] = useState({ api_key: "", model: "", base_url: "" });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const handleSave = async () => {
    setSaving(true);
    try {
      await api("/api/v2/llm", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setMsg("已更新（重启后失效）");
    } catch (e: any) {
      setMsg(`错误：${e.message}`);
    }
    setSaving(false);
  };

  return (
    <div className="v2-settings-bar">
      <button className="v2-settings-toggle" onClick={() => setShow(!show)}>
        ⚙ LLM 设置 {show ? "▲" : "▼"}
        {llm && <span className="v2-settings-model">（{llm.model}{llm.has_key ? "" : " · 无 Key"}）</span>}
      </button>
      {show && (
        <div className="v2-settings-body">
          <input className="v2-settings-input" placeholder="API Key（留空保持现有）"
            type="password" value={form.api_key}
            onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
          <input className="v2-settings-input" placeholder={`Model（当前：${llm?.model ?? "未知"}）`}
            value={form.model}
            onChange={e => setForm(f => ({ ...f, model: e.target.value }))} />
          <input className="v2-settings-input" placeholder={`Base URL（当前：${llm?.base_url || "默认"}）`}
            value={form.base_url}
            onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))} />
          <button className="v2-btn" onClick={handleSave} disabled={saving}>保存</button>
          {msg && <span className="v2-settings-msg">{msg}</span>}
        </div>
      )}
    </div>
  );
}

// ── 菜单屏 ──────────────────────────────────────────────────────────────────
function MenuScreen({ onStart, busy }: { onStart: (sliceId: string) => void; busy: boolean }) {
  return (
    <div className="v2-menu-screen game-shell">
      <div className="v2-menu-card">
        <h1 className="v2-menu-title">明末·力挽狂澜</h1>
        <p className="v2-menu-sub">你是崇祯。天下已是一盘碎棋——你来收。</p>
        <div className="v2-menu-buttons">
          <button className="v2-btn v2-btn-lg" onClick={() => onStart("dingwei")} disabled={busy}>
            第一刀 · 定魏
            <span className="v2-btn-sub">崇祯元年十一月 / 如何处置魏忠贤</span>
          </button>
          <button className="v2-btn v2-btn-lg" onClick={() => onStart("liaodong")} disabled={busy}>
            第二刀 · 辽东索饷
            <span className="v2-btn-sub">崇祯元年四月 / 关宁军欠饷四月</span>
          </button>
        </div>
        {busy && <div className="v2-loading">开局中…</div>}
      </div>
    </div>
  );
}

// ── 终局屏 ──────────────────────────────────────────────────────────────────
function EndedScreen({ gs, onMenu }: { gs: GameState; onMenu: () => void }) {
  return (
    <div className="v2-ended-screen game-shell">
      <div className="v2-ended-card">
        <h2 className="v2-ended-title">【史册】</h2>
        <div className="v2-ended-metrics">
          {METRIC_KEYS.map(k => (
            <div key={k} className="v2-metric-row">
              <span className="v2-metric-name">{k}</span>
              <div className="v2-metric-track">
                <div className="v2-metric-fill" style={{ width: `${gs.metrics[k] ?? 0}%`, background: METRIC_COLOR[k] }} />
              </div>
              <span className="v2-metric-val">{gs.metrics[k] ?? 0}</span>
            </div>
          ))}
        </div>
        <div className="v2-ended-chronicle">
          {gs.chronicle.map((entry, i) => (
            <div key={i} className="v2-ended-entry">{entry}</div>
          ))}
        </div>
        <button className="v2-btn v2-btn-lg" style={{ marginTop: 24 }} onClick={onMenu}>
          返回主菜单
        </button>
      </div>
    </div>
  );
}

// ── 主应用 ──────────────────────────────────────────────────────────────────
export function App() {
  const [screen, setScreen] = useState<"menu" | "game" | "ended">("menu");
  const [gs, setGs] = useState<GameState | null>(null);
  const [chatLog, setChatLog] = useState<ChatEntry[]>([]);
  const [activeChar, setActiveChar] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [decree, setDecree] = useState("");
  const [busy, setBusy] = useState(false);
  const [narrative, setNarrative] = useState("");
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saves, setSaves] = useState<string[]>([]);
  const [saveSlot, setSaveSlot] = useState("auto");
  const [llm, setLlm] = useState<LlmConfig | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    api<LlmConfig>("/api/v2/llm").then(setLlm).catch(() => {});
    api<{ slots: string[] }>("/api/v2/saves").then(r => setSaves(r.slots)).catch(() => {});
  }, []);

  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e: any) {
      setError(e.message || "请求失败");
    } finally {
      setBusy(false);
    }
  };

  const applyState = (newGs: GameState) => {
    setGs(newGs);
    if (!newGs.active_crisis) setScreen("ended");
    else setScreen("game");
  };

  const handleNewGame = (sliceId: string) =>
    withBusy(async () => {
      const s = await api<GameState>("/api/v2/game/new", {
        method: "POST",
        body: JSON.stringify({ slice_id: sliceId }),
      });
      setChatLog([]);
      setActiveChar(null);
      setDecree("");
      setNarrative("");
      setNotes([]);
      applyState(s);
      // 刷新存档列表
      api<{ slots: string[] }>("/api/v2/saves").then(r => setSaves(r.slots)).catch(() => {});
    });

  const handleSummon = (name: string, msg: string) =>
    withBusy(async () => {
      setChatLog(prev => [...prev, { who: "帝", text: msg, k: ck() }]);
      const r = await api<{ reply: string }>("/api/v2/game/summon", {
        method: "POST",
        body: JSON.stringify({ name, message: msg }),
      });
      setChatLog(prev => [...prev, { who: name, text: r.reply, k: ck() }]);
    });

  const handleSetDecree = (text: string) =>
    withBusy(async () => {
      await api("/api/v2/game/decree", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      setGs(prev => prev ? { ...prev, month_decree: text || null } : prev);
    });

  const handleAdvance = () =>
    withBusy(async () => {
      const r = await api<AdvanceResult>("/api/v2/game/advance", { method: "POST" });
      setNarrative(r.narrative);
      setNotes(r.notes);
      setDecree("");
      applyState(r.state);
    });

  const handleSave = () =>
    withBusy(async () => {
      await api(`/api/v2/saves/${encodeURIComponent(saveSlot)}`, { method: "POST" });
      const r = await api<{ slots: string[] }>("/api/v2/saves");
      setSaves(r.slots);
    });

  const handleLoad = (slot: string) =>
    withBusy(async () => {
      const s = await api<GameState>(`/api/v2/saves/${encodeURIComponent(slot)}/load`, { method: "POST" });
      setChatLog([]);
      setActiveChar(null);
      setDecree("");
      setNarrative("");
      setNotes([]);
      applyState(s);
    });

  if (screen === "menu") {
    return <MenuScreen onStart={handleNewGame} busy={busy} />;
  }

  if (screen === "ended" && gs) {
    return <EndedScreen gs={gs} onMenu={() => setScreen("menu")} />;
  }

  if (!gs) return null;

  return (
    <div className="v2-shell game-shell">
      <StatusPanel
        gs={gs}
        saves={saves}
        saveSlot={saveSlot}
        setSaveSlot={setSaveSlot}
        onSave={handleSave}
        onLoad={handleLoad}
        onNewGame={handleNewGame}
        busy={busy}
      />
      <CharacterList
        gs={gs}
        activeChar={activeChar}
        onSelect={name => { setActiveChar(name === activeChar ? null : name); setInput(""); }}
      />
      <div className="v2-right-col">
        <ChatLog entries={chatLog} />
        <ActionArea
          gs={gs}
          decree={decree}
          setDecree={setDecree}
          activeChar={activeChar}
          input={input}
          setInput={setInput}
          onSummon={handleSummon}
          onSetDecree={handleSetDecree}
          onAdvance={handleAdvance}
          busy={busy}
          narrative={narrative}
          notes={notes}
          error={error}
        />
        <SettingsBar llm={llm} show={showSettings} setShow={setShowSettings} />
      </div>
    </div>
  );
}
