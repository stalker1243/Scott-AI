"""
Лучшие практики обработки ошибок для backend
"""

# ============================================================================
# PATTERN 1: Валидация входных данных
# ============================================================================

def validate_profile_name(name: str) -> tuple[bool, str]:
    """
    Валидация имени профиля
    
    Returns:
        (is_valid, error_message)
    """
    if not name:
        return False, "Имя профиля не может быть пустым"
    
    if not isinstance(name, str):
        return False, "Имя профиля должно быть строкой"
    
    if len(name.strip()) == 0:
        return False, "Имя профиля не может состоять только из пробелов"
    
    if len(name) > 100:
        return False, "Имя профиля слишком длинное (макс 100 символов)"
    
    if len(name) < 2:
        return False, "Имя профиля слишком короткое (мин 2 символа)"
    
    # Проверь на недопустимые символы
    forbidden_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in forbidden_chars:
        if char in name:
            return False, f"Имя профиля не может содержать символ '{char}'"
    
    return True, ""


def validate_coordinates(x: int, y: int) -> tuple[bool, str]:
    """Валидация координат"""
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False, "Координаты должны быть числами"
    
    if x < 0 or y < 0:
        return False, "Координаты не могут быть отрицательными"
    
    if x > 10000 or y > 10000:
        return False, "Координаты слишком большие"
    
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """Валидация email"""
    import re
    
    if not email or not isinstance(email, str):
        return False, "Email должен быть строкой"
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Неверный формат email"
    
    return True, ""


# ============================================================================
# PATTERN 2: Безопасная обработка файлов
# ============================================================================

import os
import json
from pathlib import Path


class SafeJSONStorage:
    """Безопасное сохранение и загрузка JSON"""
    
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.backup_path = Path(str(filepath) + ".backup")
    
    def save(self, data: dict) -> tuple[bool, str]:
        """
        Безопасное сохранение с backup
        """
        try:
            # 1. Проверь директорию
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # 2. Сохрани в temp файл
            temp_path = Path(str(self.filepath) + ".tmp")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 3. Если старый файл есть, создай backup
            if self.filepath.exists():
                try:
                    self.filepath.replace(self.backup_path)
                except Exception as e:
                    print(f"⚠️ Не смог создать backup: {e}")
            
            # 4. Переименуй temp в основной
            temp_path.replace(self.filepath)
            
            return True, f"Данные успешно сохранены: {self.filepath}"
        
        except Exception as e:
            # 5. Восстанови из backup если что-то пошло не так
            if self.backup_path.exists():
                try:
                    self.backup_path.replace(self.filepath)
                    return False, f"Ошибка сохранения, восстановлено из backup: {e}"
                except:
                    return False, f"Критическая ошибка сохранения: {e}"
            
            return False, f"Ошибка сохранения данных: {e}"
    
    def load(self) -> tuple[bool, dict, str]:
        """
        Безопасная загрузка с fallback
        """
        try:
            if not self.filepath.exists():
                return True, {}, "Файл не существует, возвращаю пустой словарь"
            
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return True, data, "Данные успешно загружены"
        
        except json.JSONDecodeError as e:
            # Попытайся загрузить backup
            if self.backup_path.exists():
                try:
                    with open(self.backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    return True, data, f"Основной файл поврежден, загруженные данные из backup: {e}"
                except:
                    pass
            
            return False, {}, f"Ошибка парсинга JSON: {e}"
        
        except Exception as e:
            return False, {}, f"Ошибка чтения файла: {e}"


# ============================================================================
# PATTERN 3: Логирование ошибок
# ============================================================================

import logging
from datetime import datetime


class ErrorLogger:
    """Логирование ошибок в файл"""
    
    def __init__(self, log_file: str = "errors.log"):
        self.log_file = log_file
        self.logger = logging.getLogger("scott_backend")
        
        # Конфигурация
        handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.ERROR)
    
    def log_error(self, component: str, operation: str, error: Exception, details: dict = None):
        """
        Логирование ошибки с контекстом
        """
        msg = f"[{component}] {operation} failed: {str(error)}"
        if details:
            msg += f" Details: {details}"
        
        self.logger.error(msg)
    
    def log_warning(self, component: str, message: str):
        """Логирование предупреждения"""
        self.logger.warning(f"[{component}] {message}")
    
    def log_info(self, component: str, message: str):
        """Логирование информации"""
        self.logger.info(f"[{component}] {message}")


