"""LLM 的两个介入点:召见(扮演大臣) + 天下裁判(定性效果 + 邸报)。
直接用 OpenAI 兼容接口,读项目根 .env 的 OPENAI_* 配置。
"""
import os
import json
import re
import httpx
from openai import OpenAI

from . import world

_client = None


def _c():
    global _client
    if _client is None:
        # 尊重 .env 的 OPENAI_TRUST_ENV(CN/本地兼容端点常需绕过系统代理)与超时
        trust_env = os.environ.get("OPENAI_TRUST_ENV", "true").strip().lower() != "false"
        timeout = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "180") or 180)
        _client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
            timeout=timeout,
            http_client=httpx.Client(trust_env=trust_env, timeout=timeout),
        )
    return _client


def _model():
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _scene(state):
    cr = state.active_crisis()
    facs = "；".join(f"{f.name}(满意{f.satisfaction}/能量{f.leverage})" for f in state.factions.values())
    if state.slice_id == "dingwei":
        head = (f"【时局】天启七年末,{state.year}年{state.month}月,信王朱由检新承大统。\n"
                f"【国势】{state.metric_line()}（耳目=情报力)\n"
                f"【朝局】{facs}")
    else:
        head = (f"【时局】{state.year}年{state.month}月。\n"
                f"【国势】{state.metric_line()}（耳目=情报力)\n"
                f"【朝局】{facs}")
    if cr:
        head += f"\n【当前大事】{cr.title}：{cr.brief}"
        head += world.backdrop(cr.cast)  # 危机点名了真实地区/军队/势力才追加;否则空串、行为不变
    return head


def summon(state, name, history, player_msg):
    ch = state.characters[name]
    sys = (f"你扮演明末{ch.office}{ch.name},被刚登基的崇祯帝召见奏对。\n"
           f"性格:{ch.persona}。当前立场:{ch.stance}。\n"
           f"你私下知道、却未必敢明说的:{ch.secret}\n\n"
           f"{_scene(state)}\n\n"
           "用明末君臣奏对的口吻,80-180字。可顺承、可进谏、可哭穷、可试探、可避重就轻,"
           "须合你的忠诚与城府,不要一五一十全交底。只说这个人物会说的话——不出戏、不报游戏数值、不写旁白。")
    msgs = [{"role": "system", "content": sys}]
    for role, text in history:
        msgs.append({"role": "user" if role == "帝" else "assistant", "content": text})
    msgs.append({"role": "user", "content": f"(崇祯)：{player_msg}"})
    r = _c().chat.completions.create(model=_model(), messages=msgs, temperature=0.8)
    return r.choices[0].message.content.strip()


_ADJ_SYS = """你是这局《明末》的天下裁判。皇帝刚下了一道处置旨意,你要推演它落到天下的真实结果。

裁判铁律:
- 君命直贯:人事、刑赏(诛/罢/贬/赦/赏)这类,皇帝一旨即生效,不打折,别写「廷议未决」拖延。
- 但每个手段都有代价与连锁:按当前国势、势力立场推演谁喜谁怒、得了什么、失了什么。参考【真相】判定,但真相不直接示玩家。
- 没有最优解:每个手段都有代价与连锁,按当前盘面推演谁喜谁怒、得失各几。

只输出一个 JSON(不要任何别的字、不要代码围栏):
{
 "narrative": "150-300字邸报体叙事,有人有地有冷暖,写出这道旨在京城激起的涟漪与代价",
 "resolved": true,
 "effects": [
   {"target":"皇威","direction":"+","magnitude":"中","reason":"处置显出决断"},
   {"target":"国库","direction":"-","magnitude":"轻","reason":"措置耗费钱粮"},
   {"target":"边事","direction":"+","magnitude":"轻","reason":"边防暂得支撑"}
 ]
}
"resolved": 这道旨是否已把『当前大事』了结(true/false)。
克制原则:effects 聚焦 2-4 个最相关的国势/势力,不必每项都动;同一回合「大」「极」档至多 1-2 项,余者用 中/轻/微 分出主次;维持现状的数值不给 effect(别「按兵不动」却还加分)。
"effects" 给 2-5 条,正负都要有、体现取舍。target 只能是:
  国势(国库/皇威/民心/朝堂/耳目/边事)、或当前盘面里的『势力名.satisfaction』『势力名.leverage』、或『人物名.loyalty』。
reason 一律用中文不夹英文单词。
magnitude 只能是 微/轻/中/大/极。"""


def adjudicate(state, decree, summon_log):
    cr = state.active_crisis()
    truth = f"\n【真相(仅你裁判可见,勿直白示玩家)】{cr.truth}" if cr else ""
    notes = f"\n【本案裁判要点】{cr.adjudicator_notes}" if cr and cr.adjudicator_notes else ""
    convo = "\n".join(f"[{who}] {text}" for who, text in summon_log) or "(本月未召见臣工)"
    user = (f"{_scene(state)}{truth}{notes}\n\n【本月召对摘要】\n{convo}\n\n"
            f"【皇帝旨意】{decree}\n\n按裁判铁律输出 JSON。")
    r = _c().chat.completions.create(
        model=_model(),
        messages=[{"role": "system", "content": _ADJ_SYS}, {"role": "user", "content": user}],
        temperature=0.7,
    )
    return _parse_json(r.choices[0].message.content)


def _parse_json(text):
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    raw = m.group(0) if m else text
    try:
        return json.loads(raw)
    except Exception:
        return {"narrative": text[:600] or "(裁判推演解析失败)", "resolved": False, "effects": []}
