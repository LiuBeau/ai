"""
LifeMate Agent - 真正的智能体版本

【核心改进】
1. 规划能力：能够分析用户意图，制定执行计划
2. 主动性：能够主动提供建议
3. 持续性：能够跟踪任务状态
4. 多轮对话：能够进行复杂交互
"""

import asyncio
import json
import re
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MAX_THINKING_STEPS, MAX_HISTORY_LENGTH
from user_profile import hybrid_retrieval
from tools import (
    get_weather, get_forecast,
    query_tasks, add_task, complete_task,
    display_notification,
    get_clothing_advice
)

async def call_llm(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            }
            data = json.dumps({
                "model": "glm-4-flash",
                "messages": messages,
                "temperature": 0.3
            }).encode('utf-8')
            
            req = urllib.request.Request(
                f"{DEEPSEEK_BASE_URL}chat/completions",
                data=data,
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result["choices"][0]["message"]["content"]
        except TimeoutError:
            print(f"⚠️ LLM超时，第 {attempt+1}/{max_retries} 次重试...")
            continue
        except Exception as e:
            return f"⚠️ LLM调用失败：{e}"
    return "⚠️ LLM调用超时，已重试多次"


async def web_search(query: str) -> str:
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('Abstract'):
                return data['Abstract']
            elif data.get('RelatedTopics'):
                return data['RelatedTopics'][0].get('Text', '未找到相关信息')
            else:
                return f"🔍 关于'{query}'的搜索无结果。"
    except Exception as e:
        return f"⚠️ 联网搜索失败：{e}"

async def show_profile() -> str:
    profile = hybrid_retrieval("")
    return profile["summary"]

async def update_profile(key: str, value: str) -> str:
    from user_profile import set_basic_info, set_preference
    
    category_keywords = {
        "name": ("basic", "name"),
        "年龄": ("basic", "age"),
        "地区": ("basic", "location"),
        "口味": ("food", "口味"),
        "风格": ("clothing", "风格"),
        "怕冷": ("weather", "怕冷"),
        "怕热": ("weather", "怕热"),
    }
    
    for kw, (cat, pref_key) in category_keywords.items():
        if kw in key or kw in value:
            if cat == "basic":
                set_basic_info(pref_key, value)
            else:
                set_preference(cat, pref_key, value)
            return f"✅ 已更新画像：{key} = {value}"
    
    set_preference("other", key, value)
    return f"✅ 已更新画像：{key} = {value}"

TOOLS = {
    "get_weather": {"func": get_weather, "description": "获取实时天气", "params": {"city": "城市名称"}},
    "get_forecast": {"func": get_forecast, "description": "获取天气预报", "params": {"city": "城市名称", "days": "天数"}},
    "query_tasks": {"func": query_tasks, "description": "查询日程", "params": {"date": "日期"}},
    "add_task": {"func": add_task, "description": "添加任务", "params": {"task": "任务内容", "date": "日期"}},
    "complete_task": {"func": complete_task, "description": "完成任务", "params": {"task": "任务内容", "date": "日期"}},
    "get_clothing_advice": {"func": get_clothing_advice, "description": "穿衣建议", "params": {"city": "城市", "date": "日期"}},
    "show_profile": {"func": show_profile, "description": "显示用户画像", "params": {}},
    "update_profile": {"func": update_profile, "description": "更新用户画像", "params": {"key": "键", "value": "值"}},
    "display_notification": {"func": display_notification, "description": "显示通知", "params": {"title": "标题", "content": "内容"}},
    "web_search": {"func": web_search, "description": "联网搜索", "params": {"query": "关键词"}}
}

class PlanningAgent:
    """规划型智能体"""
    
    def __init__(self):
        self.current_plan = []
        self.plan_results = []
        self.session_context = {}
        self.user_profile = {}
    
    async def analyze_intent(self, user_input):
        """分析用户意图，提取目标和子任务"""
        prompt = f"""
分析用户输入："{user_input}"

请提取：
1. 用户的主要目标
2. 需要完成的子任务列表
3. 需要调用的工具和参数

输出格式（JSON）：
{{
  "goal": "用户的主要目标",
  "tasks": [
    {{"tool": "工具名", "params": {{"参数": "值"}}, "reason": "为什么需要这个任务"}}
  ],
  "proactive_suggestions": ["主动建议列表"]
}}
"""
        messages = [{"role": "system", "content": "你是一个智能任务规划器。"}, {"role": "user", "content": prompt}]
        result = await call_llm(messages)
        print(f"📝 [调试] LLM返回：{result[:200]}...")
        
        try:
            return json.loads(result)
        except Exception as e:
            print(f"⚠️ [调试] JSON解析失败：{e}")
            return {
                "goal": user_input,
                "tasks": [],
                "proactive_suggestions": []
            }
    
    async def execute_plan(self, plan):
        """执行计划"""
        results = []
        
        for task in plan["tasks"]:
            tool_name = task["tool"]
            params = task["params"]
            
            if tool_name in TOOLS:
                print(f"🔧 执行任务：{tool_name}，参数：{params}")
                result = await TOOLS[tool_name]["func"](**params)
                results.append({"task": task, "result": result})
                print(f"📊 结果：{result[:50]}...")
            else:
                results.append({"task": task, "result": f"工具 {tool_name} 不存在"})
        
        return results
    
    async def summarize(self, plan, results):
        """汇总结果"""
        summary_prompt = f"""
用户目标：{plan["goal"]}

执行结果：
{json.dumps(results, ensure_ascii=False)}

请用自然语言总结给用户，并提供主动建议。
"""
        messages = [{"role": "system", "content": "你是一个智能总结助手。"}, {"role": "user", "content": summary_prompt}]
        return await call_llm(messages)

async def lifemate_agent(user_input: str, conversation_history: list = None):
    """真正的智能体模式"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    profile = hybrid_retrieval(user_input)
    profile_summary = profile["summary"]
    
    print(f"\n🤖 [LifeMate] 开始分析意图...")
    
    planner = PlanningAgent()
    intent = await planner.analyze_intent(user_input)
    
    print(f"🎯 用户目标：{intent['goal']}")
    print(f"� 子任务：{intent['tasks']}")
    
    if intent["tasks"]:
        results = await planner.execute_plan(intent)
        summary = await planner.summarize(intent, results)
        
        response = f"🎯 {intent['goal']}\n\n"
        for i, res in enumerate(results):
            response += f"✅ {res['task']['reason']}\n   {res['result']}\n\n"
        response += f"💡 {summary}"
        
        if intent.get("proactive_suggestions"):
            response += "\n\n📌 额外建议：\n"
            for suggestion in intent["proactive_suggestions"]:
                response += f"  • {suggestion}\n"
    else:
        response = await call_llm([
            {"role": "system", "content": f"你是 LifeMate，用户画像：{profile_summary}"},
            {"role": "user", "content": user_input}
        ])
    
    return response

async def chat_loop():
    print("=" * 60)
    print("🎯 LifeMate - 智能生活助手（规划版）")
    print("=" * 60)
    print("我可以帮您：")
    print("  • 分析您的需求，制定执行计划")
    print("  • 自动完成多个相关任务")
    print("  • 提供个性化建议")
    print("输入 '退出' 结束对话")
    print("=" * 60 + "\n")
    
    conversation_history = []
    
    while True:
        user_input = input("👤 您：").strip()
        
        if user_input in ["退出", "exit", "quit"]:
            print("👋 再见！期待下次为您服务。")
            break
        
        if not user_input:
            print("⚠️ 请输入内容")
            continue
        
        result = await lifemate_agent(user_input)
        
        print(f"\n🤖 LifeMate：\n{result}\n")
        
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": result})
        
        if len(conversation_history) > MAX_HISTORY_LENGTH:
            conversation_history = conversation_history[-MAX_HISTORY_LENGTH:]

if __name__ == "__main__":
    asyncio.run(chat_loop())