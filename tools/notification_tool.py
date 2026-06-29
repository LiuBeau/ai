"""
通知服务工具
提供桌面通知功能
"""


async def display_notification(title: str, content: str) -> str:
    """在屏幕上显示通知信息，用于向用户展示重要提醒"""
    try:
        from win11toast import toast
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