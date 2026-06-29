import asyncio
from life_mate_agent import lifemate_agent

async def test():
    conversation_history = [
        {'role': 'user', 'content': '北京今天天气怎么样？'},
        {'role': 'assistant', 'content': '北京现在正在下大雨，温度为23.9°C。'}
    ]
    
    print('=== 测试：穿衣建议（应该记住北京） ===')
    result = await lifemate_agent('今天应该穿什么衣服？', conversation_history=conversation_history)
    print(f'回答：{result}')

asyncio.run(test())