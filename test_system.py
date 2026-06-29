import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_user_profile():
    """测试用户画像模块"""
    print("\n" + "="*60)
    print("📋 测试 1: 用户画像模块")
    print("="*60)
    
    from user_profile import (
        set_basic_info, get_basic_info, get_all_basic_info,
        set_preference, get_preference, get_all_preferences,
        set_habit, get_habit,
        set_recent_context, get_recent_context,
        hybrid_retrieval, consolidate_memories, apply_forgetting_curve,
        update_preference_confidence
    )
    
    print("\n1.1 基本信息 CRUD...")
    set_basic_info("name", "测试用户")
    set_basic_info("age", "30")
    set_basic_info("location", "北京")
    assert get_basic_info("name") == "测试用户", "基本信息设置失败"
    assert get_all_basic_info()["location"] == "北京", "获取所有基本信息失败"
    print("✅ 基本信息 CRUD 测试通过")
    
    print("\n1.2 偏好设置...")
    set_preference("weather", "怕冷", "是", confidence=0.9)
    set_preference("clothing", "风格", "休闲", confidence=0.8)
    set_preference("food", "口味", "辣", confidence=1.0)
    assert get_preference("weather", "怕冷") == "是", "偏好设置失败"
    print("✅ 偏好设置测试通过")
    
    print("\n1.3 习惯设置...")
    set_habit("wake_up_time", "7:30")
    assert get_habit("wake_up_time") == "7:30", "习惯设置失败"
    print("✅ 习惯设置测试通过")
    
    print("\n1.4 短期上下文...")
    set_recent_context("current_activity", "正在测试系统", expire_hours=1)
    assert get_recent_context("current_activity") == "正在测试系统", "短期上下文设置失败"
    print("✅ 短期上下文测试通过")
    
    print("\n1.5 混合检索...")
    result = hybrid_retrieval("穿衣")
    assert "summary" in result, "混合检索缺少summary"
    assert "structured" in result, "混合检索缺少structured"
    assert "semantic" in result, "混合检索缺少semantic"
    assert "recent" in result, "混合检索缺少recent"
    print("📊 画像摘要:")
    print(result["summary"])
    print("✅ 混合检索测试通过")
    
    print("\n1.6 置信度更新...")
    update_preference_confidence("food", "口味", 0.1)
    prefs = get_all_preferences()
    food_pref = next(p for p in prefs if p.category == "food" and p.key == "口味")
    assert food_pref.confidence >= 1.0, "置信度更新失败"
    print("✅ 置信度更新测试通过")
    
    print("\n1.7 遗忘曲线...")
    apply_forgetting_curve()
    print("✅ 遗忘曲线测试通过")
    
    print("\n1.8 记忆巩固...")
    get_recent_context("current_activity")
    get_recent_context("current_activity")
    consolidate_memories()
    print("✅ 记忆巩固测试通过")
    
    print("\n" + "="*60)
    print("🎉 用户画像模块全部测试通过！")
    print("="*60)

async def test_tools():
    """测试各工具函数"""
    print("\n" + "="*60)
    print("🔧 测试 2: 工具函数")
    print("="*60)
    
    print("\n2.1 天气工具...")
    from tools.weather_tool import get_weather, get_forecast
    weather = await get_weather("北京")
    assert "北京" in weather, "天气查询失败"
    print(f"📊 {weather}")
    forecast = await get_forecast("上海", days=2)
    assert "上海" in forecast, "天气预报查询失败"
    print(f"📊 {forecast}")
    print("✅ 天气工具测试通过")
    
    print("\n2.2 日程工具...")
    from tools.task_tool import query_tasks, add_task, complete_task
    await add_task("测试任务", "2026-06-29")
    tasks = await query_tasks("2026-06-29")
    assert "测试任务" in tasks, "日程查询失败"
    print(f"📊 {tasks}")
    completed = await complete_task("测试任务", "2026-06-29")
    assert "已完成" in completed, "任务完成失败"
    print(f"📊 {completed}")
    print("✅ 日程工具测试通过")
    
    print("\n2.3 穿衣建议工具...")
    from tools.clothing_tool import get_clothing_advice
    advice = await get_clothing_advice("北京")
    assert "建议" in advice, "穿衣建议失败"
    print(f"📊 {advice}")
    print("✅ 穿衣建议工具测试通过")
    
    print("\n2.4 通知工具...")
    from tools.notification_tool import display_notification
    notification = await display_notification("测试通知", "这是一条测试通知")
    assert "通知" in notification, "通知工具失败"
    print(f"📊 {notification}")
    print("✅ 通知工具测试通过")
    
    print("\n" + "="*60)
    print("🎉 工具函数全部测试通过！")
    print("="*60)

