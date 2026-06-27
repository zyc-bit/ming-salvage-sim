"""《明末》v2 终端原型。从项目根跑:
   set -a; source .env; set +a
   python -m v2.play
"""
import os

from .content import new_game
from .events import next_from_pool
from .engine import apply_effects
from . import llm
from .present import LINE, banner, show_full, _verdict


def show_brief(state):
    """月内操作后的简短刷新:只一行国势,不重打危机长描述。"""
    print(f"\n国势  {state.metric_line()}")


def _print_menu(state):
    names = [name for name, ch in state.characters.items() if ch.active]
    summon_choices = {str(i): name for i, name in enumerate(names, 1)}
    decree_choice = str(len(names) + 1)
    advance_choice = str(len(names) + 2)
    items = [f"[{i}]召见{name}" for i, name in summon_choices.items()]
    items += [f"[{decree_choice}]下旨处置", f"[{advance_choice}]退朝·推演本月"]
    print("\n" + "  ".join(items))
    return summon_choices, decree_choice, advance_choice


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("缺 OPENAI_API_KEY。先在项目根 `set -a; source .env; set +a` 再跑。")
        return
    state = new_game(os.environ.get("MING_SLICE", "dingwei"))
    summon_log = []          # 本月召对摘要(喂裁判)
    history = {}             # name -> [(role, text)] 跨月保留,大臣记得你说过的话
    month_decree = None
    banner(state)
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
        summon_choices, decree_choice, advance_choice = _print_menu(state)
        choice = input("朕意> ").strip()
        if choice in summon_choices:
            name = summon_choices[choice]
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
        elif choice == decree_choice:
            d = input("拟旨> ").strip()
            if d:
                month_decree = d
                print("(旨意已拟,退朝时颁行天下)")
        elif choice == advance_choice:
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
                nxt = next_from_pool(state)
                if nxt:
                    state.crises.append(nxt)
            month_decree = None
            summon_log = []
            state.month += 1
        else:
            print(f"(请输入 1-{advance_choice})")

    section = "辽东索饷" if state.slice_id == "liaodong" else "定魏"
    print(f"\n{LINE}\n【史册 · {section}一节】")
    if state.slice_id == "liaodong":
        print(f"崇祯于{state.year}年{state.month}月处置辽东索饷。其后国势:{state.metric_line()}\n")
    else:
        print(f"崇祯于元年{state.month}月定魏案。其后国势:{state.metric_line()}\n")
    print(_verdict(state))
    if state.slice_id == "liaodong":
        print("\n(第二垂直切片到此。)")
    else:
        print("\n(第一垂直切片到此。下一刀:辽东索饷。)")
    print(LINE)


if __name__ == "__main__":
    main()
