"""
Тест системы ответов на вопросы разной сложности.
Проверяет работу с простыми, средними и сложными вопросами (математика, наука).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from llm_core import LlmEngine, LlmConfig
from llm_core.question_analyzer import QuestionAnalyzer

def test_question_analyzer():
    """Тест анализатора вопросов."""
    print("🔍 Тест анализатора вопросов")
    print("=" * 50)
    
    analyzer = QuestionAnalyzer()
    
    test_questions = [
        ("Привет, как дела?", "simple", "easy"),
        ("Сколько будет 2+2?", "math", "easy"),
        ("Реши уравнение: 5x + 10 = 25", "math", "hard"),
        ("Почему небо голубое?", "science", "medium"),
        ("Как работает гравитация?", "science", "hard"),
        ("Что такое молекула?", "science", "medium"),
        ("Расскажи о квантовой физике", "science", "hard"),
    ]
    
    for question, expected_category, expected_difficulty in test_questions:
        analysis = analyzer.analyze(question)
        status = "✅" if analysis.category == expected_category and analysis.difficulty == expected_difficulty else "⚠️"
        print(f"{status} '{question}'")
        print(f"   Категория: {analysis.category} (ожидалось: {expected_category})")
        print(f"   Сложность: {analysis.difficulty} (ожидалось: {expected_difficulty})")
        print(f"   Требует расчётов: {analysis.requires_calculation}")
        print()

def test_llm_answers():
    """Тест ответов LLM на вопросы разной сложности."""
    print("\n🤖 Тест ответов LLM")
    print("=" * 50)
    
    # Настройка Ollama
    config = LlmConfig(provider="ollama", model="qwen2.5:7b")
    llm = LlmEngine(config=config)
    
    # Простые вопросы
    print("\n📝 ПРОСТЫЕ ВОПРОСЫ:")
    print("-" * 50)
    simple_questions = [
        "Привет, как дела?",
        "Что ты умеешь?",
        "Который час?",
    ]
    
    for question in simple_questions:
        print(f"\n❓ {question}")
        answer = llm.answer(question)
        print(f"💬 {answer[:200]}...")
    
    # Средние вопросы (математика)
    print("\n\n🔢 СРЕДНИЕ ВОПРОСЫ (математика):")
    print("-" * 50)
    medium_math = [
        "Сколько будет 15 + 27?",
        "Вычисли 100 * 5",
        "Сколько процентов от 200 составляет 50?",
    ]
    
    for question in medium_math:
        print(f"\n❓ {question}")
        answer = llm.answer(question)
        print(f"💬 {answer[:200]}...")
    
    # Сложные вопросы (наука)
    print("\n\n🔬 СЛОЖНЫЕ ВОПРОСЫ (наука):")
    print("-" * 50)
    hard_science = [
        "Почему небо голубое?",
        "Как работает гравитация?",
        "Что такое фотосинтез?",
    ]
    
    for question in hard_science:
        print(f"\n❓ {question}")
        print("⏳ Ожидание ответа (может занять время)...")
        answer = llm.answer(question)
        print(f"💬 {answer[:300]}...")
    
    # Сложные математические вопросы
    print("\n\n📐 СЛОЖНЫЕ ВОПРОСЫ (математика):")
    print("-" * 50)
    hard_math = [
        "Реши уравнение: 2x + 5 = 15",
        "Что такое производная функции?",
    ]
    
    for question in hard_math:
        print(f"\n❓ {question}")
        print("⏳ Ожидание ответа...")
        answer = llm.answer(question)
        print(f"💬 {answer[:300]}...")

def main():
    print("🚀 Тест системы ответов на вопросы")
    print("=" * 50)
    
    # Тест анализатора
    test_question_analyzer()
    
    # Тест LLM
    try:
        test_llm_answers()
    except Exception as e:
        print(f"\n❌ Ошибка при тестировании LLM: {e}")
        print("💡 Убедись, что Ollama запущен: ollama run qwen2.5:7b")
    
    print("\n" + "=" * 50)
    print("✅ Тестирование завершено!")
    print("=" * 50)

if __name__ == "__main__":
    main()

