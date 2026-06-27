"""《明末》v2 终端表现层:开场白、御案展示、终局史评等与 CLI 输出耦合的文案。
play.py 只管驱动循环,这些表现文案集中收在此处。
"""

LINE = "─" * 58


def banner(state):
    cr = state.active_crisis()
    print(LINE)
    if state.slice_id == "dingwei":
        print("《明末·崇祯元年 —— 定魏》   第一垂直切片")
        print("天启七年十一月,信王朱由检入承大统。魏忠贤犹掌司礼监、东厂。")
        print("你是崇祯。登基第一道大题:这权倾朝野的九千岁,你怎么办?")
    else:
        print(f"《明末·崇祯元年 —— {cr.title if cr else '无事'}》   第二垂直切片")
        if cr:
            print(cr.brief)
    print(LINE)


def show_full(state):
    """每月开头的完整御案:国势 + 势力 + 当前危机。"""
    cr = state.active_crisis()
    print(f"\n{LINE}\n崇祯元年{state.month}月")
    print(f"国势  {state.metric_line()}    (耳目=情报力,越低越看不清天下)")
    for f in state.factions.values():
        print(f"   {f.name}：满意{f.satisfaction}  能量{f.leverage}")
    if cr:
        print(f"\n◆ {cr.title}\n  {cr.brief}")
    print(LINE)


def _dingwei_verdict(state) -> str:
    """据终局国势写一段有层次的史评。"""
    m = state.metrics
    dl = state.factions["东林"].leverage
    yan = state.factions["阉党"].satisfaction
    lines = []
    if yan > 35:
        lines.append("魏阉终未除尽、余焰犹存——这第一道考题,你避而未答,后患埋于今日。")
    elif m["皇威"] < 30:
        lines.append("魏虽除,君威却未立、朝野观望;雷霆不济,反伤天子之断。")
    else:
        lines.append("一举而权阉倒、君威立,这登基第一刀,你砍得干净利落。")
    if m["耳目"] < 40:
        lines.append("然厂卫尽废、耳目失聪,自此地方奏报真伪难辨——信息的迷雾,已悄然笼罩这位最勤政的君王。")
    elif m["耳目"] < 55:
        lines.append("厂卫虽存、元气已伤,京畿耳目不复旧日之灵便。")
    else:
        lines.append("难得的是,你留住了那双替朕看天下的眼睛。")
    if dl >= 55:
        lines.append("可东林已借势独大,科道台谏渐成一党之私——除一阉、养一党,党争之患,才刚刚开始。")
    return "\n".join("  " + s for s in lines)


def _liaodong_verdict(state) -> str:
    m = state.metrics
    army = state.factions["军队"]
    lines = []
    if army.satisfaction >= 50 and m["边事"] >= 45:
        lines.append("辽饷有着落关宁军心稍安宁锦防线暂得保全这一关你险险撑住了")
    elif army.satisfaction < 30 or m["边事"] < 25:
        lines.append("饷银终成空话关宁士卒离心辽东危如累卵兵变与通敌只在旦夕")
    else:
        lines.append("辽东暂未崩然欠饷未清军心半疑边事仍悬于一线")
    if m["民心"] < 35:
        lines.append("然加派之下内地民怨已沸拆东墙补西墙流寇之患正在腹地酝酿")
    if m["国库"] <= 5:
        lines.append("太仓彻底见底辽事稍缓九边其余各镇又将告急")
    if army.leverage >= 75:
        lines.append("且关宁将门借饷自重尾大不掉他日听调不听宣之忧已现端倪")
    return "\n".join("  " + s for s in lines)


def _verdict(state) -> str:
    if state.slice_id == "liaodong":
        return _liaodong_verdict(state)
    return _dingwei_verdict(state)
