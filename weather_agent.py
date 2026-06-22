import asyncio
import requests
import json
import httpx
import urllib3
from openai import AsyncOpenAI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== 1. 配置 =====
DEEPSEEK_API_KEY = "sk-cacc8018b55b4db49748dcbd4673ca1d"
http_client = httpx.AsyncClient(verify=False)

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    http_client=http_client
)


# ===== 2. 工具定义（与之前相同）=====

async def get_weather(city: str) -> str:
    """获取某个城市的实时天气"""
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh"
    try:
        geo_resp = requests.get(geo_url, verify=False, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        if not geo_data.get('results'):
            return f"未找到城市 '{city}'"
        lat = geo_data['results'][0]['latitude']
        lon = geo_data['results'][0]['longitude']

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
        weather_resp = requests.get(weather_url, verify=False, timeout=10)
        weather_resp.raise_for_status()
        w_data = weather_resp.json()
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
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh"
    try:
        geo_resp = requests.get(geo_url, verify=False, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        if not geo_data.get('results'):
            return f"未找到城市 '{city}'"
        lat = geo_data['results'][0]['latitude']
        lon = geo_data['results'][0]['longitude']

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days={min(days, 16)}"
        weather_resp = requests.get(weather_url, verify=False, timeout=10)
        weather_resp.raise_for_status()
        w_data = weather_resp.json()
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


# ===== 3. 工具注册表 =====
TOOLS = {
    "get_weather": {
        "func": get_weather,
        "description": "获取某个城市的实时天气，适用于查询今天或当前的天气",
        "params": {"city": "城市名称，如：北京、上海、深圳"}
    },
    "get_forecast": {
        "func": get_forecast,
        "description": "获取某个城市未来几天的天气预报，适用于查询明天、后天或未来多天的天气",
        "params": {"city": "城市名称，如：北京、上海、深圳", "days": "查询天数，默认为3天"}
    }
}

# ===== 4. 核心 Agent 逻辑（L2：带记忆）=====

# 🧠 在函数外部维护对话历史（长期保存）
conversation_history = []


async def ask_agent(user_input: str):
    """处理用户输入，带多轮记忆"""
    """
    短期记忆存在上限
    1、硬上限：模型的上下文窗口
    2、软上限：“平方级衰减”；计算量暴涨，注意力分散
    常用的解决方案：
    1、滑动窗口
    2、总结压缩
    3、RAG（检索增强）
    """
    global conversation_history

    # 4.1 把用户输入加入历史
    conversation_history.append({"role": "user", "content": user_input})

    # 4.2 构建工具描述，让 LLM 选择
    tools_desc = "\n".join([
        f"- {name}：{info['description']}，参数：{info['params']}"
        for name, info in TOOLS.items()
    ])

    # 🆕 System Prompt 增强：告诉 LLM 它可以参考对话历史
    system_prompt = f"""
你是一个智能助手，负责判断用户需要调用哪个工具。

可用工具：
{tools_desc}

重要规则：
1. 如果用户没有明确说城市，但之前的对话中提到过，请沿用之前的城市。
2. 如果用户说“明天呢”、“后天呢”，指的是之前提到的城市的天气。
3. 请返回 JSON 格式：{{"tool": "工具名", "params": {{"参数名": "参数值"}}}}
4. 如果不需要调用任何工具，返回：{{"tool": "none"}}

注意：
- 如果用户问的是"今天"或"现在"的天气，用 get_weather
- 如果用户问的是"明天"、"未来几天"或"天气预报"，用 get_forecast
- days 参数默认为 3，除非用户明确说了天数
"""

    # 4.3 构建完整的 messages（系统提示 + 对话历史 + 当前问题）
    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_history  # 👈 展开所有历史记录
    ]

    # 4.4 调用 LLM 进行工具选择
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0,
    )

    # 4.5 解析 JSON
    try:
        result = json.loads(response.choices[0].message.content)
        tool_name = result.get("tool", "none")
        params = result.get("params", {})
    except json.JSONDecodeError:
        tool_name = "none"
        params = {}

    # 4.6 执行工具
    if tool_name != "none" and tool_name in TOOLS:
        tool_func = TOOLS[tool_name]["func"]
        for key, value in params.items():
            if key == "days" and isinstance(value, str):
                params[key] = int(value)
        weather_info = await tool_func(**params)
    else:
        weather_info = "用户没有询问天气，直接回答即可。"

    # 4.7 生成友好回复（同样带上完整历史）
    final_system_prompt = """
你是一个贴心的天气助理。
请根据用户的问题和你掌握的天气信息，给出友好、自然的回答，并附上穿衣建议。
如果用户没有问天气，就正常聊天。
"""

    final_messages = [
        {"role": "system", "content": final_system_prompt},
        *conversation_history,
        {"role": "assistant", "content": f"掌握的天气信息：{weather_info}"}
    ]

    final_response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=final_messages,
        temperature=0.7,
        stream=True,
    )

    # 4.8 收集完整回复（用于存入历史）
    full_response = ""
    print("助手：", end="")
    async for chunk in final_response:
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="")
            full_response += content
    print("\n")

    # 4.9 把助手的回复存入历史
    conversation_history.append({"role": "assistant", "content": full_response})


# ===== 5. 主程序（支持连续对话）=====
async def main():
    print("=" * 50)
    print("🌤️  智能天气助手 L2（带记忆）已启动")
    print("💡 提示：输入 '退出' 结束对话")
    print("=" * 50)

    while True:
        user_input = input("\n你：")
        if user_input in ["退出", "exit", "quit"]:
            print("👋 再见！")
            break
        await ask_agent(user_input)


if __name__ == "__main__":
    asyncio.run(main())
