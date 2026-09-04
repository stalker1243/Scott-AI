"""
База знаний и память JARVIS
Сохранение и восстановление информации из диалогов
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests


class KnowledgeBase:
    """База знаний и память системы"""
    
    def __init__(self, db_file: str = "jarvis_memory.json"):
        self.db_file = Path(db_file)
        self.memory = self.load_memory()
        self.conversation_history = []
        
        print(f"✅ База знаний инициализирована ({len(self.memory)} записей)")
    
    def load_memory(self) -> Dict:
        """Загрузить память из файла"""
        try:
            if self.db_file.exists():
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Не смог загрузить память: {e}")
        
        return {}
    
    def save_memory(self):
        """Сохранить память в файл"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка при сохранении памяти: {e}")
    
    def add_memory(self, key: str, value: str, category: str = "general"):
        """Добавить в память"""
        self.memory[key] = {
            "value": value,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "access_count": 0
        }
        self.save_memory()
    
    def recall(self, key: str) -> Optional[str]:
        """Вспомнить из памяти"""
        if key in self.memory:
            self.memory[key]["access_count"] += 1
            self.save_memory()
            return self.memory[key]["value"]
        return None
    
    def search_memory(self, query: str) -> Dict:
        """Поиск по памяти"""
        results = {}
        query_lower = query.lower()
        
        for key, data in self.memory.items():
            if query_lower in key.lower() or query_lower in data.get("value", "").lower():
                results[key] = data
        
        return results
    
    def add_conversation(self, user_input: str, jarvis_response: str):
        """Добавить в историю разговоров"""
        self.conversation_history.append({
            "user": user_input,
            "jarvis": jarvis_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Сохранить последние 100 диалогов
        if len(self.conversation_history) > 100:
            self.conversation_history.pop(0)
    
    def get_conversation_context(self, last_n: int = 5) -> List[Dict]:
        """Получить контекст последних разговоров"""
        return self.conversation_history[-last_n:]
    
    def learn_from_question(self, question: str, answer: str):
        """Выучить новый факт"""
        self.add_memory(
            question.lower()[:50],
            answer,
            category="learned"
        )
    
    def query_ai(self, question: str) -> str:
        """
        Спросить AI (Ollama локально или фолбек на GPT)
        """
        try:
            print(f"🧠 Спрашиваю AI: {question}")
            
            # Попробовать Ollama
            try:
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "neural-chat",
                        "prompt": question,
                        "stream": False
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response.json().get("response", "").strip()
            except:
                print("⚠️ Ollama не доступна, используя простые ответы")
            
            # Фолбек - простые ответы
            return self.simple_response(question)
            
        except Exception as e:
            print(f"❌ Ошибка запроса AI: {e}")
            return "I'm sorry, I could not process that request."
    
    def simple_response(self, question: str) -> str:
        """Простой ответ без AI"""
        q = question.lower()
        
        responses = {
            "who": "I am JARVIS, your personal AI assistant.",
            "what": "I am designed to help you with various tasks.",
            "how": "I work by processing your input and responding accordingly.",
            "hello": "Hello sir or madam. At your service.",
            "thank": "You are welcome.",
            "help": "I can help you with system commands, information, and general assistance.",
            "weather": "I do not have access to weather information at the moment.",
            "time": f"Current time is {datetime.now().strftime('%H:%M:%S')}.",
        }
        
        for key, response in responses.items():
            if key in q:
                return response

        if any(word in q for word in ['привет', 'hello', 'hi', 'здравствуй', 'как дела', 'как ты']):
            return "Привет! Я Scott. Я могу ответить на вопросы, помочь с командами и поддержать разговор."

        if q.endswith('?') or any(word in q for word in ['что', 'кто', 'как', 'где', 'когда', 'почему', 'зачем', 'сколько']):
            return "С удовольствием помогу. Сформулируй вопрос чуть точнее, и я отвечу прямо сейчас."

        return "Я вас слушаю. Скажите, что именно вы хотите сделать или узнать?"


# Глобальный экземпляр
_knowledge_base = None


def get_knowledge_base() -> KnowledgeBase:
    """Получить глобальный экземпляр KnowledgeBase"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base


if __name__ == "__main__":
    kb = get_knowledge_base()
    
    # Примеры
    kb.add_memory("user_name", "Sir", "personal")
    kb.learn_from_question("What is Python?", "Python is a programming language")
    
    print(kb.recall("user_name"))
    print(kb.query_ai("Hello, how are you?"))
