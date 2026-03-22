"""共享的城市代码映射（IATA 代码）"""

# 通用城市代码映射（覆盖国内主要城市）
COMMON_CITY_CODE_MAP = {
    "北京": "BJS",
    "上海": "SHA",
    "广州": "CAN",
    "深圳": "SZX",
    "成都": "CTU",
    "杭州": "HGH",
    "西安": "XIY",
    "重庆": "CKG",
    "南京": "NKG",
    "武汉": "WUH",
    "天津": "TSN",
    "青岛": "TAO",
    "大连": "DLC",
    "厦门": "XMN",
    "昆明": "KMG",
    "长沙": "CSX",
    "郑州": "CGO",
    "沈阳": "SHE",
    "济南": "TNA",
    "哈尔滨": "HRB",
    "三亚": "SYX",
    "海口": "HAK",
    "福州": "FOC",
    "南宁": "NNG",
    "贵阳": "KWE",
    "长春": "CGQ",
    "太原": "TYN",
    "兰州": "LHW",
    "乌鲁木齐": "URC",
    "呼和浩特": "HET",
    "银川": "INC",
    "西宁": "XNN",
    "拉萨": "LXA",
    "合肥": "HFE",
    "南昌": "KHN",
    "石家庄": "SJW",
    "温州": "WNZ",
    "宁波": "NGB",
    "无锡": "WUX",
    "烟台": "YNT",
    "珠海": "ZUH",
    "汕头": "SWA",
    "桂林": "KWL",
    "北海": "BHY",
    "丽江": "LJG",
    "大理": "DLU",
    "西双版纳": "JHG",
    "黄山": "TXN",
    "张家界": "DYG",
    "九寨沟": "JZH",
    "揭阳": "SWA",
    "惠州": "HUZ",
}


def get_city_code(city_name: str, fallback: str = None) -> str:
    """获取城市 IATA 代码

    Args:
        city_name: 城市名称（中文）
        fallback: 找不到时返回的默认值，默认返回原城市名

    Returns:
        城市 IATA 代码
    """
    return COMMON_CITY_CODE_MAP.get(city_name, fallback or city_name)
