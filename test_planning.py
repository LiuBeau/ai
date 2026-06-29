"""
LifeMate Agent - 旅游计划测试版

使用模拟数据测试规划功能
"""

import asyncio
import json
from datetime import datetime

class MockPlanningAgent:
    """模拟规划型智能体"""
    
    async def analyze_intent(self, user_input):
        """分析用户意图"""
        print(f"🎯 用户输入：{user_input}")
        
        if '旅游' in user_input or '旅行' in user_input:
            return {
                "goal": "安排旅游计划",
                "tasks": [
                    {"tool": "get_forecast", "params": {"city": "杭州", "days": 2}, "reason": "查询杭州周末天气"},
                    {"tool": "get_clothing_advice", "params": {"city": "杭州"}, "reason": "获取穿衣建议"},
                    {"tool": "web_search", "params": {"query": "杭州周末旅游攻略"}, "reason": "搜索旅游攻略"},
                ],
                "proactive_suggestions": ["需要帮您查机票吗？", "需要帮您订酒店吗？"]
            }
        elif '天气' in user_input:
            return {
                "goal": "查询天气",
                "tasks": [
                    {"tool": "get_weather", "params": {"city": "北京"}, "reason": "查询实时天气"},
                ],
                "proactive_suggestions": []
            }
        else:
            return {
                "goal": user_input,
                "tasks": [],
                "proactive_suggestions": []
            }
    
    async def execute_plan(self, plan):
        """执行计划（模拟）"""
        results = []
        
        mock_data = {
            "get_weather": "北京实时天气：晴天，温度28°C",
            "get_forecast": "杭州周末天气预报：周六晴天，25-32°C；周日多云，24-30°C",
            "get_clothing_advice": "杭州周末天气适宜，建议穿薄外套+长裤，带防晒用品",
            "web_search": "杭州周末旅游攻略：西湖游船、灵隐寺祈福、龙井茶园品茶、湖滨银泰购物",
        }
        
        for task in plan["tasks"]:
            tool_name = task["tool"]
            print(f"🔧 执行任务：{tool_name}，参数：{task['params']}")
            result = mock_data.get(tool_name, f"模拟数据：{tool_name}")
            results.append({"task": task, "result": result})
            print(f"📊 结果：{result}")
        
        return results
    
    async def summarize(self, plan, results):
        """汇总结果"""
        summary = f"已为您完成{plan['goal']}：\n"
        for res in results:
            summary += f"• {res['task']['reason']}：{res['result']}\n"
        return summary

async def lifemate_agent(user_input: str):
    """智能体主入口"""
    print(f"\n🤖 [LifeMate] 开始分析意图...")
    
    planner = MockPlanningAgent()
    intent = await planner.analyze_intent(user_input)
    
    print(f"\n📋 分析结果：")
    print(f"   目标：{intent['goal']}")
    print(f"   任务：{[t['tool'] for t in intent['tasks']]}")
    
    if intent["tasks"]:
        print(f"\n🚀 开始执行计划...")
        results = await planner.execute_plan(intent)
        summary = await planner.summarize(intent, results)
        
        response = f"\n🎯 {intent['goal']}\n\n"
        for res in results:
            response += f"✅ {res['task']['reason']}\n   {res['result']}\n\n"
        response += f"💡 {summary}"
        
        if intent.get("proactive_suggestions"):
            response += "\n\n📌 额外建议：\n"
            for suggestion in intent["proactive_suggestions"]:
                response += f"  • {suggestion}\n"
    else:
        response = f"🤔 我不太理解您的需求，请说得更具体一些。\n\n可用功能：\n• 查询天气\n• 穿衣建议\n• 安排旅游计划\n• 管理日程"
    
    return response

async def chat_loop():
    print("=" * 60)
    print("🎯 LifeMate - 智能生活助手（规划测试版）")
    print("=" * 60)
    print("我可以帮您：")
    print("  • 分析您的需求，制定执行计划")
    print("  • 自动完成多个相关任务")
    print("  • 提供个性化建议")
    print("输入 '退出' 结束对话")
    print("=" * 60 + "\n")
    
    while True:
        user_input = input("👤 您：").strip()
        
        if user_input in ["退出", "exit", "quit"]:
            print("👋 再见！")
            break
        
        if not user_input:
            print("⚠️ 请输入内容")
            continue
        
        result = await lifemate_agent(user_input)
        print(f"\n🤖 LifeMate：\n{result}\n")

if __name__ == "__main__":
    asyncio.run(chat_loop())