# ============================================================================
# PATTERN 4: Try-except wrapper
# ============================================================================

from functools import wraps


def safe_operation(operation_name: str, logger: ErrorLogger = None):
    """
    Декоратор для безопасного выполнения операций
    
    Usage:
        @safe_operation("create_profile", logger)
        def create_profile(name):
            return {"success": True}
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                
                # Проверь что результат имеет нужный формат
                if isinstance(result, dict):
                    if "success" not in result:
                        result["success"] = True
                    if "message" not in result:
                        result["message"] = "OK"
                
                return result
            
            except ValueError as e:
                if logger:
                    logger.log_error(func.__module__, operation_name, e)
                return {
                    "success": False,
                    "message": f"Ошибка валидации: {str(e)}",
                    "data": None
                }
            
            except KeyError as e:
                if logger:
                    logger.log_error(func.__module__, operation_name, e)
                return {
                    "success": False,
                    "message": f"Не найден ключ: {str(e)}",
                    "data": None
                }
            
            except Exception as e:
                if logger:
                    logger.log_error(func.__module__, operation_name, e, {"args": args, "kwargs": kwargs})
                return {
                    "success": False,
                    "message": f"Ошибка: {str(e)}",
                    "data": None
                }
        
        return wrapper
    return decorator


# ============================================================================
# PATTERN 5: Обработка ошибок в операциях с данными
# ============================================================================

class DataOperationError(Exception):
    """Базовое исключение для ошибок операций с данными"""
    pass


class ProfileNotFoundError(DataOperationError):
    """Профиль не найден"""
    pass


class DuplicateProfileError(DataOperationError):
    """Профиль уже существует"""
    pass


class InvalidOperationError(DataOperationError):
    """Невалидная операция"""
    pass


# Примеры использования:
def create_profile_safe(manager, name: str) -> dict:
    """
    Пример безопасного создания профиля
    """
    # 1. Валидируй входные данные
    is_valid, error_msg = validate_profile_name(name)
    if not is_valid:
        return {
            "success": False,
            "message": error_msg,
            "data": None
        }
    
    # 2. Проверь что не существует
    if name in manager.profiles:
        return {
            "success": False,
            "message": f"Профиль '{name}' уже существует",
            "data": None
        }
    
    # 3. Попытайся создать
    try:
        profile = manager.create_profile(name=name)
        return {
            "success": True,
            "message": f"Профиль '{name}' успешно создан",
            "data": profile
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Ошибка создания профиля: {str(e)}",
            "data": None
        }


# ============================================================================
# PATTERN 6: Context managers для безопасных операций
# ============================================================================

from contextlib import contextmanager


@contextmanager
def safe_file_operation(filepath: str, operation: str = "read"):
    """
    Context manager для безопасной работы с файлами
    
    Usage:
        with safe_file_operation("data.json", "read") as file:
            data = json.load(file)
    """
    file = None
    try:
        if operation == "read":
            file = open(filepath, 'r', encoding='utf-8')
        elif operation == "write":
            file = open(filepath, 'w', encoding='utf-8')
        
        yield file
    
    except FileNotFoundError:
        print(f"❌ Файл не найден: {filepath}")
        yield None
    
    except Exception as e:
        print(f"❌ Ошибка работы с файлом: {e}")
        yield None
    
    finally:
        if file:
            file.close()


# ============================================================================
# PATTERN 7: Retry logic с exponential backoff
# ============================================================================

import time


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 0.5):
    """
    Декоратор для retry с exponential backoff
    
    Usage:
        @retry_with_backoff(max_attempts=3)
        def risky_operation():
            return data
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            delay = base_delay
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                
                except Exception as e:
                    attempt += 1
                    
                    if attempt >= max_attempts:
                        raise e
                    
                    print(f"⚠️ Попытка {attempt} провалилась, retry через {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
        
        return wrapper
    return decorator


# ============================================================================
# PATTERN 8: Rate limiting (для API endpoints)
# ============================================================================

from collections import defaultdict
from datetime import datetime, timedelta


class RateLimiter:
    """Rate limiting для API endpoints"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, identifier: str) -> tuple[bool, str]:
        """
        Проверь позволена ли операция
        
        Args:
            identifier: user_id, IP, или другой уникальный ID
        
        Returns:
            (allowed, message)
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        # Очисти старые requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > window_start
        ]
        
        # Проверь лимит
        if len(self.requests[identifier]) >= self.max_requests:
            return False, f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"
        
        # Добавь текущий request
        self.requests[identifier].append(now)
        return True, "OK"