async def test_agent():
    """测试主Agent"""
    print("\n" + "="*60)
    print("🤖 测试 3: 主 Agent")
    print("="*60)
    
    from life_mate_agent import lifemate_agent
    
    print("\n3.1 测试天气查询...")
    result = await lifemate_agent("北京今天天气怎么样？", max_steps=3)
    assert "天气" in result or "°C" in result, "天气查询失败"
    print(f"📊 {result}")
    print("✅ 天气查询测试通过")
    
    print("\n3.2 测试穿衣建议...")
    result = await lifemate_agent("北京今天穿什么？", max_steps=3)
    assert "建议" in result or "穿" in result, "穿衣建议失败"
    print(f"📊 {result}")
    print("✅ 穿衣建议测试通过")
    
    print("\n3.3 测试用户画像更新...")
    result = await lifemate_agent("我叫小明，今年25岁，住在上海", max_steps=2)
    print(f"📊 {result}")
    print("✅ 用户画像更新测试完成")
    
    print("\n3.4 测试多轮对话...")
    history = [
        {"role": "user", "content": "我叫小明"},
        {"role": "assistant", "content": "你好小明！很高兴认识你。"},
        {"role": "user", "content": "我喜欢吃辣"},
        {"role": "assistant", "content": "好的，我记下了，你喜欢吃辣。"},
    ]
    result = await lifemate_agent("上海明天天气怎么样？适合吃火锅吗？", max_steps=3, conversation_history=history)
    print(f"📊 {result}")
    print("✅ 多轮对话测试完成")
    
    print("\n" + "="*60)
    print("🎉 主 Agent 测试完成！")
    print("="*60)

async def test_config():
    """测试配置加载"""
    print("\n" + "="*60)
    print("⚙️ 测试 4: 配置加载")
    print("="*60)
    
    from config import (
        DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
        MAX_THINKING_STEPS, MAX_HISTORY_LENGTH,
        DB_PATH, CHROMA_PATH
    )
    
    print(f"📊 API Key: {'已配置' if DEEPSEEK_API_KEY else '未配置'}")
    print(f"📊 Base URL: {DEEPSEEK_BASE_URL}")
    print(f"📊 最大思考步数: {MAX_THINKING_STEPS}")
    print(f"📊 最大历史长度: {MAX_HISTORY_LENGTH}")
    print(f"📊 数据库路径: {DB_PATH}")
    print(f"📊 向量库路径: {CHROMA_PATH}")
    
    assert DEEPSEEK_API_KEY, "API Key 未配置"
    assert MAX_THINKING_STEPS > 0, "最大思考步数配置错误"
    assert MAX_HISTORY_LENGTH > 0, "最大历史长度配置错误"
    
    print("✅ 配置加载测试通过")
    
    print("\n" + "="*60)
    print("🎉 配置测试全部通过！")
    print("="*60)

async def main():
    """运行所有测试"""
    print("🚀 LifeMate 系统测试开始")
    print("="*60)
    
    try:
        await test_config()
        await test_user_profile()
        await test_tools()
        await test_agent()
        
        print("\n" + "="*60)
        print("🏆 所有测试全部通过！")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())