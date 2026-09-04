#!/usr/bin/env python3
"""
Тестирование полной цепи голосового ввода:
1. Распознавание речи (speech_to_text)
2. Выполнение команды/вопроса (ask/command)
3. Озвучивание ответа (speak)
"""

import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000"

def test_backend_health():
    """Проверить доступность backend"""
    print("\n📊 Проверка backend...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Backend доступен: {data.get('message')}")
            print(f"   Версия: {data.get('version')}, AI: {data.get('ai_name')}")
            return True
        else:
            print(f"❌ Backend ошибка: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Backend недоступен: {e}")
        return False


def test_ask_endpoint(question):
    """Протестировать endpoint /ask"""
    print(f"\n❓ Отправка вопроса: '{question}'")
    try:
        response = requests.post(
            f"{BASE_URL}/ask",
            json={"question": question},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get("data", {}).get("answer", "Нет ответа")
            print(f"✅ Ответ получен: {answer[:100]}...")
            return answer
        else:
            print(f"❌ Ошибка /ask: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Ошибка подключения к /ask: {e}")
        return None


def test_speak_endpoint(text):
    """Протестировать endpoint /speak"""
    print(f"\n🔊 Озвучивание: '{text[:50]}...'")
    try:
        response = requests.post(
            f"{BASE_URL}/speak",
            data={"text": text},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Текст озвучен успешно")
                return True
            else:
                print(f"⚠️ Озвучивание ошибка: {data.get('message')}")
                return False
        else:
            print(f"❌ Ошибка /speak: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка подключения к /speak: {e}")
        return False


def test_command_endpoint(command):
    """Протестировать endpoint /command"""
    print(f"\n⚙️ Выполнение команды: '{command}'")
    try:
        response = requests.post(
            f"{BASE_URL}/command",
            json={"command": command},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {}).get("result", "Команда выполнена")
            print(f"✅ Команда выполнена: {result}")
            return True
        else:
            print(f"⚠️ Команда не выполнена: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка подключения к /command: {e}")
        return False


def run_full_test():
    """Запустить полный тест цепи"""
    print("=" * 60)
    print("🎤 ТЕСТИРОВАНИЕ ПОЛНОЙ ЦЕПИ ГОЛОСОВОГО ВВОДА")
    print("=" * 60)
    
    # Проверить backend
    if not test_backend_health():
        print("\n❌ Backend недоступен. Нельзя продолжить тестирование.")
        return False
    
    # Тест 1: Простой вопрос
    print("\n\n🔷 ТЕСТ 1: Простой вопрос")
    print("-" * 40)
    answer = test_ask_endpoint("Привет, как дела?")
    if answer:
        print(f"   Полный ответ: {answer}")
        # Озвучить ответ
        test_speak_endpoint(answer)
    
    # Тест 2: Команда открыть программу
    print("\n\n🔷 ТЕСТ 2: Команда открыть программу")
    print("-" * 40)
    test_command_endpoint("открой notepad")
    time.sleep(2)
    
    # Тест 3: Вопрос про погоду
    print("\n\n🔷 ТЕСТ 3: Информационный вопрос")
    print("-" * 40)
    answer = test_ask_endpoint("Какая сегодня погода?")
    if answer:
        test_speak_endpoint(answer)
    
    # Тест 4: Поиск информации
    print("\n\n🔷 ТЕСТ 4: Поиск информации")
    print("-" * 40)
    answer = test_ask_endpoint("Найди информацию про Python")
    if answer:
        print(f"   Ответ длина: {len(answer)} символов")
        test_speak_endpoint(answer[:200])  # Озвучить первые 200 символов
    
    print("\n" + "=" * 60)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        run_full_test()
    except KeyboardInterrupt:
        print("\n⚠️ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        sys.exit(1)
