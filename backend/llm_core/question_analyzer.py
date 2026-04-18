"""
Анализатор вопросов - определяет тип и сложность вопроса.
"""
import re
from typing import Dict, Literal
from dataclasses import dataclass


@dataclass
class QuestionAnalysis:
    """Анализ вопроса."""
    category: Literal["simple", "math", "science", "general"]
    difficulty: Literal["easy", "medium", "hard"]
    requires_calculation: bool = False
    requires_reasoning: bool = False


class QuestionAnalyzer:
    """Анализатор вопросов для определения типа и сложности."""

    # Паттерны для математических вопросов
    MATH_PATTERNS = [
        r'\d+\s*[+\-*/]\s*\d+',  # 2+2, 10-5
        r'сколько\s+(?:будет|равно)',  # сколько будет
        r'вычисли|посчитай|реши',  # вычисли, посчитай
        r'процент|процентов',  # процент
        r'квадрат|корень|степень',  # математические операции
        r'уравнение|формула',  # уравнение
    ]

    # Паттерны для научных вопросов
    SCIENCE_PATTERNS = [
        r'почему|как работает|как устроен',  # почему, как работает
        r'физика|химия|биология|астрономия',  # научные дисциплины
        r'закон|теория|гипотеза',  # научные концепции
        r'молекула|атом|электрон',  # научные термины
        r'скорость света|гравитация|энергия',  # научные понятия
    ]

    # Паттерны для простых вопросов
    SIMPLE_PATTERNS = [
        r'привет|здравствуй|как дела',  # приветствие
        r'что ты|кто ты',  # о себе
        r'время|который час',  # время
        r'спасибо|пожалуйста',  # вежливость
    ]

    def analyze(self, question: str) -> QuestionAnalysis:
        """
        Анализирует вопрос и определяет его категорию и сложность.
        
        Args:
            question: Текст вопроса
            
        Returns:
            QuestionAnalysis с информацией о вопросе
        """
        question_lower = question.lower().strip()
        
        # Проверка на математику
        is_math = any(re.search(pattern, question_lower) for pattern in self.MATH_PATTERNS)
        
        # Проверка на науку
        is_science = any(re.search(pattern, question_lower) for pattern in self.SCIENCE_PATTERNS)
        
        # Проверка на простые вопросы
        is_simple = any(re.search(pattern, question_lower) for pattern in self.SIMPLE_PATTERNS)
        
        # Определение категории
        if is_math:
            category = "math"
        elif is_science:
            category = "science"
        elif is_simple:
            category = "simple"
        else:
            category = "general"
        
        # Определение сложности
        difficulty = self._determine_difficulty(question_lower, category, is_math)
        
        # Требует ли расчётов
        requires_calculation = is_math and any(
            re.search(r'\d+', word) for word in question_lower.split()
        )
        
        # Требует ли рассуждений
        requires_reasoning = (
            len(question.split()) > 10 or  # Длинный вопрос
            '?' in question or  # Вопросительное предложение
            any(word in question_lower for word in ['почему', 'как', 'объясни', 'расскажи'])
        )
        
        return QuestionAnalysis(
            category=category,
            difficulty=difficulty,
            requires_calculation=requires_calculation,
            requires_reasoning=requires_reasoning
        )
    
    def _determine_difficulty(self, question: str, category: str, is_math: bool) -> Literal["easy", "medium", "hard"]:
        """Определяет сложность вопроса."""
        words_count = len(question.split())
        
        if category == "simple":
            return "easy"
        
        if is_math:
            # Простая арифметика
            if re.search(r'\d+\s*[+\-]\s*\d+', question):
                return "easy"
            # Средняя (умножение, деление, проценты)
            elif re.search(r'\d+\s*[*/]', question) or 'процент' in question:
                return "medium"
            # Сложная (уравнения, формулы)
            else:
                return "hard"
        
        # Для общих вопросов
        if words_count < 5:
            return "easy"
        elif words_count < 15:
            return "medium"
        else:
            return "hard"

