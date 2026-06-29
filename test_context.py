import asyncio
from life_mate_agent import lifemate_agent

async def test():
    conversation_history = []
    
    print('=== 第1轮对话：查询北京天气 ===')
    result1 = await lifemate_agent('北京今天天气怎么样？', conversation_history=conversation_history)
    print(f'回答：{result1}')
    conversation_history.append({'role': 'user', 'content': '北京今天天气怎么样？'})
    conversation_history.append({'role': 'assistant', 'content': result1})
    
    print('\n=== 第2轮对话：穿衣建议（应该记住北京） ===')
    result2 = await lifemate_agent('今天应该穿什么衣服？', conversation_history=conversation_history)
    print(f'回答：{result2}')

asyncio.run(test())