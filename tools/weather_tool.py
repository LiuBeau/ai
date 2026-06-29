"""
天气服务工具
提供实时天气查询和天气预报功能
"""

import json
import re
import urllib.request
import urllib.parse
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


async def get_weather(city: str) -> str:
    """获取某个城市的实时天气"""
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=zh"
    try:
        with urllib.request.urlopen(geo_url, timeout=10) as geo_resp:
            geo_data = json.loads(geo_resp.read().decode('utf-8'))
            if not geo_data.get('results'):
                return f"未找到城市 '{city}'"
            lat = geo_data['results'][0]['latitude']
            lon = geo_data['results'][0]['longitude']
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
            with urllib.request.urlopen(weather_url, timeout=10) as weather_resp:
                w_data = json.loads(weather_resp.read().decode('utf-8'))
                current = w_data['current_weather']
                temp = current['temperature']
                weather_code = current['weathercode']
                code_desc = {
                    0: "晴天", 1: "晴天", 2: "多云", 3: "阴天",
                    45: "雾", 48: "雾",
                    51: "小雨", 53: "中雨", 55: "大雨",
                    61: "小雨", 63: "中雨", 65: "大雨",
                    80: "阵雨", 81: "中阵雨", 82: "大阵雨",
                    71: "小雪", 73: "中雪", 75: "大雪",
                }
                desc = code_desc.get(weather_code, f"未知({weather_code})")
                return f"{city}实时天气：{desc}，温度{temp}°C"
    except Exception as e:
        return f"获取{city}实时天气失败：{e}"


async def get_forecast(city: str, days: int = 3) -> str:
    """获取某个城市未来几天的天气预报"""
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=zh"
    try:
        with urllib.request.urlopen(geo_url, timeout=10) as geo_resp:
            geo_data = json.loads(geo_resp.read().decode('utf-8'))
            if not geo_data.get('results'):
                return f"未找到城市 '{city}'"
            lat = geo_data['results'][0]['latitude']
            lon = geo_data['results'][0]['longitude']
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days={min(days, 16)}"
            with urllib.request.urlopen(weather_url, timeout=10) as weather_resp:
                w_data = json.loads(weather_resp.read().decode('utf-8'))
                daily = w_data['daily']
                code_desc = {
                    0: "晴天", 1: "晴天", 2: "多云", 3: "阴天",
                    45: "雾", 48: "雾",
                    51: "小雨", 53: "中雨", 55: "大雨",
                    61: "小雨", 63: "中雨", 65: "大雨",
                    80: "阵雨", 81: "中阵雨", 82: "大阵雨",
                    71: "小雪", 73: "中雪", 75: "大雪",
                }
                forecast_lines = [f"{city}未来{days}天天气预报："]
                for i in range(min(days, len(daily['time']))):
                    date = daily['time'][i]
                    max_temp = daily['temperature_2m_max'][i]
                    min_temp = daily['temperature_2m_min'][i]
                    code = daily['weathercode'][i]
                    desc = code_desc.get(code, f"未知({code})")
                    forecast_lines.append(f"  {date}：{desc}，{min_temp}°C ~ {max_temp}°C")
                return "\n".join(forecast_lines)
    except Exception as e:
        return f"获取{city}天气预报失败：{e}"


async def parse_weather_info(weather_result: str) -> dict:
    """解析天气信息为结构化数据"""
    result = {"temp": 20, "desc": "", "city": ""}
    
    temp_match = re.search(r"(\d+)°C", weather_result)
    if temp_match:
        result["temp"] = int(temp_match.group(1))
    
    for keyword in ["晴", "多云", "阴", "雨", "雪", "雾", "雷"]:
        if keyword in weather_result:
            result["desc"] = keyword
            break
    
    city_match = re.search(r"(.+?)实时天气|(.+?)未来", weather_result)
    if city_match:
        result["city"] = city_match.group(1) or city_match.group(2)
    
    return result