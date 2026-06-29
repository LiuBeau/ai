import asyncio
import requests
import json
import httpx
import urllib3
import re
from openai import AsyncOpenAI
import sqlite3
from datetime import datetime
from win11toast import toast
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== 1. 配置 =====
DEEPSEEK_API_KEY = "01dc2c1ac9e044d28083b1014573a385.q0roblJozvn4AFLD"
http_client = httpx.AsyncClient(verify=False)

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    http_client=http_client
)

# ===== 1.5 数据库管理（用户偏好持久化）=====

DB_PATH = "user_profile.db"


def load_life_knowledge():
    """将 life_knowledge.json 中的知识导入向量库"""
    try:
        with open("life_knowledge.json", "r", encoding="utf-8") as f:
            knowledge_list = json.load(f)

        # 检查是否已导入（避免重复）
        existing = memory_collection.get()
        if existing['ids']:
            return  # 已有知识，跳过

        for item in knowledge_list:
            content = item.get("content", "")
            category = item.get("category", "生活知识")
            # 把关键词和分类也拼到内容里，提高检索准确性
            enhanced_content = f"[{category}] {content}"
            doc_id = f"know_{category}_{int(time.time() * 1000)}_{len(memory_collection.get()['ids'])}"
            memory_collection.add(
                documents=[enhanced_content],
                metadatas=[{"category": category, "source": "life_knowledge"}],
                ids=[doc_id]
            )
        print(f"✅ 已加载 {len(knowledge_list)} 条生活知识")
    except FileNotFoundError:
        print("⚠️ life_knowledge.json 未找到，跳过加载")
    except Exception as e:
        print(f"⚠️ 加载生活知识失败：{e}")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS preferences (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversation_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        summary TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_preference(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO preferences (key, value, updated_at)
    VALUES (?, ?, ?)
    """, (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"💾 [记忆] 已保存偏好：{key} = {value}")


def load_preferences() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM preferences")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def save_conversation_summary(summary: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO conversation_summary (summary, created_at)
    VALUES (?, ?)
    """, (summary, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_recent_summaries(limit: int = 5) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT summary FROM conversation_summary
    ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


init_db()

# ===== 1.6 向量记忆库（无 torch 版本）=====

# 初始化 Chroma 客户端（持久化存储）
chroma_client = chromadb.PersistentClient(path="./chroma_memory")

# 使用 ONNX 版本的 MiniLM（轻量，不需要 torch，兼容 Windows）
try:
    embedding_fn = ONNXMiniLM_L6_V2()
    memory_collection = chroma_client.get_or_create_collection(
        name="life_memory",
        embedding_function=embedding_fn
    )
    print("✅ 向量记忆库初始化成功（使用 ONNX embedding）")
except Exception as e:
    print(f"⚠️ ONNX embedding 初始化失败：{e}")
    # 如果 ONNX 也失败，回退到默认 embedding（Chroma 内置）
    memory_collection = chroma_client.get_or_create_collection(
        name="life_memory"
    )
    print("✅ 向量记忆库初始化成功（使用默认 embedding）")

load_life_knowledge()

async def remember_memory(content: str, category: str = "general") -> str:
    try:
        import time
        doc_id = f"mem_{int(time.time() * 1000)}"
        memory_collection.add(
            documents=[content],
            metadatas=[{"category": category, "timestamp": time.time()}],
            ids=[doc_id]
        )
        print(f"💾 [记忆] 已存储：{content[:50]}...")
        return f"✅ 已记住：{content[:30]}..."
    except Exception as e:
        return f"⚠️ 记忆存储失败：{e}"


async def recall_memory(query: str, n_results: int = 3) -> str:
    try:
        results = memory_collection.query(
            query_texts=[query],
            n_results=n_results
        )
        if not results['documents'] or not results['documents'][0]:
            return "📭 暂时没有相关的记忆。"
        memories = []
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i] if results['metadatas'] else {}
            category = metadata.get('category', 'general')
            memories.append(f"[{category}] {doc}")
        return "📖 我回忆起以下相关记忆：\n" + "\n".join(memories)
    except Exception as e:
        return f"⚠️ 记忆检索失败：{e}"


# ===== 2. 工具定义 =====

async def get_weather(city: str) -> str:
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


async def display_notification(title: str, content: str) -> str:
    try:
        toast(title, content, duration="short")
        print(f"\n📢 桌面通知已发送：{title}")
        return f"桌面通知已发送：{title}"
    except Exception as e:
        print(f"⚠️ 桌面通知失败({e})，降级为终端显示")
        print("\n" + "=" * 50)
        print(f"📢 {title}")
        print("=" * 50)
        print(content)
        print("=" * 50 + "\n")
        return f"通知已显示（终端模式）：{title}"


async def query_tasks(date: str = None) -> str:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        with open("tasks.json", "r", encoding="utf-8") as f:
            all_tasks = json.load(f)
        for entry in all_tasks:
            if entry["date"] == date:
                tasks = entry["tasks"]
                if not tasks:
                    return f"📋 {date} 没有待办事项，放松一下吧！"
                task_list = "\n".join([f"  • {t}" for t in tasks])
                return f"📋 {date} 的待办事项：\n{task_list}"
        return f"📋 {date} 没有安排任何任务。"
    except FileNotFoundError:
        return "⚠️ 日程文件未找到，请先创建 tasks.json"
    except Exception as e:
        return f"⚠️ 查询日程失败：{e}"


async def add_task(task: str, date: str = None) -> str:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        try:
            with open("tasks.json", "r", encoding="utf-8") as f:
                all_tasks = json.load(f)
        except FileNotFoundError:
            all_tasks = []
        found = False
        for entry in all_tasks:
            if entry["date"] == date:
                entry["tasks"].append(task)
                found = True
                break
        if not found:
            all_tasks.append({"date": date, "tasks": [task]})
        with open("tasks.json", "w", encoding="utf-8") as f:
            json.dump(all_tasks, f, ensure_ascii=False, indent=2)
        return f"✅ 已添加任务：{task}（日期：{date}）"
    except Exception as e:
        return f"⚠️ 添加任务失败：{e}"


async def complete_task(task: str, date: str = None) -> str:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        with open("tasks.json", "r", encoding="utf-8") as f:
            all_tasks = json.load(f)
        for entry in all_tasks:
            if entry["date"] == date:
                if task in entry["tasks"]:
                    entry["tasks"].remove(task)
                    with open("tasks.json", "w", encoding="utf-8") as f:
                        json.dump(all_tasks, f, ensure_ascii=False, indent=2)
                    return f"✅ 已完成任务：{task}"
                else:
                    return f"⚠️ 在 {date} 未找到任务：{task}"
        return f"⚠️ {date} 没有任何任务"
    except Exception as e:
        return f"⚠️ 完成任务失败：{e}"

async def web_search(query: str) -> str:
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
        response = requests.get(url)
        data = response.json()
        if data.get('Abstract'):
            return data['Abstract']
        elif data.get('RelatedTopics'):
            return data['RelatedTopics'][0].get('Text', '未找到相关信息')
        else:
            return f"🔍 关于'{query}'的搜索无结果。"
    except Exception as e:
        return f"⚠️ 联网搜索失败：{e}"

# ===== 3. 工具注册表 =====
TOOLS = {
    "get_weather": {
        "func": get_weather,
        "description": "获取某个城市的实时天气",
        "params": {"city": "城市名称"}
    },
    "get_forecast": {
        "func": get_forecast,
        "description": "获取某个城市未来几天的天气预报",
        "params": {"city": "城市名称", "days": "天数，默认为3"}
    },
    "display_notification": {
        "func": display_notification,
        "description": "在屏幕上显示通知信息，用于向用户展示重要提醒",
        "params": {"title": "通知标题", "content": "通知内容"}
    },
    "query_tasks": {
        "func": query_tasks,
        "description": "查询指定日期的待办事项日程",
        "params": {"date": "日期，格式 YYYY-MM-DD，默认为今天"}
    },
    "add_task": {
        "func": add_task,
        "description": "添加一条待办事项到指定日期",
        "params": {"task": "任务内容描述", "date": "日期，格式 YYYY-MM-DD，默认为今天"}
    },
    "complete_task": {
        "func": complete_task,
        "description": "标记一条待办事项为已完成（删除）",
        "params": {"task": "要完成的任务内容", "date": "日期，格式 YYYY-MM-DD，默认为今天"}
    },
    "remember_memory": {
        "func": remember_memory,
        "description": "记住用户分享的生活信息、偏好、计划或个人事实。当用户提到自己的喜好、计划、生活细节时使用。",
        "params": {"content": "要记住的内容", "category": "偏好/计划/事实/通用"}
    },
    "recall_memory": {
        "func": recall_memory,
        "description": "根据用户的问题，检索之前记住的相关生活信息。当用户询问过去的喜好、计划或说过的话时使用。",
        "params": {"query": "检索关键词或问题", "n_results": "返回结果数量，默认为3"}
    },
    "web_search": {
        "func": web_search,
        "description": "根据用户的问题,本地知识检索不到的时候，使用联网功能查询",
        "params": {"query": "检索关键词或问题", "n_results": "返回结果数量，默认为3"}
    }
}


# ===== 4. 辅助函数：引导语生成 =====
def _generate_guide(user_input: str, last_result: str) -> str:
    if any(kw in user_input for kw in ["天气", "温度", "下雨", "晴天", "多云"]):
        if "雨" in last_result:
            return "💡 温馨提示：今天有雨，出门记得带伞哦！\n🌤️ 需要我帮您查一下明天的天气吗？"
        elif "晴" in last_result:
            return "☀️ 今天天气晴朗，适合出门活动！\n💡 需要我帮您规划一下今天的日程吗？"
        else:
            return "🌤️ 天气信息已送达！\n💡 需要我帮您查其他城市，或者看看今天的待办事项吗？"
    if any(kw in user_input for kw in ["待办", "日程", "任务", "事项"]):
        if "没有" in last_result or "无" in last_result:
            return "📋 今天没有任务，可以放松一下！\n💡 需要我帮您查一下天气吗？"
        else:
            return "📋 今天的任务已列出！\n💡 需要我帮您添加新任务，或者查一下天气吗？"
    return "💡 我还可以帮您查天气、管理日程、设置提醒，有什么需要就告诉我吧！"


# ===== 5. 核心 Agent 逻辑 =====
async def _extract_and_save_preferences(history: list):
    recent_history = history[-6:] if len(history) > 6 else history
    extract_prompt = f"""
从以下对话中提取用户的个人偏好，返回 JSON 格式。
对话历史：{json.dumps(recent_history, ensure_ascii=False, indent=2)}
可能提取的偏好字段：city, clothing_preference, diet, activity, other
如果没有提取到任何新偏好，返回空 JSON：{{}}
只返回 JSON，不要有其他文字。
"""
    try:
        response = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        preferences = json.loads(content.strip())
        for key, value in preferences.items():
            if value:
                save_preference(key, value)
    except Exception as e:
        print(f"⚠️ [记忆] 提取偏好失败：{e}")


async def ask_agent(user_input: str, max_steps: int = 5):
    tools_desc = "\n".join([
        f"- {name}：{info['description']}，参数：{info['params']}"
        for name, info in TOOLS.items()
    ])
    user_prefs = load_preferences()
    pref_text = ""
    if user_prefs:
        pref_text = "\n\n用户的个人偏好：\n" + "\n".join([f"- {k}: {v}" for k, v in user_prefs.items()])

    system_prompt = f"""
你是一个能自主规划和执行任务的智能助手。
可用工具：{tools_desc}
{pref_text}
请严格按照以下格式进行思考和行动：
思考：我需要先做第一步...
行动：调用 get_forecast，参数 {{"city": "北京", "days": 1}}
当你认为任务已经全部完成，不再需要调用任何工具时，输出：
思考：所有任务已完成
行动：完成
重要规则：
1. 每次只能调用一个工具
2. 参数必须使用 JSON 格式
3. 最多执行 {max_steps} 步
4. 如果用户分享个人生活信息或偏好，请调用 remember_memory 保存。
5. 如果用户询问过去的记忆或偏好，请先调用 recall_memory 检索。
6. 【生活知识】：当用户咨询穿衣搭配、旅游出行、饮食健康等生活问题时，请先调用 recall_memory 检索相关知识库，再结合用户偏好给出个性化建议。
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    step = 0
    reflection_count = 0
    print(f"\n🤖 [Agent] 开始自主规划...")
    while step < max_steps:
        step += 1
        print(f"\n🔄 [Agent] 第 {step} 步思考...")
        if not messages or not any(m["role"] == "user" for m in messages):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        try:
            response = await client.chat.completions.create(
                model="glm-4-flash",
                messages=messages,
                temperature=0.3,
            )
        except Exception as e:
            print(f"❌ [Agent] LLM 调用失败：{e}")
            return f"⚠️ 请求失败，请稍后重试。错误：{e}"
        output = response.choices[0].message.content
        print(f"💭 [Agent] 原始输出：\n{output}\n{'-' * 40}")
        if "行动：完成" in output or "思考：所有任务已完成" in output:
            print(f"✅ [Agent] 任务完成！")
            final_answer = ""
            for msg in reversed(messages):
                if msg["role"] == "user" and msg["content"].startswith("观察结果："):
                    final_answer = msg["content"].replace("观察结果：", "")
                    break
            if not final_answer:
                final_answer = output.split("行动：完成")[0].strip()
            guide = _generate_guide(user_input, final_answer)
            await _extract_and_save_preferences(messages)
            return f"{final_answer}\n\n{guide}"
        action_line = None
        for line in output.split('\n'):
            if line.strip().startswith('行动：'):
                action_line = line.strip()
                break
        if not action_line:
            print("⚠️ [Agent] 未找到'行动：'指令，检查是否已完成任务...")
            has_observation = any(
                msg["role"] == "user" and msg["content"].startswith("观察结果：")
                for msg in messages
            )
            if has_observation:
                print("✅ [Agent] 检测到任务已有结果，主动结束循环")
                last_observation = ""
                for msg in reversed(messages):
                    if msg["role"] == "user" and msg["content"].startswith("观察结果："):
                        last_observation = msg["content"].replace("观察结果：", "")
                        break
                guide = _generate_guide(user_input, last_observation)
                await _extract_and_save_preferences(messages)
                return f"{last_observation}\n\n{guide}"
            print("⚠️ [Agent] 尝试推断用户意图...")
            weather_keywords = ["天气", "温度", "下雨", "晴天", "多云", "预报"]
            task_query_keywords = ["待办", "日程", "任务", "事项", "todo", "有什么", "有没有"]
            task_add_keywords = ["添加", "加入", "增加", "加一条", "新增"]
            task_complete_keywords = ["完成", "做完", "结束", "搞定", "删除", "去掉"]
            if any(kw in user_input for kw in weather_keywords):
                prefs = load_preferences()
                city = prefs.get("city", "北京")
                tool_name = "get_forecast"
                params = {"city": city, "days": 1}
                print(f"🔍 推断为天气查询，城市：{city}")
            elif any(kw in user_input for kw in task_add_keywords):
                task_content = user_input
                for kw in task_add_keywords:
                    task_content = task_content.replace(kw, "").strip()
                tool_name = "add_task"
                params = {"task": task_content, "date": datetime.now().strftime("%Y-%m-%d")}
                print(f"🔍 推断为添加任务：{task_content}")
            elif any(kw in user_input for kw in task_complete_keywords):
                task_content = user_input
                for kw in task_complete_keywords:
                    task_content = task_content.replace(kw, "").strip()
                tool_name = "complete_task"
                params = {"task": task_content, "date": datetime.now().strftime("%Y-%m-%d")}
                print(f"🔍 推断为完成任务：{task_content}")
            elif any(kw in user_input for kw in task_query_keywords):
                tool_name = "query_tasks"
                params = {"date": datetime.now().strftime("%Y-%m-%d")}
                print(f"🔍 推断为日程查询")
            else:
                friendly_reply = "我不太理解您的意思，请明确告诉我您需要查询天气、日程还是其他帮助。"
                messages.append({"role": "assistant", "content": output})
                messages.append({"role": "user", "content": friendly_reply})
                return friendly_reply
            if tool_name in TOOLS:
                tool_func = TOOLS[tool_name]["func"]
                observation = await tool_func(**params)
                messages.append({"role": "assistant", "content": output})
                messages.append({"role": "user", "content": f"观察结果：{observation}"})
                continue
            else:
                return "抱歉，暂时无法处理您的请求。"
        try:
            tool_match = re.search(r'调用\s+(\w+)', action_line)
            if not tool_match:
                print("⚠️ [Agent] 无法解析工具名，触发反思...")
                messages.append({"role": "assistant", "content": output})
                messages.append({"role": "user", "content": f"无法从'{action_line}'中解析工具名，请检查格式。"})
                continue
            tool_name = tool_match.group(1)
            params_match = re.search(r'参数\s+(\{.*?\})', action_line)
            if not params_match:
                print("⚠️ [Agent] 无法解析参数，触发反思...")
                messages.append({"role": "assistant", "content": output})
                messages.append({"role": "user", "content": "参数必须使用 JSON 格式，请重新输出。"})
                continue
            params = json.loads(params_match.group(1))
            print(f"🔧 [Agent] 执行工具：{tool_name}，参数：{params}")
            if tool_name == "query_tasks" and "date" in params:
                today = datetime.now().strftime("%Y-%m-%d")
                if params["date"] != today:
                    print(f"⚠️ [Agent] 日期参数 '{params['date']}' 不是今天，自动修正为 '{today}'")
                    params["date"] = today
            if tool_name in TOOLS:
                tool_func = TOOLS[tool_name]["func"]
                for key, value in params.items():
                    if key == "days" and isinstance(value, str):
                        params[key] = int(value)
                observation = await tool_func(**params)
                print(f"📊 [Agent] 观察结果：{observation[:100]}...")
                if "失败" in observation or "未找到" in observation or "Error" in observation:
                    reflection_count += 1
                    if reflection_count > 2:
                        print("⚠️ [Agent] 反思次数过多，直接反馈用户")
                        messages.append({"role": "assistant", "content": output})
                        messages.append({"role": "user", "content": f"工具执行失败：{observation}，请告诉我下一步需求。"})
                        continue
                    print(f"⚠️ [Agent] 检测到执行失败，触发自我反思（{reflection_count}次）")
                    reflection_msg = f"工具 {tool_name} 执行失败。观察结果：{observation}。\n请分析原因并修正，不要重复相同的调用。"
                    messages.append({"role": "assistant", "content": output})
                    messages.append({"role": "user", "content": reflection_msg})
                    continue
                else:
                    print("✅ [Agent] 工具执行成功，任务完成！")
                    guide = _generate_guide(user_input, observation)
                    await _extract_and_save_preferences(messages)
                    return f"{observation}\n\n{guide}"
            else:
                print(f"❌ [Agent] 未知工具：{tool_name}")
                messages.append({"role": "assistant", "content": output})
                messages.append({"role": "user", "content": f"错误：未知工具 {tool_name}"})
        except json.JSONDecodeError as e:
            print(f"❌ [Agent] JSON解析失败：{e}")
            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": f"参数 JSON 格式错误，请重新输出。错误：{e}"})
        except Exception as e:
            print(f"❌ [Agent] 执行异常：{e}")
            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": f"执行失败：{e}，请重试。"})
    return "⏰ 任务执行超时，请尝试简化需求。"


# ===== 5. 主程序 =====
async def main():
    print("=" * 50)
    print("🧠  智能生活助手 L3+（带长期记忆）已启动")
    prefs = load_preferences()
    if prefs:
        print("📋 已加载用户偏好：")
        for key, value in prefs.items():
            print(f"   - {key}: {value}")
    else:
        print("📋 暂无用户偏好，我会在对话中学习")
    print("💡 提示：输入 '退出' 结束对话")
    print("=" * 50)
    while True:
        user_input = input("\n你：")
        if user_input in ["退出", "exit", "quit"]:
            print("👋 再见！")
            break
        result = await ask_agent(user_input)
        print(f"\n📝 [最终答案]\n{result}\n")


if __name__ == "__main__":
    asyncio.run(main())
