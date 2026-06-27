"""《明末》v2 垂直切片开局数据。史实为锚,数值为游戏化设定。

人物/派系的「身份基线」(name/office/faction/loyalty/ability)取自 v1 content/characters.json
(见 world.py);切片只覆盖戏剧字段(stance/secret/persona)与游戏化微调的数值。
省略的关键字参数即沿用 v1 基线值。
"""
from .state import GameState, Crisis
from .world import character, faction
from .events import DINGWEI_POOL


def _dingwei() -> GameState:
    return GameState(
        year=1627, month=11,
        metrics={"国库": 22, "皇威": 28, "民心": 45, "朝堂": 33, "耳目": 60, "边事": 50},
        factions={
            "阉党": faction("阉党", satisfaction=48,
                          note="掌司礼监、东厂、锦衣卫,根系遍布内廷与各地镇守、税监"),
            "东林": faction("东林", satisfaction=62, leverage=38,
                          note="刚从天启朝冤狱中昭雪、清流复起,然根基未稳、亟欲清算"),
        },
        characters={
            "王承恩": character(
                "王承恩", office="司礼监秉笔(信王府旧人)", ability=60,
                stance="一心向着陛下,却畏魏党势大,不敢明言",
                persona="谨慎忠谨,说话留三分,真急了才掏心窝子",
                secret="已察觉魏忠贤暗中转移宫中积银、党羽人心惶惶,但怕担『构陷』之名,不敢主动具奏"),
            "韩爌": character(
                "韩爌", office="东林元老,议复入阁", loyalty=70, ability=75,
                stance="力主即诛魏忠贤、尽除阉党,为天启冤死者昭雪",
                persona="持重讲名节,引经据典,步步逼陛下表态",
                secret="东林内部已草拟一长串『阉党』名册,意在借诛魏之势大举清算、安插己人"),
            "魏忠贤": character(
                "魏忠贤", office="司礼监掌印,提督东厂", ability=80,
                stance="上表乞休示弱,暗观新君虚实,留有后手",
                persona="谦卑惶恐的表面下藏极深城府,哭穷、表忠、试探,绝不先翻脸",
                secret="实已是惊弓之鸟:新君若铁腕,一旨即可令其树倒猢狲散;若犹豫,则可能反扑或拖延自保。党羽崔呈秀等仍居要职。"),
        },
        event_pool=list(DINGWEI_POOL),
        crises=[
            Crisis(
                "wei", "如何处置魏忠贤",
                brief=("魏忠贤连上乞休之表、姿态极低;东林交章弹劾,历数其十大罪。"
                       "然东厂、锦衣卫、内廷与各地镇守税监多出其门下,骤然发难,恐生意外之变。"),
                truth=("魏党外强中干、已成惊弓之鸟——新君只要意志坚决,一道明旨即可令其树倒猢狲散,"
                       "崔呈秀等党羽不足以成事。但东厂、锦衣卫、镇守太监这套『耳目』体系一旦随之清洗,"
                       "京畿与地方的情报网会骤然瘫痪,日后地方瞒报、边镇虚实、民变苗头都将更难察觉(耳目大跌)。"
                       "东林则必借机把『阉党』帽子扣向异己、大举安插私人(东林 leverage 涨,但朝堂未必更和)。"),
                adjudicator_notes="定魏裁判要点 诛魏则皇威民心涨东林喜但厂卫这套耳目体系瘫痪耳目大跌东林借机坐大留缓则东林失望皇威难立但保住耳目与制衡犹豫不决最糟两头不讨好玩家旨意越精细如留厂卫限株连代价越轻"),
        ],
        slice_id="dingwei",
    )


def _liaodong() -> GameState:
    return GameState(
        year=1628, month=4,
        metrics={"国库": 20, "皇威": 40, "民心": 44, "朝堂": 38, "耳目": 52, "边事": 32},
        factions={
            "军队": faction("军队", satisfaction=28, leverage=66,
                          note="关宁军为辽东支柱然欠饷四月士卒鼓噪祖大寿等将门尾大难制"),
            "东林": faction("东林", satisfaction=55, leverage=46,
                          note="清流当朝主守辽重名节然于筹饷之难多空谈"),
        },
        characters={
            "袁崇焕": character(
                "袁崇焕", office="兵部尚书督师蓟辽", loyalty=62, ability=88,
                stance="主守辽夸口五年复辽然军中已四月无饷催饷急如星火",
                persona="自信刚直敢任事催饷不留情面隐以辽事自重不耐掣肘",
                secret="塘报中夸大了后金即时威胁以多要饷皇太极此刻未必即攻且与东江毛文龙不和已起专戮其人之念"),
            "毕自严": character(
                "毕自严", office="户部尚书", faction="东林", loyalty=78, ability=82,
                stance="哭太仓之穷谓辽饷一项已耗天下太半实无银可拨力阻加派",
                persona="务实精核句句是账会哭穷却不虚报以国计为念",
                secret="太仓实存银百余万然江南积欠可催宗室禄米可缓盐课可清皆远水若骤加派民变在即"),
            "王承恩": character(
                "王承恩", office="司礼监秉笔", ability=60,
                stance="内库亦不丰然陛下若决意尚可挪三五十万以应燃眉",
                persona="谨慎忠谨为陛下计不愿轻动内帑却也不敢拦",
                secret="内库实存约百万系陛下私帑毕自严不敢请陛下自己亦舍不得轻用"),
        },
        crises=[
            Crisis(
                "liaodong", "辽东索饷",
                brief="督师袁崇焕连章告急关宁军欠饷四月士卒鼓噪宁锦缺粮塘报后金皇太极于辽阳整军似有西向之意户部尚书毕自严则称太仓空匮辽饷无出力阻加派",
                truth="欠饷属实再拖一两月关宁军必哗变或将领私通后金然袁崇焕塘报夸大了后金的即时威胁为多要饷皇太极此刻未必即攻补饷能稳军心固边事但国库已空筹饷处处是代价",
                adjudicator_notes="辽东索饷裁判要点 此为协作政务类非君命直贯钱不是说有就有严守资源约束 一国库仅20凭空拨大额银是空头支票军队不领情边事不稳 二加派加赋筹饷民心大跌可能激民变边事虽暂稳亦埋祸 三挪内库国库微补至多三五十万可解燃眉但不可持久 四催江南积欠清盐课缓宗禄远水这个月到不了当月军心仍危可为未来埋正向伏笔 五让欠饷切实有着落加安抚得当边事升军队satisfaction升resolved=True 六拖延空头支票只申饬不给钱边事大跌军队satisfaction大跌resolved=False且埋兵变 七给袁崇焕专权加足饷辽东可稳但养骄兵军队leverage升伏督师专权之患猜忌或裁撤袁而无良替边事危 八玩家若在召对中点破袁崇焕夸大军情可酌情少拨而边事不崩",
                cast=["guanning", "liaodong", "houjin"]),  # 点名关宁军+辽东边镇+后金:让裁判/召对引真实盘面(只进 LLM 提示,非确定、未入 golden)
        ],
        slice_id="liaodong",
    )


SLICES = {"dingwei": _dingwei, "liaodong": _liaodong}


def new_game(slice_id="dingwei") -> GameState:
    return SLICES[slice_id]()
