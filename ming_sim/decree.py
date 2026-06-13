"""诏书生成与回合结算：拟诏、推演落库。L7。

纯逻辑（无 input()）：模块内的 print 均为诊断输出，非交互。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable, Dict, List, Optional, Tuple

from agno.db.sqlite import SqliteDb

from ming_sim.agents import (
    create_chat_memory_agent,
    create_decree_writer_agent,
    create_immediate_simulator_agent,
    create_json_sanitizer_agent,
    create_score_extractor_module_agent,
    create_season_simulator_agent,
)
from ming_sim.context import victory_status
from ming_sim.db import GameDB
from ming_sim.exceptions import LLMContractError, LLMUnavailable
from ming_sim.flows import apply_fixed_daily_flows
from ming_sim.issues import apply_issue_inertia_and_ongoing, apply_score_extraction, clear_gated_legacies
from ming_sim.llm_model import extract_agent_text, llm_unavailable_from_error
from ming_sim.models import GameState, LLMConfig, date_label
from ming_sim.memories import extract_all_chat_memories
from ming_sim.simulation import (
    EXTRACTION_MODULES,
    build_simulator_payload,
    build_extractor_shared_context,
    extract_scores_by_modules_with_agno,
    simulate_season_with_payload,
)
from ming_sim.token_stats import tlog


def _collect_secret_orders_for_sim(db: GameDB) -> List[Dict[str, object]]:
    secret_orders_for_sim: List[Dict[str, object]] = []
    try:
        active_orders = (
            db.list_secret_orders(status="active")
            + db.list_secret_orders(status="pending_review")
        )[:20]
        for o in active_orders:
            secret_orders_for_sim.append({
                "id": int(o["id"]),
                "minister_name": o["minister_name"],
                "title": o["title"],
                "content": str(o["content"] or "")[:120],
                "status": o["status"],
                "turn_issued": o.get("turn_issued") or 0,
                "due_turn": o.get("due_turn") or 0,
                "progress": o.get("result") or "",
                "sim_note": o.get("sim_note") or "",
            })
    except Exception as exc:
        tlog(f"[secret_order] 注入失败，跳过：{exc}")
    return secret_orders_for_sim


def _compact_applied_summary(applied: Dict[str, object]) -> Dict[str, object]:
    keys = (
        "metric_delta", "economy_moves", "faction_delta", "class_delta",
        "region_changes", "army_changes", "created_armies", "power_changes",
        "issue_summary", "fiscal_changes", "appointments",
        "character_status_changes", "character_power_changes", "office_changes",
        "secret_order_updates", "secret_order_closes",
    )
    return {key: applied.get(key) for key in keys if applied.get(key)}


def write_decree_with_agno(
    llm_config: LLMConfig,
    agno_db: SqliteDb,
    state: GameState,
    directives: List[sqlite3.Row],
    db: Optional[GameDB] = None,
) -> str:
    if not directives:
        raise LLMContractError("无草案不能拟诏。")
    # 已办结密令的 result 作为实质证据清单注入——皇帝下旨拿人/定罪时可引为依据。
    closed_evidence: List[Dict[str, object]] = []
    if db is not None:
        try:
            for o in db.list_secret_orders(status="done"):
                if o.get("result"):
                    closed_evidence.append({
                        "id": int(o["id"]), "title": o["title"],
                        "assignee": o["minister_name"], "evidence": o["result"],
                    })
        except Exception:
            closed_evidence = []
    payload = {
        "turn": {"year": state.year, "period": state.period, "turn": state.turn},
        "directives": [
            {
                "text": row["text"],
            }
            for row in directives
        ],
        "closed_secret_orders": closed_evidence,
        "instruction": "合并成一份正式诏书正文。closed_secret_orders 是已办结密令查得的实证，"
                       "若草案据某密令查办之事拿人定罪，可在诏书里引该实证为据，使罪名落到实处。",
    }
    try:
        agent = create_decree_writer_agent(llm_config, agno_db)
        text = extract_agent_text(agent.run(json.dumps(payload, ensure_ascii=False, sort_keys=True)))
    except LLMUnavailable:
        raise
    except Exception as error:
        raise llm_unavailable_from_error(error, "拟诏") from error
    if not text.strip():
        raise LLMContractError("拟诏输出为空。")
    return text.strip()


def resolve_immediate_event(
    state: GameState,
    db: GameDB,
    agno_db: SqliteDb,
    llm_config: LLMConfig,
    source_kind: str,
    source_id: str,
    minister_name: str = "",
    title: str = "",
    trigger_text: str = "",
    response_text: str = "",
    tool_result: str = "",
    on_event: Optional[Callable[[str, str], None]] = None,
    content=None,
    registry=None,
) -> Dict[str, object]:
    """日制即时回奏：不跑固定月度收支，不推进日期，只落本次事件的受控字段。"""

    def _emit(kind: str, data: str) -> None:
        if on_event:
            on_event(kind, data)

    if db.court_event_exists(source_kind, source_id):
        return {"status": "duplicate", "court_event": db.get_court_event_by_source(source_kind, source_id)}

    event_id = db.create_court_event(
        state,
        source_kind=source_kind,
        source_id=source_id,
        minister_name=minister_name,
        title=title or "即时回奏",
        trigger_text=trigger_text,
        response_text=response_text,
        tool_result=tool_result,
        status="running",
    )
    if not event_id:
        return {"status": "duplicate", "court_event": None}

    extra_context: Dict[str, object] = {
        "mode": "immediate",
        "immediate_trigger": {
            "source_kind": source_kind,
            "source_id": source_id,
            "minister_name": minister_name,
            "title": title,
            "trigger_text": trigger_text,
            "response_text": response_text,
            "tool_result": tool_result,
            "date": {"year": state.year, "period": state.period, "day": state.day, "turn": state.turn},
        },
        "mode_instruction": (
            "即时回奏模式：只结算 immediate_trigger 这一次召对/旨意/密令造成的即时后果；"
            "禁止固定财政、军饷、建筑维护/产出、issue 自然惯性、月末邸报和日期推进。"
        ),
    }
    try:
        _emit("immediate_stage", "即时回奏推演")
        previous_narrative = db.previous_turn_summary(state) or ""
        secret_orders_for_sim = _collect_secret_orders_for_sim(db)
        simulator_payload = build_simulator_payload(
            state,
            db,
            trigger_text,
            [],
            previous_narrative,
            fixed_flows=[],
            relevant_memories=[],
            secret_orders=secret_orders_for_sim,
            extra_context=extra_context,
        )
        simulator = create_immediate_simulator_agent(
            llm_config, agno_db, simulator_payload=simulator_payload
        )
        narrative, simulator_payload = simulate_season_with_payload(
            simulator,
            state,
            db,
            trigger_text,
            [],
            previous_narrative,
            fixed_flows=[],
            relevant_memories=[],
            secret_orders=secret_orders_for_sim,
            simulator_payload=simulator_payload,
            extra_context=extra_context,
            on_thinking=lambda c: _emit("immediate_thinking", c),
            on_text=lambda c: _emit("immediate_text", c),
        )

        _emit("immediate_stage", "即时数值落账")
        extractor_shared_context = build_extractor_shared_context(
            db,
            state,
            narrative,
            trigger_text,
            relevant_memories=[],
            secret_orders=secret_orders_for_sim,
            extra_context=extra_context,
        )
        extractors = {
            module: create_score_extractor_module_agent(
                llm_config,
                agno_db,
                module,
                simulator_payload=simulator_payload,
                supplemental_context=extractor_shared_context,
            )
            for module in EXTRACTION_MODULES
        }
        sanitizer = create_json_sanitizer_agent(llm_config, agno_db)
        extracted, extractor_output, extractor_input = extract_scores_by_modules_with_agno(
            extractors,
            db,
            state,
            narrative,
            decree_text=trigger_text,
            sanitizer=sanitizer,
            relevant_memories=[],
            secret_orders=secret_orders_for_sim,
            extra_context=extra_context,
        )
        applied = apply_score_extraction(db, state, extracted, content=content, registry=registry)
        applied_summary = _compact_applied_summary(applied)
        db.record_log(state, f"即时回奏：{title or source_kind}\n{narrative[:1000]}")
        db.update_court_event_result(
            event_id,
            status="applied",
            narrative=narrative,
            extractor_output=extractor_output,
            applied_summary=json.dumps(applied_summary, ensure_ascii=False, sort_keys=False),
        )
        clear_gated_legacies(db, state)
        db.save_state(state)
        event = db.get_court_event(event_id)
        _emit("immediate_done", json.dumps(event or {}, ensure_ascii=False))
        return {
            "status": "applied",
            "court_event": event,
            "narrative": narrative,
            "extractor_input": extractor_input,
            "extractor_output": extractor_output,
            "applied_summary": applied_summary,
        }
    except Exception as exc:
        db.update_court_event_result(event_id, status="error", error=str(exc))
        _emit("immediate_error", str(exc))
        return {"status": "error", "court_event": db.get_court_event(event_id), "error": str(exc)}


def _month_daily_reports(db: GameDB, state: GameState, limit: int = 30) -> List[Dict[str, object]]:
    rows = db.conn.execute(
        """
        SELECT tr.turn, tr.report, COALESCE(tc.day, 0) AS day
        FROM turn_reports tr
        LEFT JOIN turn_calendar tc ON tc.turn = tr.turn
        WHERE tr.year = ? AND tr.period = ?
        ORDER BY tr.turn
        """,
        (int(state.year), int(state.period)),
    ).fetchall()
    reports: List[Dict[str, object]] = []
    for row in rows[-max(1, int(limit or 30)):]:
        report = str(row["report"] or "").strip()
        if not report:
            continue
        reports.append({
            "turn": int(row["turn"]),
            "day": int(row["day"] or 0),
            "report_tail": report[-1200:],
        })
    return reports


def resolve_day_end(
    state: GameState,
    db: GameDB,
    agno_db: SqliteDb,
    llm_config: LLMConfig,
    deaths_this_turn: Optional[List[Dict[str, str]]] = None,
    debuts_this_turn: Optional[List[Dict[str, str]]] = None,
    on_event: Optional[Callable[[str, str], None]] = None,
    content=None,
    registry=None,
) -> Tuple[str, dict]:
    """每日退朝结算：固定日额 + 当日自然推进 + 到期密令 + 当日奏报。

    本函数只结算当前日期，不推进 state.turn/date；日期推进由 GameSession.end_day 统一处理。
    """

    def _emit(kind: str, data: str) -> None:
        if on_event:
            on_event(kind, data)

    before_turn = state.turn
    today_label = date_label(state.year, state.period, state.day)
    decree_text = (
        f"日终退朝：{today_label}当日召对、诏令、密令与地方通信已经按送达时点入盘；"
        "本日只结算当日固定收支、局势自然推进、到期密令核议与候选情势。"
    )
    directives_brief: List[Dict[str, object]] = []
    day_events = db.list_court_events(
        year=state.year, period=state.period, day=state.day, limit=80
    )

    tlog("日终 1/4 固定财政日 tick")
    _emit("stage", "日终固定收支入账")
    fixed_flows = apply_fixed_daily_flows(db, state)

    try:
        due_orders = db.auto_submit_due_secret_orders(state)
        if due_orders:
            tlog(f"[secret_order] 到期送核议 {due_orders}")
    except Exception as exc:
        tlog(f"[secret_order] 到期送核议失败，跳过：{exc}")
    secret_orders_for_sim = _collect_secret_orders_for_sim(db)

    extra_context: Dict[str, object] = {
        "mode": "day_end",
        "settlement_scope": "single_day",
        "court_events": [
            {
                "id": e.get("id"),
                "day": e.get("day"),
                "source_kind": e.get("source_kind"),
                "title": e.get("title"),
                "minister_name": e.get("minister_name"),
                "status": e.get("status"),
                "applied_summary": e.get("applied_summary"),
                "narrative_tail": str(e.get("narrative") or "")[-240:],
            }
            for e in day_events
        ],
        "mode_instruction": (
            "日终模式：只推演当前这一日。court_events 里的即时事件已经逐次落数，"
            "日终奏报只能概括其过程，不得重复抽取这些行动的硬效果；"
            "固定财政、军饷、建筑维护/产出、issue inertia/ongoing 均已按 30 日切片，"
            "只能抽取确属当日发生的自然变化、到期密令核议和候选情势。"
        ),
    }

    tlog("日终 2/4 推演 agent（日终奏报）")
    _emit("stage", "推演日终奏报")
    previous_narrative = db.previous_turn_summary(state) or ""
    simulator_payload = build_simulator_payload(
        state,
        db,
        decree_text,
        directives_brief,
        previous_narrative,
        fixed_flows=fixed_flows,
        deaths_this_turn=deaths_this_turn,
        debuts_this_turn=debuts_this_turn,
        relevant_memories=[],
        secret_orders=secret_orders_for_sim,
        extra_context=extra_context,
    )
    simulator = create_season_simulator_agent(
        llm_config, agno_db, state=state, db=db, simulator_payload=simulator_payload
    )
    try:
        narrative, simulator_payload = simulate_season_with_payload(
            simulator,
            state,
            db,
            decree_text,
            directives_brief,
            previous_narrative,
            fixed_flows=fixed_flows,
            deaths_this_turn=deaths_this_turn,
            debuts_this_turn=debuts_this_turn,
            relevant_memories=[],
            secret_orders=secret_orders_for_sim,
            simulator_payload=simulator_payload,
            extra_context=extra_context,
            on_thinking=lambda c: _emit("thinking", c),
            on_text=lambda c: _emit("text", c),
        )
    except Exception as exc:
        print(f"[WARN] 日终推演 agent 失败：{exc}；保留固定日额与自然推进。")
        narrative = f"{today_label}日终推演 agent 失败，固定日额已落账，事项按日切片自然推进。错误：{exc}"
        db.record_log(state, narrative[:1200])
        db.save_turn_report(state, narrative)
        db.save_turn_extraction(
            state, decree_text=decree_text, narrative=narrative,
            extractor_output=f"[日终推演 agent 失败] {exc}；本日跳过 extractor。",
        )
        apply_issue_inertia_and_ongoing(db, state, touched_ids=set(), period_days=30)
        clear_gated_legacies(db, state)
        db.save_state(state)
        assert state.turn == before_turn
        return narrative, {}

    tlog("日终 3/4 结算 agent（抽 JSON）")
    _emit("stage", "日终数值结算")
    extractor_shared_context = build_extractor_shared_context(
        db,
        state,
        narrative,
        decree_text,
        relevant_memories=[],
        secret_orders=secret_orders_for_sim,
        extra_context=extra_context,
    )
    extractors = {
        module: create_score_extractor_module_agent(
            llm_config,
            agno_db,
            module,
            simulator_payload=simulator_payload,
            supplemental_context=extractor_shared_context,
        )
        for module in EXTRACTION_MODULES
    }
    sanitizer = create_json_sanitizer_agent(llm_config, agno_db)
    try:
        extracted, extractor_output, extractor_input = extract_scores_by_modules_with_agno(
            extractors,
            db,
            state,
            narrative,
            decree_text=decree_text,
            sanitizer=sanitizer,
            relevant_memories=[],
            secret_orders=secret_orders_for_sim,
            extra_context=extra_context,
        )
    except Exception as exc:
        print(f"[WARN] 日终结算抽取失败：{exc}；本日数值只保留固定日额。")
        extracted = {}
        extractor_output = f"[日终抽取失败] {exc}"
        extractor_input = ""

    tlog("日终 4/4 落库 + inertia/ongoing")
    _emit("stage", "日终落库与事项推进")
    applied = apply_score_extraction(db, state, extracted, content=content, registry=registry)
    db.record_log(state, narrative[:1200])
    db.save_turn_report(state, narrative)
    db.save_turn_extraction(
        state,
        decree_text=decree_text,
        narrative=narrative,
        extractor_input=extractor_input,
        extractor_output=extractor_output,
    )
    _emit("stage", "提取对话记忆")
    try:
        chat_mem_agent = create_chat_memory_agent(llm_config, agno_db)
        extract_all_chat_memories(chat_mem_agent, db, state)
    except Exception as exc:
        tlog(f"[chat-memory] 跳过：{exc}")

    touched_ids = set()
    for adv in applied.get("issue_summary", {}).get("advances", []) or []:
        touched_ids.add(int(adv.get("issue_id") or 0))
    apply_issue_inertia_and_ongoing(db, state, touched_ids=touched_ids, period_days=30)
    clear_gated_legacies(db, state)

    outcome = applied.get("victory_status") or victory_status(db, state)
    if isinstance(outcome, dict) and outcome.get("status") != "ongoing":
        db.record_log(state, f"结局判定：{outcome.get('summary', '')}")

    db.save_state(state)
    assert state.turn == before_turn
    return narrative, applied


def resolve_month_summary(
    state: GameState,
    db: GameDB,
    agno_db: SqliteDb,
    llm_config: LLMConfig,
    daily_report: str = "",
    on_event: Optional[Callable[[str, str], None]] = None,
) -> str:
    """月末只生成总结报告，不落数、不推进、不调用 extractor。"""

    def _emit(kind: str, data: str) -> None:
        if on_event:
            on_event(kind, data)

    month_label = f"{state.year}年{state.period}月"
    decree_text = (
        f"月末总结：{month_label}已按日结算、按日推进；"
        "本段只汇总本月走势，不新增硬效果，不改变盘面数值。"
    )
    daily_reports = _month_daily_reports(db, state)
    extra_context: Dict[str, object] = {
        "mode": "month_summary",
        "settlement_scope": "summary_only",
        "daily_reports": daily_reports,
        "mode_instruction": (
            "月末总结模式：只能综合 daily_reports 和当前盘面写报告。"
            "禁止新增或暗示新增任何硬效果；禁止调用 extractor；禁止写固定收支落账、"
            "issue 新推进、密令新结案或日期推进。"
        ),
    }
    previous_narrative = db.previous_turn_summary(state) or ""
    simulator_payload = build_simulator_payload(
        state,
        db,
        decree_text,
        [],
        previous_narrative,
        fixed_flows=[],
        deaths_this_turn=[],
        debuts_this_turn=[],
        relevant_memories=[],
        secret_orders=_collect_secret_orders_for_sim(db),
        extra_context=extra_context,
    )
    simulator = create_season_simulator_agent(
        llm_config, agno_db, state=state, db=db, simulator_payload=simulator_payload
    )
    tlog("月末总结 1/1 推演 agent（只写总结）")
    _emit("stage", "生成月末总结")
    try:
        narrative, _ = simulate_season_with_payload(
            simulator,
            state,
            db,
            decree_text,
            [],
            previous_narrative,
            fixed_flows=[],
            deaths_this_turn=[],
            debuts_this_turn=[],
            relevant_memories=[],
            secret_orders=_collect_secret_orders_for_sim(db),
            simulator_payload=simulator_payload,
            extra_context=extra_context,
            on_thinking=lambda c: _emit("thinking", c),
            on_text=lambda c: _emit("text", c),
        )
    except Exception as exc:
        print(f"[WARN] 月末总结 agent 失败：{exc}；使用简要总结。")
        narrative = f"{month_label}月末总结生成失败；本月已按日完成 {len(daily_reports)} 份日终奏报，盘面数值不因总结再变化。错误：{exc}"

    summary = narrative.strip() or f"{month_label}月末总结：本月已按日完成 {len(daily_reports)} 份日终奏报，盘面数值不因总结再变化。"
    combined = (daily_report.strip() + "\n\n【月末总结】\n" + summary) if daily_report.strip() else summary
    db.record_log(state, summary[:1200])
    db.save_turn_report(state, combined)
    db.save_state(state)
    return combined
