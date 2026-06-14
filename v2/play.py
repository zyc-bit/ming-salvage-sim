"""《崇祯元年·定魏》终端原型。从项目根跑:
   set -a; source .env; set +a
   python3 v2/play.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content import new_game            # noqa: E402
from engine import apply_effects        # noqa: E402
import llm                              # noqa: E402

LINE = "─" * 58


def banner():
    print(LINE)
    print("《明末·崇祯元年 —— 定魏》   第一垂直切片")
    print("天启七年十一月,信王朱由检入承大统。魏忠贤犹掌司礼监、东厂。")
    print("你是崇祯。登基第一道大题:这权倾朝野的九千岁,你怎么办?")
    print(LINE)


def show_full(state):
    """每月开头的完整御案:国势 + 势力 + 当前危机。"""
    cr = state.active_crisis()
    print(f"\n{LINE}\n崇祯元年{state.month}月    精力 {state.energy}")
    print(f"国势  {state.metric_line()}    (耳目=情报力,越低越看不清天下)")
    for f in state.factions.values():
        print(f"   {f.name}：满意{f.satisfaction}  能量{f.leverage}")
    if cr:
        print(f"\n◆ {cr.title}\n  {cr.brief}")
    print(LINE)


def show_brief(state):
    """月内操作后的简短刷新:只一行国势 + 精力,不重打危机长描述。"""
    print(f"\n国势  {state.metric_line()}    精力 {state.energy}")


def _verdict(state) -> str:
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


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("缺 OPENAI_API_KEY。先在项目根 `set -a; source .env; set +a` 再跑。")
        return
    state = new_game()
    summon_log = []          # 本月召对摘要(喂裁判)
    history = {}             # name -> [(role, text)] 跨月保留,大臣记得你说过的话
    month_decree = None
    banner()
    shown_month = None
    while True:
        cr = state.active_crisis()
        if cr is None:
            break
        if state.month != shown_month:      # 新月:完整御案
            show_full(state)
            shown_month = state.month
        else:                                # 月内:只刷新一行国势,不重打危机长描述
            show_brief(state)
        print("\n[1]召见王承恩  [2]召见韩爌  [3]召见魏忠贤  [4]下旨处置  [5]退朝·推演本月")
        choice = input("朕意> ").strip()
        if choice in ("1", "2", "3"):
            name = {"1": "王承恩", "2": "韩爌", "3": "魏忠贤"}[choice]
            if state.energy <= 0:
                print("(精力已尽,本月无力再召,且退朝吧)")
                continue
            q = input(f"朕问{name}> ").strip()
            if not q:
                continue
            hist = history.setdefault(name, [])
            print(f"\n  …{name}趋前奏对…")
            try:
                reply = llm.summon(state, name, hist, q)
            except Exception as exc:
                print(f"(召对失败:{exc})")
                continue
            print(f"\n{name}：{reply}\n")
            hist += [("帝", q), (name, reply)]
            summon_log += [(f"帝问{name}", q), (name, reply)]
            state.energy -= 1
        elif choice == "4":
            d = input("拟旨> ").strip()
            if d:
                month_decree = d
                print("(旨意已拟,退朝时颁行天下)")
        elif choice == "5":
            if not month_decree:
                if input("尚未下旨,空过本月?(y/N)> ").strip().lower() != "y":
                    continue
            print("\n  …邸报推演中…\n")
            try:
                res = llm.adjudicate(state, month_decree or "(本月未下处置之旨,留中观望)", summon_log)
            except Exception as exc:
                print(f"(推演失败:{exc})")
                continue
            print(LINE)
            print(res.get("narrative", ""))
            print(LINE)
            notes = apply_effects(state, res.get("effects", []))
            if notes:
                print("〔档房〕 " + "；  ".join(notes))
            state.chronicle.append(res.get("narrative", ""))
            if res.get("resolved"):
                cr.resolved = True
            month_decree = None
            summon_log = []
            state.month += 1
            state.energy = 3
        else:
            print("(请输入 1-5)")

    print(f"\n{LINE}\n【史册 · 定魏一节】")
    print(f"崇祯于元年{state.month}月定魏案。其后国势:{state.metric_line()}\n")
    print(_verdict(state))
    print("\n(第一垂直切片到此。下一刀:辽东索饷。)")
    print(LINE)


if __name__ == "__main__":
    main()