# ============================================================================
# PATTERN 9: Health check для основных компонентов
# ============================================================================

class HealthCheck:
    """Проверка здоровья системы"""
    
    def __init__(self):
        self.components = {}
    
    def register_component(self, name: str, check_func):
        """
        Регистрируй компонент для проверки
        
        check_func должна возвращать (is_healthy, message)
        """
        self.components[name] = check_func
    
    def check_all(self) -> dict:
        """Проверь все компоненты"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "components": {},
            "healthy": True
        }
        
        for name, check_func in self.components.items():
            try:
                is_healthy, message = check_func()
                results["components"][name] = {
                    "healthy": is_healthy,
                    "message": message
                }
                if not is_healthy:
                    results["healthy"] = False
            except Exception as e:
                results["components"][name] = {
                    "healthy": False,
                    "message": f"Error: {str(e)}"
                }
                results["healthy"] = False
        
        return results


# ============================================================================
# PATTERN 10: Circuit breaker (для предотвращения каскадных ошибок)
# ============================================================================

from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"      # Нормальное состояние
    OPEN = "open"          # Блокирование из-за ошибок
    HALF_OPEN = "half_open"  # Пытаемся восстановиться


class CircuitBreaker:
    """Circuit breaker для предотвращения каскадных сбоев"""
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    def call(self, func, *args, **kwargs):
        """
        Выполни функцию через circuit breaker
        """
        if self.state == CircuitState.OPEN:
            # Проверь timeout
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout_seconds):
                self.state = CircuitState.HALF_OPEN
                print(f"🔄 Circuit breaker: переходим в HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN - service temporarily unavailable")
        
        try:
            result = func(*args, **kwargs)
            
            # Успех - сброс счетчика
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                print(f"✅ Circuit breaker: восстановление - CLOSED")
            
            return result
        
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                print(f"⚠️ Circuit breaker: открыт - OPEN (failures: {self.failure_count})")
            
            raise e


# ============================================================================
# EXAMPLE: Использование всех patterns
# ============================================================================

if __name__ == "__main__":
    # 1. Валидация
    is_valid, msg = validate_profile_name("Valid Name")
    print(f"Валидация: {is_valid} - {msg}")
    
    # 2. Безопасное хранилище
    storage = SafeJSONStorage("test_data.json")
    success, msg = storage.save({"key": "value"})
    print(f"Сохранение: {success} - {msg}")
    
    # 3. Логирование
    logger = ErrorLogger("errors.log")
    logger.log_info("TEST", "Тестовое сообщение")
    
    # 4. Rate limiting
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    allowed, msg = limiter.is_allowed("user_123")
    print(f"Rate limit: {allowed} - {msg}")
    
    # 5. Health check
    health = HealthCheck()
    health.register_component("database", lambda: (True, "OK"))
    print(f"Health: {health.check_all()}")
