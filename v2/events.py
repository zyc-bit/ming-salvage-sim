"""v2 内联事件池。

事件 dict 结构：id/title/brief/truth/adjudicator_notes/cast(id列表)/trigger_gate/urgency/credibility。
cast 只放 region/army/power 的 id——characters/factions 已活在 state，不重复。
truth 人工撰写，只喂裁判 LLM，玩家不可见。
"""
from .state import Crisis

# ── dingwei 切片的后续事件池（2条），urgency 决定出队顺序）─────────────────────
DINGWEI_POOL = [
    {
        "id": "deficit",
        "title": "户部亏空",
        "brief": (
            "户部尚书毕自严具题：太仓存银不足三百万，辽饷、京营、官俸、赈济四项轮番告急，"
            "月月赤字，奏称若不及时筹源，恐不支半载。"
        ),
        "truth": (
            "太仓实存银约二百余万两，但江南积欠、宗室禄米虚报与火耗截留吃掉大半——"
            "毕自严哭穷八分真。月刚性支出（辽饷+京营+官俸）已达三十万上下，"
            "无新财源则半年内国库见底。可动用渠道：催江南积欠（远水）、缓宗禄（激宗藩不满）、"
            "催盐课（得罪盐商）、动内帑（陛下自掏，有限）。强加赋则民心大跌、埋民变之祸。"
        ),
        "adjudicator_notes": (
            "财政裁判要点：钱不是说有就有，严守资源约束。"
            "清欠/催盐/缓宗禄需时，本月到不了账；动内帑最多解燃眉、不可持续；"
            "强加派则民心大跌可能激民变；只颁空头支票、无实银落地则 resolved=False 且国库继续下滑。"
            "玩家若同时给出具体筹银渠道并有相应人事配合（毕自严主事），可 resolved=True。"
        ),
        "cast": [],           # 财政危机无特定地区/军队背景
        "trigger_gate": {},   # 无触发门，陕西民变解决后接棒
        "urgency": 65,
        "credibility": 70,
    },
    {
        "id": "shaanxi_unrest",
        "title": "陕西民变苗头",
        "brief": (
            "陕西巡按奏报：连岁亢旱，逃户成群，驿卒、饥民与盗匪渐混。"
            "王嘉胤、王二之徒已起，地方官称尚可弹压。"
        ),
        "truth": (
            "地方官严重瞒报：陕西流民聚众已达数千，王嘉胤部众持刀兵、据险要，"
            "「尚可弹压」纯为塞责。大批失业驿卒投寇使其组织力骤增。"
            "若不在一季内拨赈银+以工代赈+调兵招抚三策并举，流民攻州县之势不可收拾；"
            "单纯加派兵剿而无赈济，只会催出更大民变；"
            "拖延则陕西与山西、河南流民合流，演成崇祯朝贯穿始终的心腹大患。"
        ),
        "adjudicator_notes": (
            "民变裁判要点：赈银与以工代赈若一季内到位且有可信地方官主事，可化解（resolved=True）。"
            "单剿不赈必激变；空头支票无银落地则民变加剧（resolved=False）。"
            "玩家召对韩爌/毕自严可获更接近真相的情报（地方奏报不可全信）。"
            "注意：此时耳目若因定魏废厂卫而骤降，地方塘报可信度已大打折扣，"
            "裁判应将玩家所获信息按耳目水平酌情打折。"
        ),
        "cast": ["shaanxi", "shaanxi_army", "bandits"],
        "trigger_gate": {},   # 无触发门，定魏解决后第一个接棒
        "urgency": 80,
        "credibility": 50,    # 低可信度：耳目<40 时 brief 加迷雾前缀
    },
]


def _gate_met(gate, metrics):
    """仅评估 METRIC_KEYS 简单门；点号子指标路径静默跳过（视为满足）。"""
    for k, expr in gate.items():
        if "." in k or k not in metrics:
            continue
        op, num = expr[:2], int(expr[2:])
        if op == "<=" and not (metrics[k] <= num):
            return False
        if op == ">=" and not (metrics[k] >= num):
            return False
    return True


def event_to_crisis(ev, state):
    """把事件 dict 转成 Crisis；低耳目×低可信度时在 brief 加迷雾前缀。"""
    brief = ev["brief"]
    if state.metrics.get("耳目", 60) < 40 and ev.get("credibility", 100) < 70:
        brief = "【消息语焉不详，各省塘报真假难辨】" + brief
    return Crisis(
        id=ev["id"], title=ev["title"],
        brief=brief, truth=ev["truth"],
        adjudicator_notes=ev.get("adjudicator_notes", ""),
        cast=list(ev.get("cast", [])),
    )


def next_from_pool(state):
    """从事件池取下一个满足触发门的最高 urgency 事件，转成 Crisis 并移出池。"""
    eligible = [e for e in state.event_pool
                if _gate_met(e.get("trigger_gate", {}), state.metrics)]
    if not eligible:
        return None
    ev = max(eligible, key=lambda e: e.get("urgency", 0))
    state.event_pool.remove(ev)
    return event_to_crisis(ev, state)
