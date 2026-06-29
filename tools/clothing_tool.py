"""
穿衣建议工具
结合天气和用户画像提供个性化穿衣建议
"""

from datetime import datetime
from tools.weather_tool import get_forecast


async def get_clothing_advice(city: str = None, date: str = None) -> str:
    """
    获取穿衣建议（结合天气和用户画像）
    
    【服务逻辑】
    1. 查询目标城市天气
    2. 获取用户穿衣偏好（从 user_profile）
    3. 综合生成个性化建议
    """
    from user_profile import hybrid_retrieval
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. 获取用户画像中的位置和穿衣偏好
    profile = hybrid_retrieval("穿衣")
    
    # 确定城市
    if not city:
        city = profile["structured"]["basic"].get("location", "北京")
    
    # 获取穿衣偏好
    clothing_prefs = {}
    for pref in profile["structured"]["preferences"]:
        if pref["category"] == "clothing":
            clothing_prefs[pref["key"]] = pref["value"]
    
    # 获取天气偏好
    weather_prefs = {}
    for pref in profile["structured"]["preferences"]:
        if pref["category"] == "weather":
            weather_prefs[pref["key"]] = pref["value"]
    
    # 2. 查询天气
    weather_result = await get_forecast(city, days=1)
    
    # 3. 解析天气信息
    import re
    temp_match = re.search(r"(\d+)°C", weather_result)
    weather_desc = ""
    for keyword in ["晴", "多云", "阴", "雨", "雪", "雾"]:
        if keyword in weather_result:
            weather_desc = keyword
            break
    
    temp = int(temp_match.group(1)) if temp_match else 20
    
    # 4. 生成穿衣建议
    base_advice = ""
    if temp >= 28:
        base_advice = "👕 天气炎热，建议穿短袖、短裤、凉鞋"
    elif temp >= 20:
        base_advice = "👔 天气舒适，建议穿长袖衬衫或薄外套"
    elif temp >= 10:
        base_advice = "🧥 天气微凉，建议穿毛衣或厚外套"
    else:
        base_advice = "❄️ 天气寒冷，建议穿羽绒服、毛衣和厚裤子"
    
    # 结合天气状况
    if "雨" in weather_desc:
        base_advice += "，记得带雨伞"
    elif "雪" in weather_desc:
        base_advice += "，注意防滑保暖"
    
    # 结合用户偏好
    if clothing_prefs.get("风格"):
        base_advice += f"，您偏好{clothing_prefs['风格']}风格"
    
    if weather_prefs.get("怕冷") == "是":
        base_advice += "，您比较怕冷，建议多穿一件"
    elif weather_prefs.get("怕热") == "是":
        base_advice += "，您比较怕热，建议穿透气衣物"
    
    return f"{weather_result}\n\n{base_advice}"