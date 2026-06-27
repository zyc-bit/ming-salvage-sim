// v2 API 客户端。api() 和 parseSseMessage() 来自 v1 main.tsx:392-417。

export type Faction = {
  name: string;
  satisfaction: number;
  leverage: number;
  note: string;
};

// 白名单投影:只含玩家该看到的字段(无 loyalty/ability/secret/persona)
export type Character = {
  name: string;
  office: string;
  faction: string;
  stance: string;
  active: boolean;
};

export type GameState = {
  year: number;
  month: number;
  slice_id: string;
  metrics: Record<string, number>;
  factions: Faction[];          // 数组,顺序稳定
  characters: Character[];
  active_crisis: { title: string; brief: string } | null;
  month_decree: string | null;
  chronicle: string[];
};

export type AdvanceResult = {
  narrative: string;
  resolved: boolean;
  effects: { target: string; direction: string; magnitude: string; reason: string }[];
  notes: string[];
  state: GameState;
};

export type LlmConfig = { model: string; base_url: string; has_key: boolean };

// 复用自 v1 main.tsx:392-402
export const api = async <T,>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err?.detail || response.statusText);
  }
  return response.json();
};

// 复用自 v1 main.tsx:404-417
export const parseSseMessage = (raw: string): { event: string; data: string } | null => {
  const lines = raw.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n") };
};
