import sys
sys.path.insert(0, '.')

try:
    from tools import get_weather, get_forecast, query_tasks, add_task, complete_task, display_notification, get_clothing_advice
    print("✅ 工具导入成功")
except Exception as e:
    print(f"❌ 工具导入失败: {e}")
    import traceback
    traceback.print_exc()

try:
    from user_profile import hybrid_retrieval, extract_and_save_profile
    print("✅ 用户画像模块导入成功")
except Exception as e:
    print(f"❌ 用户画像模块导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n所有模块导入测试完成！")