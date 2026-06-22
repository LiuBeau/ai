import asyncio
import requests
from openai import AsyncOpenAI
import httpx
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== 1. 配置 =====
# 替换成你的 DeepSeek API Key
DEEPSEEK_API_KEY = "sk-cacc8018b55b4db49748dcbd4673ca1d"
http_client = httpx.AsyncClient(verify=False)


# 初始化 DeepSeek 客户端
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",  # 必须指向 DeepSeek
    http_client=http_client
)


# ===== 2. 天气工具（使用 Open-Meteo，免费无需密钥）=====
async def get_weather(city: str) -> str:
    """通过 Open-Meteo 免费 API 获取天气"""
    # 地理编码：城市名 → 经纬度
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh"
    try:
        geo_resp = requests.get(geo_url, verify=False, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        if not geo_data.get('results'):
            return f"未找到城市 '{city}'"
        lat = geo_data['results'][0]['latitude']
        lon = geo_data['results'][0]['longitude']

        # 获取天气
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
        weather_resp = requests.get(weather_url, verify=False, timeout=10)
        weather_resp.raise_for_status()
        w_data = weather_resp.json()
        current = w_data['current_weather']
        temp = current['temperature']
        weather_code = current['weathercode']

        # 天气代码转文字（简化）
        code_desc = {
            0: "晴天", 1: "晴天", 2: "多云", 3: "阴天",
            45: "雾", 48: "雾",
            51: "小雨", 53: "中雨", 55: "大雨",
            61: "小雨", 63: "中雨", 65: "大雨",
            80: "阵雨", 81: "中阵雨", 82: "大阵雨",
            71: "小雪", 73: "中雪", 75: "大雪",
        }
        desc = code_desc.get(weather_code, f"未知({weather_code})")
        return f"{city}天气：{desc}，温度{temp}°C"
    except Exception as e:
        return f"获取{city}天气失败：{e}"


# ===== 3. 核心 Agent 逻辑 =====
async def ask_agent(user_input: str):
    """处理用户输入，自动判断是否调用天气工具"""
    # 第一步：判断是否询问天气，提取城市名
    judge_prompt = f"""
你是一个天气助手。用户说：“{user_input}”
请判断用户是否在询问某个城市的天气。
如果是，请只返回城市名称（例如“北京”），不要有其他内容。
如果不是，请只返回“无”。
"""
    judge_response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": judge_prompt}],
        temperature=0,
    )
    city = judge_response.choices[0].message.content.strip()

    # 第二步：如需天气，调用工具
    if city != "无":
        weather_info = await get_weather(city)
    else:
        weather_info = "用户没有询问天气，直接回答即可。"

    # 第三步：生成友好回复（含穿衣建议）
    final_prompt = f"""
你是一个贴心的天气助理。
用户的问题：{user_input}
你掌握的天气信息：{weather_info}
请根据这些信息，给用户一个友好、自然的回答，并附上穿衣建议（如果涉及天气）。
如果用户没有问天气，就正常聊天。
"""
    final_response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.7,
        stream=True,
    )
    # 流式输出
    print("助手：", end="")
    async for chunk in final_response:
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="")
    print("\n")


# ===== 4. 主程序 =====
async def main():
    user_input = "北京今天天气怎么样？"
    print(f"用户：{user_input}")
    await ask_agent(user_input)


if __name__ == "__main__":
    asyncio.run(main())
