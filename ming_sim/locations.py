"""Location inference helpers for character/court communication."""

from __future__ import annotations

import re
from typing import Tuple


COURT_LOCATION = "beizhili"


def infer_character_location(
    office: str,
    office_type: str = "",
    status: str = "",
) -> Tuple[str, bool, str]:
    """Infer a character region_id from office/status text.

    Returns (region_id, defaulted, reason). The default is the court location:
    newly appointed central officials are assumed to return to Beijing unless
    a provincial or exile/residence clue is present.
    """
    text = f"{office or ''} {office_type or ''} {status or ''}"

    explicit_rules = [
        (r"东莞|广东|广州|潮州|惠州", "guangdong", "官职/居地指向广东"),
        (r"南京|应天|常熟|松江|上海|凤阳", "nanzhili", "官职/居地指向南直隶"),
        (r"蒲州|山西|大同|宣大", "shanxi", "官职/居地指向山西/宣大"),
        (r"陕西|陕北|延安|督粮参政", "shaanxi", "官职/居地指向陕西"),
        (r"辽东|锦州|宁锦|蓟辽|山海关|关宁", "liaodong", "官职/居地指向辽东/山海关"),
        (r"东江|皮岛", "dongjiang_area", "官职/居地指向东江"),
        (r"登莱|山东", "shandong", "官职/居地指向山东"),
        (r"永城|河南|睢州|开封|洛阳", "henan", "官职/居地指向河南"),
        (r"大名府|高阳|北直隶|京师|京营|信邸|司礼监|东厂|锦衣卫|内阁|翰林院|都察院", "beizhili", "官职/居地指向京师"),
        (r"浙江|杭州|宁波|绍兴", "zhejiang", "官职/居地指向浙江"),
        (r"江西|南昌", "jiangxi", "官职/居地指向江西"),
        (r"湖广|武昌|荆州", "huguang", "官职/居地指向湖广"),
        (r"四川|成都", "sichuan", "官职/居地指向四川"),
        (r"福建|福州|泉州", "fujian", "官职/居地指向福建"),
        (r"广西|桂林", "guangxi", "官职/居地指向广西"),
        (r"云南|昆明", "yunnan", "官职/居地指向云南"),
        (r"贵州|贵阳", "guizhou", "官职/居地指向贵州"),
        (r"朝鲜", "shandong", "朝鲜使归途按登莱/山东通信估算"),
    ]
    for pattern, region_id, reason in explicit_rules:
        if re.search(pattern, text):
            return region_id, False, reason

    if office_type in {"后宫", "内阁", "吏部", "户部", "礼部", "兵部", "刑部", "工部", "司礼监", "东厂", "锦衣卫", "都察院", "翰林院"}:
        return COURT_LOCATION, False, "京官/内廷默认在京师"

    return COURT_LOCATION, True, "未能从官职/居地推断，默认回京师"
