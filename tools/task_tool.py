"""
日程服务工具
提供待办事项的查询、添加和完成功能
"""

import json
from datetime import datetime


async def query_tasks(date: str = None) -> str:
    """查询指定日期的待办事项日程"""
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
    """添加一条待办事项到指定日期"""
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
    """标记一条待办事项为已完成（删除）"""
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