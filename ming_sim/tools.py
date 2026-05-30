"""大臣 Agent 工具集：查询工具 + court tools（拟旨/退下/换人）。L5。"""

from __future__ import annotations

import difflib
import json
import re

from ming_sim.constants import TURN_UNIT
from ming_sim.context import _ctx as _content_ctx, state_context
from ming_sim.models import Character, CourtContext
from ming_sim.skills import available_skill_ids, skill_template

_STATUS_CN = {
    "active": "在朝",
    "dismissed": "已罢黜",
    "imprisoned": "下狱",
    "exiled": "流放",
    "retired": "致仕",
    "dead": "已故",
}


def _normalize_person_name(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def _match_character_by_name(name: str) -> Character | None:
    key = _normalize_person_name(name)
    if not key:
        return None
    characters = [c for c in _content_ctx().characters.values() if c.office_type != "后宫"]
    for c in characters:
        names = [c.name, *(c.aliases or [])]
        if any(_normalize_person_name(n) == key for n in names):
            return c
    for c in characters:
        names = [c.name, *(c.aliases or [])]
        if any(key in _normalize_person_name(n) or _normalize_person_name(n) in key for n in names):
            return c
    choices = {c.name: c for c in characters}
    match = difflib.get_close_matches(key, list(choices.keys()), n=1, cutoff=0.6)
    return choices[match[0]] if match else None


def _duty_location(office: str, office_type: str, status: str) -> str:
    if status == "dead":
        return "已故，不在任事。"
    if status == "imprisoned":
        return "系狱待勘，具体羁押处以处置缘由为准。"
    if status in {"dismissed", "exiled", "retired", "offstage"}:
        return "不在朝任事。"
    text = office or office_type
    if not text:
        return "在朝但现职未明。"
    region_markers = [
        "陕西", "辽东", "宁远", "关宁", "山西", "河南", "山东", "湖广", "四川", "福建",
        "广东", "广西", "浙江", "江西", "南直隶", "北直隶", "南京", "登莱", "宣大", "延绥",
    ]
    for marker in region_markers:
        if marker in text:
            return f"按现职在{marker}任事。"
    if office_type in {"内阁", "吏部", "户部", "礼部", "兵部", "工部", "都察院", "翰林院", "司礼监", "锦衣卫", "东厂", "内廷"}:
        return f"按现职在京师{office_type}衙署任事。"
    if office_type == "边镇":
        return "按现职在所辖边镇任事。"
    if office_type == "地方":
        return "按现职在地方任事。"
    return "按现职任事，具体地点需看官衔所辖。"


def _assignment_hint(text: str) -> str:
    if not text:
        return ""
    places = [
        "山海关", "宁远", "辽东", "陕西", "延绥", "宣大", "登莱", "山东", "河南",
        "南直隶", "南京", "江南", "苏州", "松江", "湖广", "四川", "福建", "浙江",
        "广东", "广西", "京师",
    ]
    verbs = ("赴", "往", "至", "驻", "巡", "督押", "赍旨赴", "差往", "前往")
    if not any(v in text for v in verbs):
        return ""
    hits = [p for p in places if p in text]
    if not hits:
        return ""
    return "近来差遣：" + "、".join(hits[:4]) + "。"


def build_minister_tools(character: Character, context: CourtContext):
    skill_ids = set(available_skill_ids(character, context.db))

    def view_state() -> str:
        """查看当前大明核心国势数值（含派系/阶级/势力）。"""
        return (
            state_context(context.state)
            + "。派系：" + context.db.faction_report()
            + "。" + context.db.class_report()
            + "。外部：" + context.db.power_report(exclude_self=True)
        )

    def list_memorials() -> str:
        """查看当前在办的所有事项（issue）。"""
        rows = context.db.list_active_issues()
        if not rows:
            return f"本{TURN_UNIT}无在办事项。"
        lines = []
        for idx, row in enumerate(rows, 1):
            kind_tag = "系统" if row["kind"] == "situation" else "皇帝推动"
            lines.append(
                f"{idx}. #{row['id']}[{kind_tag}]{row['title']}"
                f"（bar {int(row['bar_value'])}/{row['bar_good_meaning']}，{row['stage_text']}）"
            )
        return "\n".join(lines)

    def inspect_memorial(slot: int) -> str:
        """查看某条在办事项的细节。slot 是事项编号（由 list_memorials 给出）。"""
        rows = context.db.list_active_issues()
        try:
            n = int(slot)
        except (ValueError, TypeError):
            return f"slot 必须是整数 1-{len(rows)}。"
        if n < 1 or n > len(rows):
            return f"slot 越界 {n}。本{TURN_UNIT}有 {len(rows)} 条在办事项。"
        row = rows[n - 1]
        return (
            f"#{row['id']} {row['title']}（bar {int(row['bar_value'])}，{row['bar_bad_meaning']}↔{row['bar_good_meaning']}）。"
            f"阶段：{row['stage_text']}。牵涉：{row['faction_hint'] or '—'}。"
            f"结案条件：{row['resolve_condition'] or '（未填）'}。失败条件：{row['fail_condition'] or '（未填）'}。"
        )

    def list_regions() -> str:
        f"""查看两京十三省最危险地区和账面{TURN_UNIT}税。"""
        return context.db.region_report(limit=6)

    def inspect_region(region_name: str) -> str:
        """查看某一地区人口、民心、动乱、天灾、人祸、田亩和税收。"""
        try:
            return context.db.region_detail(region_name)
        except ValueError as e:
            return f"未找到地区 '{region_name}'。可先调 list_regions 看地区 id/名称列表。错误：{e}"

    def list_armies() -> str:
        """查看大明主要军队的驻扎、维护费、补给、士气和欠饷警讯。"""
        return context.db.army_report(limit=6)

    def inspect_army(army_name: str) -> str:
        """查看某支军队驻扎地、兵种、人数、维护费、补给、士气、训练和欠饷。"""
        try:
            return context.db.army_detail(army_name)
        except ValueError as e:
            return f"未找到军队 '{army_name}'。可先调 list_armies 看军队 id/名称列表。错误：{e}"

    def list_powers() -> str:
        """查看后金、蒙古、朝鲜、日本、流寇等势力状态。"""
        return context.db.power_report(exclude_self=True)

    def list_buildings() -> str:
        """查看全国在册建筑（火炮厂、矿厂、常平仓、边堡、织造局等）的等级、完好、维护费与产出。"""
        return context.db.buildings_report()

    def inspect_building(building_name: str) -> str:
        """查看某座建筑的类别、等级、完好、维护费、风险与产出。"""
        try:
            return context.db.building_detail(building_name)
        except ValueError as e:
            return f"未找到建筑 '{building_name}'。可先调 list_buildings 看建筑列表。错误：{e}"

    def list_court() -> str:
        """查在朝（及被罢/下狱/流放/致仕）官员名册：姓名、现职、派系、状态。"""
        lines = []
        for c in _content_ctx().characters.values():
            if c.office_type == "后宫":
                continue
            if getattr(c, "power_id", "ming") != "ming":
                continue
            status, _ = context.db.get_character_status(c.name)
            if status == "offstage":
                continue  # 未登场者不泄露，防剧透
            tag = _STATUS_CN.get(status, status)
            suffix = "" if status == "active" else f"（{tag}）"
            lines.append(f"{c.name}：{c.office}，{c.faction}{suffix}")
        return "在朝官员名册：\n" + "\n".join(lines)

    def list_personnel() -> str:
        """查看当前人事总表：姓名、现职、派系、状态与任事处。"""
        lines = []
        for c in _content_ctx().characters.values():
            if c.office_type == "后宫":
                continue
            if getattr(c, "power_id", "ming") != "ming":
                continue
            status, reason = context.db.get_character_status(c.name)
            if status == "offstage":
                continue
            tag = _STATUS_CN.get(status, status)
            location = _duty_location(c.office, c.office_type, status)
            suffix = f"；{reason}" if reason else ""
            lines.append(f"{c.name}：{c.office or '无现任官职'}，{c.faction}，{tag}，{location}{suffix}")
        return f"当前时点：{context.state.year}年{context.state.period}月。\n人事总表：\n" + "\n".join(lines)

    def inspect_minister(name: str) -> str:
        """查某位官员的现任官职、派系、当前状态、任事处和近来差遣。"""
        target = _match_character_by_name(name)
        if target is None:
            return f"名册中无『{name}』。可先调 list_personnel/list_court 看在朝官员名单。"
        status, reason = context.db.get_character_status(target.name)
        tag = _STATUS_CN.get(status, status)
        location = _duty_location(target.office, target.office_type, status)
        power_row = context.db.conn.execute(
            "SELECT name FROM powers WHERE id=?", (getattr(target, "power_id", "ming") or "ming",)
        ).fetchone()
        power_name = power_row["name"] if power_row else (getattr(target, "power_id", "ming") or "ming")
        office_row = context.db.conn.execute(
            "SELECT office_title, office_type, source, updated_at FROM character_offices WHERE character_name=?",
            (target.name,),
        ).fetchone()
        office_source = ""
        if office_row:
            office_source = f"任职记录：{office_row['office_title']}（{office_row['office_type']}，来源：{office_row['source']}，更新时间：{office_row['updated_at']}）。"
        recent_directives = context.db.conn.execute(
            """
            SELECT turn, year, period, text, source, status, notes
            FROM turn_directives
            WHERE actor = ? OR text LIKE ?
            ORDER BY turn DESC, id DESC
            LIMIT 3
            """,
            (target.name, f"%{target.name}%"),
        ).fetchall()
        out = (
            f"当前时点：{context.state.year}年{context.state.period}月。"
            f"{target.name}：归属{power_name}，现职{target.office}，职位类型{target.office_type}，派系{target.faction}，状态{tag}。"
            f"任事处：{location}"
        )
        if reason:
            out += f"（{reason}）"
        if target.summary:
            out += f"简介：{target.summary}"
        if office_source:
            out += "\n" + office_source
        if recent_directives:
            lines = [
                f"{r['year']}年{r['period']}月：{r['source']}（{r['status']}）{str(r['text'])[:80]}"
                + (f"；{r['notes']}" if r["notes"] else "")
                for r in recent_directives
            ]
            assignment = next((_assignment_hint(str(r["text"] or "")) for r in recent_directives if _assignment_hint(str(r["text"] or ""))), "")
            if assignment:
                out += "\n" + assignment
            out += "\n近来牵涉诏令/草案：\n" + "\n".join(lines)
        return out

    def inspect_personnel_changes(name: str = "") -> str:
        """查某人或全朝最近人事变动（任命、调任、罢黜、下狱、致仕、死亡）。"""
        target = _match_character_by_name(name) if name else None
        where = ""
        params: list[object] = []
        if target is not None:
            where = "WHERE character_name = ?"
            params.append(target.name)
        office_rows = context.db.conn.execute(
            f"""
            SELECT character_name, office_title, office_type, source, updated_at
            FROM character_offices
            {where}
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            params,
        ).fetchall()
        status_rows = []
        if target is not None:
            status_rows = context.db.conn.execute(
                """
                SELECT name, status, status_reason, status_changed_turn
                FROM characters
                WHERE name = ? AND status_reason != ''
                """,
                (target.name,),
            ).fetchall()
        else:
            status_rows = context.db.conn.execute(
                """
                SELECT name, status, status_reason, status_changed_turn
                FROM characters
                WHERE status_reason != ''
                ORDER BY status_changed_turn DESC
                LIMIT 10
                """
            ).fetchall()
        if not office_rows and not status_rows:
            return "暂无可查的人事变动记录。"
        lines = [f"当前时点：{context.state.year}年{context.state.period}月。"]
        if office_rows:
            lines.append("任职记录：")
            for r in office_rows:
                lines.append(f"- {r['character_name']}：{r['office_title']}（{r['office_type']}），来源：{r['source']}，更新时间：{r['updated_at']}")
        if status_rows:
            lines.append("状态变更：")
            for r in status_rows:
                lines.append(f"- {r['name']}：{_STATUS_CN.get(r['status'], r['status'])}，第{r['status_changed_turn']}回合，{r['status_reason']}")
        return "\n".join(lines)

    def estimate_resistance(slot: int) -> str:
        """估算某条在办事项若下旨推动的主要阻力。slot 是事项编号（由 list_memorials 给出）。"""
        rows = context.db.list_active_issues()
        try:
            n = int(slot)
        except (ValueError, TypeError):
            return f"slot 必须是整数 1-{len(rows)}。"
        if n < 1 or n > len(rows):
            return f"slot 越界 {n}。本{TURN_UNIT}有 {len(rows)} 条在办事项。"
        row = rows[n - 1]
        db = context.db
        faction_lev_avg = db.conn.execute("SELECT AVG(leverage) AS v FROM factions").fetchone()["v"] or 50
        resistance = int(row["severity"]) // 4 + int(faction_lev_avg) // 6
        tags = row["faction_hint"] or ""
        if any(t in tags for t in ("边", "军")):
            # arrears 是累计欠饷万两，按 maintenance 归一成"平均欠饷月数"再加权
            row_av = db.conn.execute(
                "SELECT AVG(arrears * 1.0 / NULLIF(maintenance_per_turn, 0)) AS months "
                "FROM armies WHERE maintenance_per_turn > 0"
            ).fetchone()
            months = float(row_av["months"] or 0)
            resistance += int(months * 2)
        if any(t in tags for t in ("百姓", "地方", "士绅")):
            unrest_avg = db.conn.execute("SELECT AVG(unrest) AS v FROM regions").fetchone()["v"] or 0
            resistance += int(unrest_avg) // 12
        if any(t in tags for t in ("户部", "财")):
            resistance += max(0, 500 - context.state.metrics["国库"]) // 50
        if resistance >= 28:
            level = "高"
        elif resistance >= 18:
            level = "中"
        else:
            level = "低"
        return f"{row['title']}阻力{level}，主要牵涉：{tags or '—'}。估算阻力值：{resistance}。"

    def read_past_report(year: int = 0, month: int = 0) -> str:
        """读某年某月邸报全文，了解此前朝局走向、地方动静、灾兵祸福，避免接旨时凭空臆议。
        参数：
        - year：年份（如 1628）。缺省（0）默认查上月。
        - month：月份（1-12）。缺省（0）配 year 缺省即上月；若给了 year 而 month=0，按 1 月算。
        所求年月未到、无邸报存档或在登基之前 → 提示『未见正式记录』。"""
        # 缺省：查上月（state.year/period - 1）
        if not year:
            target_year = context.state.year
            target_month = context.state.period - 1
            if target_month < 1:
                target_month = 12
                target_year -= 1
        else:
            target_year = int(year)
            target_month = int(month) if month else 1
            target_month = max(1, min(12, target_month))
        row = context.db.conn.execute(
            "SELECT turn, report FROM turn_reports WHERE year=? AND period=?",
            (target_year, target_month),
        ).fetchone()
        if not row or not row["report"]:
            return f"{target_year}年{target_month}月未见正式邸报记录。"
        return f"【{target_year}年{target_month}月邸报】\n{row['report']}"

    def recall_memory_detail(memory_id: int) -> str:
        """查某条旧事记忆的原始来源摘录。只有需要引用旧事细节、被皇帝追问经过、或准备据旧事拟旨时调用。"""
        try:
            mid = int(memory_id)
        except (TypeError, ValueError):
            return "memory_id 必须是旧事记忆编号。"
        return context.db.event_memory_detail(mid)

    def recall_memories_by_time(
        year: int,
        period: int,
        keywords: str = "",
    ) -> str:
        """按年月回忆历史旧事，可附加关键词辅助检索。
        皇帝问及某年某月旧事、或需追溯特定时期事件时调用。
        year: 年份（如1628）；period: 月份1-12；keywords: 逗号分隔的人名/地名/势力名（可为空）。
        时间查询绕过记忆衰减，能追溯已过期的历史记忆。
        """
        ref_turn = (int(year) - 1627) * 12 + (int(period) - 10) + 1
        kw_list = [k.strip() for k in str(keywords).split(",") if k.strip()] if keywords else []

        # 时间查：精确该月，ignore_expiry（历史档案，无视衰减）
        time_rows = context.db.conn.execute(
            """
            SELECT id, year, period, subject_id, title, cause, outcome, importance
            FROM event_memories
            WHERE turn = ?
            ORDER BY importance DESC
            LIMIT 10
            """,
            (ref_turn,),
        ).fetchall()

        # 关键词查：tags匹配，正常衰减过滤
        kw_rows = context.db.get_memories_by_keywords(
            kw_list, turn=context.state.turn, limit=10, ignore_expiry=False
        ) if kw_list else []

        # 合并去重，时间查优先
        seen: set = set()
        merged = []
        for r in list(time_rows) + list(kw_rows):
            rid = r["id"] if hasattr(r, "keys") else r[0]
            if rid not in seen:
                seen.add(rid)
                merged.append(r)

        if not merged:
            return f"{year}年{period}月前后未见相关旧事记忆。"
        lines = [f"【{year}年{period}月旧事】"]
        for r in merged:
            lines.append(
                f"- #{r['id']} {r['year']}年{r['period']}月 {r['subject_id']}："
                f"{r['title']}。起因：{r['cause']}。结果：{r['outcome']}。"
            )
        return "\n".join(lines)

    def search_memories(keywords: str) -> str:
        """检索相关旧事记忆摘要。两种场景必须调用：
        1. 皇帝问及某人/某地/某事时，先查有无相关历史记录再作答；
        2. 拟旨前涉及任何人事处置（任命/罢黜/下狱/赦免），先查该人旧事确认现状，避免重复处置。
        keywords: 逗号分隔的人名/地名/军队名/势力名/事项关键词，如 "魏忠贤,下狱" 或 "山东,民变"。
        返回命中的旧事摘要（含 #id）；无命中返回空提示。
        """
        kw_list = [k.strip() for k in str(keywords or "").split(",") if k.strip()]
        if not kw_list:
            return "请提供关键词（逗号分隔）。"
        memories = context.db.get_memories_by_keywords(
            kw_list, turn=context.state.turn, limit=8
        )
        if not memories:
            return f"未找到与「{'、'.join(kw_list)}」相关的旧事记忆。"
        from ming_sim.token_stats import tlog
        tlog(f"[search_memories] keywords={kw_list} hit={len(memories)}")
        lines = [f"【旧事检索：{' '.join(kw_list)}】"]
        for m in memories:
            lines.append(
                f"- #{m['id']} {m['year']}年{m['period']}月 {m['subject_id']}："
                f"{m['title']}。起因：{m['cause']}。结果：{m['outcome']}。"
            )
        return "\n".join(lines)

    def check_treasury() -> str:
        """查国库、内库、收支和欠账。"""
        return skill_template("check_treasury_prefix") + context.db.treasury_report(context.state)

    def inspect_treasury_ledger(account: str = "内库", turns: int = 6) -> str:
        """查国库或内库的历史流水明细（每笔收支原因、金额、余额）。
        涉及内库/国库调动来源、历史拨款、查抄收益、赏赐开销时调用。
        account: "国库" 或 "内库"；turns: 查最近几回合（默认6）。
        """
        acc = (account or "内库").strip()
        if acc not in {"国库", "内库"}:
            return "account 须为「国库」或「内库」。"
        try:
            t = max(1, min(24, int(turns)))
        except (TypeError, ValueError):
            t = 6
        return context.db.treasury_ledger(acc, t)

    def audit_tax_arrears(target: str = "各省积欠") -> str:
        """清查积欠、估算可追收入库。"""
        return skill_template("audit_tax_arrears", target=target)

    def allocate_payroll(target: str = f"本{TURN_UNIT}急需钱粮处") -> str:
        """核算军饷调度。"""
        return skill_template("allocate_payroll", target=target)

    def propose_directive(decree_text: str) -> str:
        """把已定处置方案拟成一道圣旨草稿呈给皇帝审阅。decree_text 为完整圣旨正文。"""
        text = (decree_text or "").strip()
        if not text:
            return "拟旨失败：圣旨正文为空。"
        # 返回草稿标记，由 minister_chat / GameSession.chat 截获展示给皇帝确认，不在此入库。
        return f"__pending_directive__{text}"

    def propose_appointment(name: str, office: str, faction: str = "中立", reason: str = "", replaces: str = "") -> str:
        """吏部铨选拟任。name 为拟任者，office 为拟授官职，replaces 为需腾缺的现任官员。"""
        nm = (name or "").strip()
        off = (office or "").strip()
        if not nm or not off:
            return "铨选失败：姓名或拟授官职为空。"
        import json as _json
        payload = _json.dumps(
            {
                "name": nm, "office": off,
                "faction": (faction or "中立").strip(),
                "reason": (reason or "").strip(),
                "replaces": (replaces or "").strip(),
            },
            ensure_ascii=False,
        )
        return f"__pending_appointment__{payload}"

    def register_unlisted_person(
        name: str,
        office: str,
        office_type: str,
        faction: str = "中立",
        aliases_json: str = "[]",
        summary: str = "",
        source: str = "historical",
        summon_after: bool = True,
    ) -> str:
        """登记名册外人物，使其进入本局可召见人物池。

        仅在两种情况下调用：
        1. source="historical"：名册无此人，但你高置信确认其为史实人物（含异体字、误写、近音、别名归一）。
        2. source="user_confirmed"：名册无此人且非明确史实，但皇帝已经说明其身份背景。

        不可用于正式升迁、外放或替换现任官缺；正式任官仍走吏部铨选或圣旨。
        aliases_json 填 JSON 数组字符串，如 ["李若璉","李若链","李若莲"]。
        """
        nm = (name or "").strip()
        off = (office or "").strip()
        kind = (office_type or "").strip()
        if not nm or not off or not kind:
            return "登记失败：姓名、职衔、官署类型不能为空。"
        try:
            aliases = json.loads(aliases_json or "[]")
        except (ValueError, TypeError):
            aliases = []
        if not isinstance(aliases, list):
            aliases = []
        payload = json.dumps(
            {
                "name": nm,
                "office": off,
                "office_type": kind,
                "faction": (faction or "中立").strip(),
                "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
                "summary": (summary or "").strip(),
                "source": (source or "historical").strip(),
                "summon_after": bool(summon_after),
            },
            ensure_ascii=False,
        )
        return f"__pending_unlisted_person__{payload}"

    def issue_secret_order(title: str, content: str, tags_json: str = "[]", assignee: str = "", deadline_months: int = 0) -> str:
        """皇帝下达密令，直接登记入档并返回密令编号。

        title：密令标题（20字内）。
        content：密令详情，交代任务目标、保密要求、期限等。
        tags_json：JSON 数组，填相关人名/地区/事项关键词，用于日后检索，如 '["辽饷","兵部","密查"]'。
        assignee：实际承办人姓名。留空则默认为当前召见的大臣；若皇帝指名他人承办（如"命毕自严去查"），填该人全名。
        deadline_months：硬期限月数；0 表示无硬期限。若皇帝说"一月内务必结案"填 1，说"三个月内结案"填 3。
        """
        t = (title or "").strip()[:20]
        c = (content or "").strip()
        if not t or not c:
            return "密令下达失败：标题或内容为空。"
        try:
            tags = json.loads(tags_json or "[]")
            if not isinstance(tags, list):
                tags = []
        except (ValueError, TypeError):
            tags = []
        tags_clean = [str(k).strip() for k in tags if str(k).strip()]
        real_assignee = (assignee or "").strip() or character.name
        try:
            deadline = max(0, min(int(deadline_months or 0), 36))
        except (TypeError, ValueError):
            deadline = 0
        try:
            order_id = context.db.create_secret_order(
                context.state, real_assignee, t, c, tags_clean, deadline_months=deadline
            )
        except ValueError as e:
            return f"密令下达失败：{e}"
        except Exception as e:
            return f"__secret_order__{json.dumps({'title': t, 'content': c, 'tags': tags_clean, 'assignee': real_assignee, 'deadline_months': deadline}, ensure_ascii=False)}"
        print(f"[secret_order/tool] 直接落库 id={order_id} assignee={real_assignee} title={t!r}")
        deadline_text = f"，御限 {deadline} 个月" if deadline else ""
        return f"__secret_order_registered__{order_id}__密令已登记入档，编号 #{order_id}，承办：{real_assignee}{deadline_text}，标题：{t}。"

    def _own_secret_order(order_id: int):
        """取本承办人名下密令；非承办人或不存在返回 (None, 提示串)。"""
        oid = int(order_id) if str(order_id).isdigit() else 0
        if not oid:
            return None, "密令编号无效。"
        order = context.db.get_secret_order(oid)
        if order is None:
            return None, f"查无此密令（编号 #{oid}）。"
        if order["minister_name"] != character.name:
            return None, f"密令 #{oid} 由{order['minister_name']}承办，非你职掌，无从查问。"
        return order, ""

    def report_secret_order_progress(order_id: int, progress: str = "") -> str:
        """皇帝问密令进度时调本工具——一步完成"查历史 + 落本日新进展"。
        - progress 非空且本日尚未推进且非建档当日 → 直接把本日这一步落档；
        - progress 为空、本日已推进、或本日即建档当日 → 只回历史不落档；
        **建档当日不能立刻推进**（领旨待办，后续日程再查）。
        **一日最多落一步**。结案另用 submit_secret_order_for_review。

        order_id：密令编号。
        progress：本日新查到的一步进展（100字内，顺着已有线索往下推一步）。仅查无需写时可省略。
        """
        order, err = _own_secret_order(order_id)
        if order is None:
            return err
        if order["status"] != "active":
            return f"密令 #{order['id']} 已{order['status']}，不能再记进展。"
        already_advanced = context.db._has_secret_order_period_line(
            order["id"], "result", context.state.year, context.state.period, context.state.day
        )
        is_issuing_turn = int(order.get("turn_issued") or 0) == int(context.state.turn)
        note = (progress or "").strip()[:200]
        saved = False
        if note and not already_advanced and not is_issuing_turn:
            saved = context.db.update_secret_order_progress(
                order["id"], note, year=context.state.year, period=context.state.period, day=context.state.day
            )
        # 落档后重读，让返回里的"查办经过"包含本日这一行
        order = context.db.get_secret_order(order["id"]) or order
        parts = [f"密令 #{order['id']}「{order['title']}」状态：{order['status']}。"]
        parts.append(f"查办经过（按日，末行最新）：\n{order['result'] or '尚无进展记录。'}")
        if order.get("sim_note"):
            parts.append(f"外间动静（按日，末行最新）：\n{order['sim_note']}")
        if saved:
            parts.append(f"✅ 本日新进展已落档：{note}")
        elif is_issuing_turn:
            parts.append("⚠️ 本日刚接密令，眼下只能领旨筹备、布置人手，须待后续日程才可查得头绪——本次未落档。回奏陛下时坦言「才接旨、尚未动身查访」即可。")
        elif already_advanced:
            parts.append("⚠️ 本日已查进一步，欲再进须待明日或后续通信——本次未再落档。")
        elif not note:
            parts.append("ℹ️ 未提供 progress 参数，本日仍未推进；下次调用请填 progress 把本日新一步落档。")
        return "\n".join(parts)

    def submit_secret_order_for_review(order_id: int, claim: str) -> str:
        """承办人自认任务办到位（或无法再推）时调本工具，把密令转入"待核议"，等推演据全盘面判最终成败。
        **大臣无权直接定 done/failed**——结案权归推演（season simulator），它会看承办人能力、目标实力、风声、派系反扑、可行性等因素，
        在日终奏报「密旨核议」章给出真实判定（实据齐 → done；不可行/虚报/反扑 → failed；仍需继续 → 退回 active）。

        order_id：密令编号。
        claim：你自述的办结陈词（200字内）。要写：声称已查得/办到的事实、关键证据、附带情况（如风声暴露程度、有无反扑迹象）。
              不要写"已处决/已抄家"等执行类动作——那些不是密令承办人能做的。
        """
        order, err = _own_secret_order(order_id)
        if order is None:
            return err
        if order["status"] != "active":
            return f"密令 #{order['id']} 当前状态 {order['status']}，不可重复提交核议。"
        text = (claim or "").strip()
        if not text:
            return "提交失败：claim 为空，须写明你声称办到了什么。"
        ok = context.db.submit_secret_order_for_review(
            order["id"], text, year=context.state.year, period=context.state.period, day=context.state.day
        )
        if not ok:
            return f"密令 #{order['id']} 提交失败（当前状态非 active）。"
        return f"密令 #{order['id']}「{order['title']}」已提交待推演核议，本日不再可推进。陛下可静候日终奏报「密旨核议」章定夺。"

    def rush_secret_order(order_id: int, deadline_months: int = 1, reason: str = "") -> str:
        """皇帝催办/加急某条密令时调用，缩短硬期限。

        order_id：密令编号。
        deadline_months：从今日起还给几个月。1=约一月内必须核议；0=本日立即送日终核议。
        reason：皇帝催办缘由或新限令，100字内。
        """
        order, err = _own_secret_order(order_id)
        if order is None:
            return err
        if order["status"] != "active":
            return f"密令 #{order['id']} 当前状态 {order['status']}，不能再催办。"
        try:
            rushed = context.db.rush_secret_order(
                order["id"], context.state, deadline_months=deadline_months, reason=reason
            )
        except Exception as exc:
            return f"密令 #{order['id']} 催办失败：{exc}"
        if rushed["status"] == "pending_review":
            return f"密令 #{order['id']}「{order['title']}」已奉旨即核，转入待核议；本日日终推演必须判 done/failed。"
        remain = max(0, int(rushed["due_turn"]) - int(context.state.turn))
        return f"密令 #{order['id']}「{order['title']}」已奉旨加急，限 {remain} 日内核议。"

    def dismiss_minister() -> str:
        """结束本次召见。"""
        return "__dismiss__"

    def summon_minister(name: str) -> str:
        """传召另一位大臣。name 填大臣姓名。"""
        return f"__summon__{name}"

    tools = [
        view_state,
        list_memorials,
        inspect_memorial,
        list_regions,
        inspect_region,
        list_armies,
        inspect_army,
        list_powers,
        list_buildings,
        inspect_building,
        list_court,
        list_personnel,
        inspect_minister,
        inspect_personnel_changes,
        estimate_resistance,
        read_past_report,
        search_memories,
        recall_memory_detail,
        recall_memories_by_time,
        inspect_treasury_ledger,
        propose_directive,
        issue_secret_order,
        report_secret_order_progress,
        submit_secret_order_for_review,
        rush_secret_order,
        dismiss_minister,
        summon_minister,
        register_unlisted_person,
    ]
    # 吏部尚书专属：铨选任命，可把名册外的史实官员补入朝堂。
    if character.office_type == "吏部":
        tools.append(propose_appointment)
    if "check_treasury" in skill_ids:
        tools.append(check_treasury)
    if "allocate_payroll" in skill_ids:
        tools.extend([check_treasury, allocate_payroll])
    if "audit_tax_arrears" in skill_ids:
        tools.append(audit_tax_arrears)
    unique_tools = []
    seen_tool_names: set = set()
    for tool in tools:
        name = getattr(tool, "__name__", str(tool))
        if name in seen_tool_names:
            continue
        seen_tool_names.add(name)
        unique_tools.append(tool)
    return unique_tools
