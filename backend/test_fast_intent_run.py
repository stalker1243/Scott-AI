import sys
sys.path.insert(0, 'backend')
from main import scott_ai
import asyncio

async def run_tests():
    queries = [
        'Расскажи мне что-нибудь о Марсе',
        'Найди информацию про Python',
        'Какая сегодня погода в Москве',
        'Привет, как дела?'
    ]
    for q in queries:
        print('===', q)
        result = await scott_ai.process_command(q)
        print(result)

asyncio.run(run_tests())
