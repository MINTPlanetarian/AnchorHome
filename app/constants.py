"""业务枚举常量（中文标签映射）。"""

# 账户类型（PRD v1.2：纯资金性质，共 7 类）
# 现金=纸币/活期/支付宝余额/微信零钱等随时可用的钱；理财=活期理财/定期/银行理财；
# 公积金=余额计入总资产但不计入可用资金；股票/基金=持仓制联网行情；
# 信用卡=负债性质；其他=兜底。
ACCOUNT_TYPES = [
    ("cash", "现金"),
    ("wealth", "理财"),
    ("provident_fund", "公积金"),
    ("fund", "基金"),
    ("stock", "股票"),
    ("credit_card", "信用卡"),
    ("other", "其他"),
]

# 币种（PRD FR-1.2）
CURRENCIES = ["CNY", "USD", "HKD", "EUR", "JPY"]

# 资产类型（PRD FR-2.1）
ASSET_TYPES = [
    ("real_estate", "房产"),
    ("vehicle", "车辆"),
    ("insurance", "保险"),
    ("precious_metal", "贵金属"),
    ("other", "其他"),
]

# 保险子类型（v1.3 优化）：保障型(无现金价值，不计资产) / 储蓄型(有现金价值，计资产)
INSURANCE_SUBTYPES = [
    ("protection", "保障型"),
    ("savings", "储蓄型"),
]

# 负债类型（PRD FR-3.1）
LIABILITY_TYPES = [
    ("mortgage", "房贷"),
    ("car_loan", "车贷"),
    ("consumer_loan", "消费贷"),
    ("credit_card", "信用卡欠款"),
    ("other", "其他"),
]

# 预置开户机构（PRD v1.2 2.3：下拉 + 可自定义）
INSTITUTIONS = [
    "工商银行", "建设银行", "农业银行", "中国银行", "招商银行",
    "交通银行", "邮储银行", "支付宝", "微信", "华泰证券",
    "中信证券", "东方财富证券",
]


def type_label(mapping: list[tuple[str, str]], key: str) -> str:
    """根据 key 返回中文标签，找不到时返回 key 本身。"""
    for k, label in mapping:
        if k == key:
            return label
    return key


def to_label_map(mapping: list[tuple[str, str]]) -> dict[str, str]:
    """把 [(key, label), ...] 转成 {key: label}，供按 key 直接取标签的场景。

    字典由上面的列表派生，新增枚举项时只需改列表一处，
    不必再同步维护散落各模块的同名字典。
    """
    return dict(mapping)


# 由上述列表派生的字典形式（原先 report_service 里另维护了一份同名副本）
ACCOUNT_TYPE_LABELS = to_label_map(ACCOUNT_TYPES)
ASSET_TYPE_LABELS = to_label_map(ASSET_TYPES)
LIABILITY_TYPE_LABELS = to_label_map(LIABILITY_TYPES)

