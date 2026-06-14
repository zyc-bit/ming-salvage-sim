"""非交互自动跑通《定魏》一局,打详细后端日志,确认 LLM 链路走通。
   set -a; source .env; set +a
   .venv/bin/python v2/smoke_play.py
"""
import sys
import os
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content import new_game            # noqa: E402
from engine import apply_effects        # noqa: E402
import llm                              # noqa: E402


def log(msg=""):
    print(msg, flush=True)


def main():
    log("============ 后端配置 ============")
    log(f"BASE_URL  = {os.environ.get('OPENAI_BASE_URL')}")
    log(f"MODEL     = {os.environ.get('OPENAI_MODEL')}")
    log(f"TRUST_ENV = {os.environ.get('OPENAI_TRUST_ENV')}  (false=绕过系统代理)")
    log(f"API_KEY   = {'已配置 ****' + (os.environ.get('OPENAI_API_KEY') or '')[-4:] if os.environ.get('OPENAI_API_KEY') else '缺失'}")
    log(f"HTTPS_PROXY(系统) = {os.environ.get('HTTPS_PROXY') or '无'}")

    # —— 连通自检:先用最小请求确认 连接/认证/模型 都通 ——
    log("\n============ 连通自检 ============")
    t = time.time()
    try:
        r = llm._c().chat.completions.create(
            model=llm._model(),
            messages=[{"role": "user", "content": "只回一个字:通"}],
            max_tokens=10,
        )
        log(f"[OK {time.time()-t:.1f}s] 模型应答: {r.choices[0].message.content!r}")
    except Exception as e:
        log(f"[失败 {time.time()-t:.1f}s] {type(e).__name__}: {e}")
        log("\n--- 诊断 ---")
        log("model not found → 换 OPENAI_MODEL(如 deepseek-chat);")
        log("超时/连接错 → 多半是代理,确认 OPENAI_TRUST_ENV=false 生效;")
        log("401/认证 → 检查 OPENAI_API_KEY。")
        traceback.print_exc()
        return

    # —— 跑一局《定魏》——
    state = new_game()
    log("\n============ 开局《崇祯元年·定魏》============")
    log(f"国势  {state.metric_line()}")
    log(f"危机  {state.active_crisis().title}")

    summon_log = []
    plays = [
        ("王承恩", "魏忠贤这阉竖,如今宫里厂卫还听不听他的?朕若动他,内廷可稳?"),
        ("韩爌", "卿等执意诛魏。然厂卫一去,朕耳目尽失,地方谁替朕盯着?可有两全之策?"),
    ]
    for name, q in plays:
        log(f"\n------ 召见 {name} ------")
        log(f"朕问:{q}")
        t = time.time()
        try:
            reply = llm.summon(state, name, [], q)
        except Exception as e:
            log(f"[summon 失败 {time.time()-t:.1f}s] {type(e).__name__}: {e}")
            traceback.print_exc()
            return
        log(f"[LLM {time.time()-t:.1f}s] {name}:{reply}")
        summon_log += [(f"帝问{name}", q), (name, reply)]

    decree = ("魏忠贤罪恶滔天,着即革去司礼监掌印、东厂提督一切差使,发凤阳安置;"
              "其党羽崔呈秀等下法司勘问。然东厂、锦衣卫缇骑暂留,择忠谨者统之,不得借机株连无辜。")
    log(f"\n============ 下旨 ============\n{decree}")

    log("\n------ 退朝·天下推演 ------")
    t = time.time()
    try:
        res = llm.adjudicate(state, decree, summon_log)
    except Exception as e:
        log(f"[adjudicate 失败 {time.time()-t:.1f}s] {type(e).__name__}: {e}")
        traceback.print_exc()
        return
    log(f"[LLM {time.time()-t:.1f}s] 裁判完成")
    log(f"\n【邸报】\n{res.get('narrative')}")
    log(f"\nresolved = {res.get('resolved')}")
    log(f"effects  = {res.get('effects')}")

    before = state.metric_line()
    notes = apply_effects(state, res.get("effects", []))
    log("\n============ 落账 ============")
    log("档房:" + " / ".join(notes) if notes else "档房:(裁判未给 effects)")
    log(f"国势  {before}")
    log(f"  →   {state.metric_line()}")
    if res.get("resolved"):
        state.active_crisis().resolved = True
        log("\n魏案已了。耳目=" + str(state.metrics["耳目"]) + ("(<40,信息迷雾结局)" if state.metrics["耳目"] < 40 else ""))

    log("\n============ 全流程走通 ✓ ============")


if __name__ == "__main__":
    main()
