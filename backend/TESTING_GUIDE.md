# 🧪 TESTING GUIDE - Scott v3.3

Полное руководство по тестированию backend компонентов.

---

## 📋 СОДЕРЖАНИЕ

1. [Быстрый старт](#быстрый-старт)
2. [Установка](#установка)
3. [Запуск тестов](#запуск-тестов)
4. [Интерпретация результатов](#интерпретация-результатов)
5. [Написание тестов](#написание-тестов)
6. [Troubleshooting](#troubleshooting)

---

## 🚀 БЫСТРЫЙ СТАРТ

```bash
# 1. Установи зависимости для тестирования
pip install -r requirements-test.txt

# 2. Запусти все тесты
pytest tests/ -v

# 3. Получи отчет о покрытии
pytest tests/ --cov=. --cov-report=html
```

---

## 📦 УСТАНОВКА

### 1. Убедись что ты в backend директории

```bash
cd backend
```

### 2. Установи testing зависимости

```bash
pip install -r requirements-test.txt
```

Это установит:
- `pytest` - фреймворк для тестирования
- `pytest-cov` - отчет о покрытии кода
- `pytest-asyncio` - async тесты
- `pytest-xdist` - параллельное выполнение
- `httpx` - HTTP клиент для тестов

### 3. Проверь что pytest работает

```bash
pytest --version
```

---

## 🎯 ЗАПУСК ТЕСТОВ

### Все тесты

```bash
pytest tests/ -v
```

**Параметры:**
- `-v` - verbose output (показывает каждый тест)
- `-s` - показывай print() statements
- `-k KEYWORD` - запусти только тесты с keyword
- `-x` - остановись на первой ошибке
- `--tb=short` - короткий traceback

### Тесты одного модуля

```bash
# Только профили
pytest tests/test_profiles.py -v

# Только шаблоны
pytest tests/test_templates.py -v

# Только макросы
pytest tests/test_macros.py -v

# Только версии
pytest tests/test_versions.py -v

# Только API
pytest tests/test_api.py -v
```

### По меткам (markers)

```bash
# Только юнит тесты
pytest -m unit -v

# Только интеграционные тесты
pytest -m integration -v

# Только тесты на стабильность
pytest -m stability -v

# Исключи медленные тесты
pytest -m "not slow" -v
```

### С параллельным выполнением

```bash
# Запусти 4 тесты одновременно
pytest tests/ -n 4 -v
```

### С отчетом о покрытии

```bash
# Базовый отчет
pytest tests/ --cov=. --cov-report=term

# HTML отчет (открой htmlcov/index.html)
pytest tests/ --cov=. --cov-report=html

# JSON отчет
pytest tests/ --cov=. --cov-report=json
```

---

## 📊 ИНТЕРПРЕТАЦИЯ РЕЗУЛЬТАТОВ

### ✅ Успешный тест

```
test_profiles.py::TestUserProfile::test_profile_creation PASSED
```

### ❌ Неудачный тест

```
test_profiles.py::TestUserProfile::test_invalid_name FAILED
```

**Как читать ошибку:**
```
FAILED test_profiles.py::TestUserProfile::test_invalid_name - AssertionError
  assert False == True
```

Смотри:
1. Какой файл/класс/тест упал
2. Какая ошибка (AssertionError, ValueError, etc)
3. На какой строке (увидишь в traceback)

### ⊘ Пропущенный тест

```
test_profiles.py::TestUserProfile::test_todo SKIPPED
```

Может быть помечен с `@pytest.mark.skip` или `@pytest.mark.xfail`

### 🟡 Предупреждение

```
test_profiles.py::TestUserProfile::test_warning WARNING
```

---

## 📈 ИНТЕРПРЕТАЦИЯ ПОКРЫТИЯ

```
tests/test_profiles.py    145 lines    142 covered    97%
tests/test_templates.py   120 lines    115 covered    95%
tests/test_macros.py      130 lines    128 covered    98%
tests/test_versions.py    125 lines    120 covered    96%
tests/test_api.py         200 lines    190 covered    95%
---
TOTAL                     720 lines    695 covered    96%
```

**Что это значит:**
- 96% покрытия = хорошо! ✅
- 90%+ = отлично
- 80-90% = приемлемо
- <80% = нужны дополнительные тесты

### Где посмотреть какой код не покрыт

```bash
pytest tests/ --cov=. --cov-report=html
# Потом открой htmlcov/index.html в браузере
# Красная строка = не покрыта тестом
# Зеленая строка = покрыта тестом
```

---

## 🧪 НАПИСАНИЕ ТЕСТОВ

### Структура теста

```python
def test_something():
    # ARRANGE - подготовка данных
    input_data = {"key": "value"}
    
    # ACT - выполнение операции
    result = function(input_data)
    
    # ASSERT - проверка результата
    assert result == expected_value
```

### Простой пример

```python
def test_create_profile():
    # Arrange
    manager = ProfileManager()
    
    # Act
    result = manager.create_profile(name="Test")
    
    # Assert
    assert result["success"] == True
    assert "Test" in manager.profiles
```

### Тест с fixtures

```python
@pytest.fixture
def manager(tmp_path):
    """Fixture предоставляет чистый менеджер"""
    import os
    os.environ["DATA_DIR"] = str(tmp_path)
    return ProfileManager()

def test_with_fixture(manager):
    """Используй fixture как параметр"""
    result = manager.create_profile(name="Test")
    assert result["success"] == True
```

### Параметризованный тест

```python
@pytest.mark.parametrize("input,expected", [
    ("Профиль 1", True),
    ("Профиль 2", True),
    ("", False),
])
def test_create_with_params(input, expected):
    manager = ProfileManager()
    result = manager.create_profile(name=input)
    assert result["success"] == expected
```

### Тест на исключения

```python
def test_error_handling():
    manager = ProfileManager()
    
    # Проверь что выбрасывается исключение
    with pytest.raises(ValueError):
        manager.do_something_invalid()
```

---

## 🛠️ TROUBLESHOOTING

### Тест падает с ModuleNotFoundError

```
ModuleNotFoundError: No module named 'profile_manager'
```

**Решение:**
```bash
# Убедись что ты в backend директории
cd backend

# Запусти pytest из backend
pytest tests/ -v
```

### ImportError: cannot import name 'ProfileManager'

**Проверь:**
1. Есть ли файл `profile_manager.py` в backend?
2. Правильно ли импортируется в conftest.py?
3. Нет ли синтаксических ошибок в модуле?

```bash
# Проверь синтаксис
python -m py_compile profile_manager.py
```

### Тесты медленно выполняются

**Решение:**
```bash
# Запусти только быстрые тесты
pytest -m "not slow" -v

# Или запусти параллельно
pytest tests/ -n 4 -v
```

### Тесты зависят друг от друга

❌ **ПЛОХО:**
```python
def test_1():
    create_profile()

def test_2():
    # Зависит от test_1 создавшего профиль
    switch_profile()
```

✅ **ХОРОШО:**
```python
def test_1():
    manager = ProfileManager()
    manager.create_profile()

def test_2():
    manager = ProfileManager()  # Новый экземпляр
    manager.switch_profile()
```

**Используй fixtures для setup:**
```python
@pytest.fixture
def clean_manager(tmp_path):
    """Каждый тест получает чистый менеджер"""
    os.environ["DATA_DIR"] = str(tmp_path)
    return ProfileManager()

def test_1(clean_manager):
    clean_manager.create_profile()

def test_2(clean_manager):
    clean_manager.switch_profile()
```

### Тесты зависят от времени

❌ **ПЛОХО:**
```python
def test_timing():
    time.sleep(1)  # Почему? Тест медленный!
    assert something()
```

✅ **ХОРОШО:**
```python
def test_timing(mock_time):
    """Используй mock для времени"""
    with mock.patch('time.time', return_value=100):
        assert something()
```

---

## 📋 ЧЕКЛИСТ ДЛЯ НОВЫХ ТЕСТОВ

Когда пишешь новый тест:

- [ ] Имя теста начинается с `test_`
- [ ] Имя понятное: `test_create_profile_success`
- [ ] Используешь Arrange-Act-Assert паттерн
- [ ] Каждый тест независим (не зависит от других)
- [ ] Используешь fixtures для setup/teardown
- [ ] Проверяешь happy path и edge cases
- [ ] Проверяешь обработку ошибок
- [ ] Добавил docstring: что тест проверяет
- [ ] Добавил нужный marker (@pytest.mark.unit/integration/stability)
- [ ] Тест быстрый (<1 сек для unit, <5 сек для integration)

---

## 🎯 РЕКОМЕНДУЕМЫЙ WORKFLOW

### День 1 - Установка и базовые тесты

```bash
# 1. Установи тестирование
pip install -r requirements-test.txt

# 2. Запусти все тесты
pytest tests/ -v

# 3. Посмотри результаты
# Должно быть примерно: 300+ passed, 0 failed
```

### День 2 - Тесты на стабильность

```bash
# 1. Запусти тесты на стабильность
pytest -m stability -v

# 2. Проверь performance
pytest tests/ -v --tb=short -s

# 3. Генерируй отчет о покрытии
pytest tests/ --cov=. --cov-report=html
# Открой htmlcov/index.html
```

### День 3 - Добавь свои тесты

```bash
# 1. Создай новый файл tests/test_my_feature.py
# 2. Напиши тесты
# 3. Запусти: pytest tests/test_my_feature.py -v
# 4. Добавь к suite: pytest tests/ -v
```

---

## 📊 ОТЧЕТ О СТАТУСЕ

```bash
# Базовый статус
pytest tests/ -v --tb=short

# С покрытием и таймингами
pytest tests/ -v --cov=. --tb=short --durations=10

# Только failed тесты
pytest tests/ -v --tb=short --lf

# Только failed + пытайся все
pytest tests/ -v --tb=short --failed-first
```

---

## 🎊 УСПЕШНЫЕ РЕЗУЛЬТАТЫ

```
================================ test session starts =================================
platform win32 -- Python 3.13.7, pytest-7.4.3, pluggy-1.3.0
rootdir: C:\...\backend
collected 300 items

tests/test_profiles.py ............................ [ 30%]
tests/test_templates.py ........................... [ 40%]
tests/test_macros.py ............................. [ 50%]
tests/test_versions.py ........................... [ 60%]
tests/test_api.py ................................ [ 100%]

========================= 300 passed in 12.34s ==========================
Coverage HTML written to htmlcov/index.html
Coverage: 95% ✅
```

---

## 🚨 ЕСЛИ ЧТО-ТО УПАЛО

1. **Прочитай ошибку в консоли**
   - Какой тест упал?
   - Какая была ошибка?
   - На какой строке?

2. **Посмотри traceback**
   ```
   test_profiles.py:45: in test_create_profile
   > assert result["success"] == True
   E AssertionError: assert False == True
   ```
   - Строка 45: `assert result["success"] == True`
   - Это значит что result["success"] = False

3. **Запусти тест отдельно**
   ```bash
   pytest tests/test_profiles.py::TestUserProfile::test_create_profile -v -s
   ```
   `-s` покажет print() statements

4. **Добавь debug информацию**
   ```python
   def test_create_profile(manager):
       result = manager.create_profile(name="Test")
       print(f"Result: {result}")  # DEBUG
       assert result["success"] == True
   ```

5. **Проверь что модуль работает**
   ```bash
   python -c "from profile_manager import ProfileManager; print('OK')"
   ```

---

## 📞 ПОМОЩЬ

**Если тест падает:**
1. Погугли сообщение об ошибке
2. Посмотри в код теста что он проверяет
3. Проверь что исследуемый модуль работает
4. Добавь print() statements для debug

**Если не знаешь как писать тест:**
1. Смотри примеры в tests/
2. Используй Arrange-Act-Assert паттерн
3. Один тест = одна проверка

**Если pytest не работает:**
```bash
# Переустанови
pip uninstall pytest pytest-cov -y
pip install -r requirements-test.txt

# Проверь версию
pytest --version
```

---

## ✅ ГОТОВО!

Теперь ты готов к тестированию Scott v3.3! 🎉

```bash
pytest tests/ -v --cov=. --cov-report=html
```

Удачи! 🚀
