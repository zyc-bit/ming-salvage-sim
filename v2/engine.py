"""推演内核:把裁判 LLM 的「定性效果」确定性地落成数值。

关键:LLM 给方向与档位(定性)+ 叙事,代码做档位→数值的唯一映射。
单层 LLM、不反向从叙事里抠数字 —— 这是 v2 区别于旧架构的核心。
"""
from .state import GameState

MAGNITUDE = {"微": 3, "轻": 6, "中": 12, "大": 22, "极": 40}


def _clamp(v: int) -> int:
    return max(0, min(100, v))


def apply_effects(state: GameState, effects: list) -> list:
    """effects: [{target, direction:'+'/'-', magnitude:'微/轻/中/大/极', reason}]
    target: 国势名(如'皇威') | '势力名.satisfaction|leverage' | '人物名.loyalty|ability'
    返回人话变化清单,供邸报附注/史册留痕。
    """
    notes = []
    for e in effects or []:
        target = str(e.get("target", "")).strip()
        sign = 1 if str(e.get("direction", "+")) != "-" else -1
        amt = MAGNITUDE.get(str(e.get("magnitude", "中")), 12) * sign
        reason = str(e.get("reason", "")).strip()
        if not target:
            continue
        if "." in target:
            owner, attr = (s.strip() for s in target.split(".", 1))
            obj = state.factions.get(owner) or state.characters.get(owner)
            if obj is None or not hasattr(obj, attr) or not isinstance(getattr(obj, attr), int):
                continue
            setattr(obj, attr, _clamp(getattr(obj, attr) + amt))
            notes.append(f"{owner}·{attr} {amt:+d}（{reason}）")
        elif target in state.metrics:
            state.metrics[target] = _clamp(state.metrics[target] + amt)
            notes.append(f"{target} {amt:+d}（{reason}）")
    return notes
