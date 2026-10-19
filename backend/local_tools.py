"""Small offline tools, bounded arithmetic, and one explicit monotonic stopwatch."""
import ast
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
import math
import re
import secrets
import threading
import time
import utility_units

def number(text):
    text = text.strip().replace(',', '.')
    if re.fullmatch(r'[+-]?\d{1,14}(?:\.\d{1,12})?', text):
        return Decimal(text)
    from voice_commands import _spoken_number
    result = _spoken_number('сто' if text == 'ста' else text)
    if result is None:
        raise ValueError('Назовите число цифрами или словами от нуля до ста.')
    return Decimal(result)

def format_number(value):
    with localcontext() as context:
        context.prec = 40
        value = value.normalize()
        return format(value, 'f') if value == 0 or Decimal('1e-12') <= abs(value) < Decimal('1e21') else format(value, 'g')

def prepare_expression(expression):
    expression = expression.casefold().replace('×', '*').replace('÷', '/').replace('^', '**')
    # Commas separate function arguments; plain arithmetic accepts decimal commas.
    if not re.search(r'\b(?:sqrt|abs|round|min|max)\s*\(', expression):
        expression = expression.replace(',', '.')
    for phrase, symbol in (('умножить на', '*'), ('разделить на', '/'), ('делить на', '/'),
            ('в степени', '**'), ('плюс', '+'), ('минус', '-'), ('умножить', '*'), ('разделить', '/')):
        expression = re.sub(r'\b' + phrase + r'\b', symbol, expression)
    expression = re.sub(r'(?<=\d)\s*[xх]\s*(?=\d)', '*', expression)
    if expression.startswith('корень из '):
        expression = 'sqrt(' + expression[10:] + ')'
    def spoken(match):
        text = match[0].strip()
        if text in ('sqrt', 'abs', 'round', 'min', 'max', 'pi', 'e'):
            return text
        return str(number(text))
    expression = re.sub(r'[a-zа-яё]+(?:\s+[a-zа-яё]+)*', spoken, expression).strip()
    if len(expression) > 512:
        raise ValueError('Выражение слишком длинное.')
    return expression

def calculate(expression):
    expression = prepare_expression(expression)
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, ValueError):
        raise ValueError('Не понял выражение. Например: «посчитай (12 + 3) / 5».') from None
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError('Слишком много операций в выражении.')
    def visit(node, depth=0):
        if depth > 20:
            raise ValueError('Выражение слишком вложенное.')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = Decimal(ast.get_source_segment(expression, node))
            if result != 0 and result.adjusted() < -100:
                raise ValueError('Число слишком мало для этого калькулятора.')
        elif isinstance(node, ast.Name) and node.id in ('pi', 'e'):
            result = Decimal('3.141592653589793238462643383' if node.id == 'pi' else '2.718281828459045235360287471')
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand, depth+1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            left, right = visit(node.left, depth+1), visit(node.right, depth+1)
            if isinstance(node.op, ast.Add): result = left + right
            elif isinstance(node.op, ast.Sub): result = left - right
            elif isinstance(node.op, ast.Mult): result = left * right
            elif isinstance(node.op, ast.Div): result = left / right
            elif isinstance(node.op, ast.FloorDiv): result = Decimal(math.floor(left / right))
            elif isinstance(node.op, ast.Mod): result = left - Decimal(math.floor(left / right)) * right
            elif isinstance(node.op, ast.Pow) and right == right.to_integral_value() and abs(right) <= 100:
                result = left ** int(right)
            else: raise ValueError('Эта операция недоступна; степень должна быть целым числом от −100 до 100.')
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and 1 <= len(node.args) <= 8:
            values = [visit(arg, depth+1) for arg in node.args]
            name = node.func.id
            if name == 'sqrt' and len(values) == 1: result = values[0].sqrt()
            elif name == 'abs' and len(values) == 1: result = abs(values[0])
            elif name in ('min', 'max'): result = (min if name == 'min' else max)(values)
            elif name == 'round' and len(values) in (1, 2):
                places = values[1] if len(values) == 2 else Decimal(0)
                if places != places.to_integral_value() or abs(places) > 12:
                    raise ValueError('Округление допускает от −12 до 12 знаков.')
                result = round(values[0], int(places))
            else: raise ValueError('Доступны sqrt, abs, round, min и max.')
        else:
            raise ValueError('Допустимы только числа и арифметические операции.')
        if not result.is_finite() or abs(result) > Decimal('1e100'):
            raise ValueError('Результат слишком велик.')
        return result
    with localcontext() as context:
        context.prec = 40
        return visit(tree.body)

class Stopwatch:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.state, self.started, self.elapsed, self.laps = 'idle', 0., 0., []

    def run(self, operation):
        if operation not in ('start', 'resume', 'pause', 'stop', 'reset', 'lap', 'status'):
            raise ValueError('Неизвестное действие секундомера.')
        with self.lock:
            now = self.clock()
            elapsed = self.elapsed + (max(0., now-self.started) if self.state == 'running' else 0.)
            if operation == 'start' and self.state != 'running':
                self.started, self.elapsed, self.laps, elapsed, self.state = now, 0., [], 0., 'running'
            elif operation == 'resume' and self.state == 'paused':
                self.started, self.state = now, 'running'
            elif operation in ('pause', 'stop'):
                self.elapsed, self.state = elapsed, 'paused' if operation == 'pause' else 'stopped'
            elif operation == 'reset':
                self.state, self.elapsed, self.laps, elapsed = 'idle', 0., [], 0.
            elif operation == 'lap':
                if self.state != 'running':
                    raise ValueError('Сначала запустите секундомер.')
                if len(self.laps) >= 100:
                    raise ValueError('Сохранено 100 кругов. Сбросьте секундомер для нового замера.')
                self.laps.append(elapsed)
            milliseconds = int(elapsed * 1000)
            hours, rest = divmod(milliseconds, 3600000)
            minutes, rest = divmod(rest, 60000)
            seconds, millis = divmod(rest, 1000)
            shown = f'{hours:02}:{minutes:02}:{seconds:02}.{millis:03}'
            labels = {'idle': 'сброшен', 'running': 'работает', 'paused': 'на паузе', 'stopped': 'остановлен'}
            return f'Секундомер {labels[self.state]}: {shown}' + (f'. Круг {len(self.laps)}.' if operation == 'lap' else ''), {
                'state': self.state, 'elapsed_seconds': elapsed, 'laps': list(self.laps)}

stopwatch = Stopwatch()
WEEKDAYS = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')
def read_date(text):
    try:
        return date.fromisoformat(text) if '-' in text else datetime.strptime(text, '%d.%m.%Y').date()
    except ValueError:
        raise ValueError('Укажите существующую дату: 31.12.2026 или 2026-12-31.') from None

def execute(request, today=None):
    try:
        action, today = request['action'], today or date.today()
        data = {}
        if action == 'calculate':
            response = format_number(calculate(request['expression']))
        elif action == 'percent':
            response = format_number(number(request['value']) * number(request['percent']) / 100)
        elif action == 'convert':
            value, label = utility_units.convert(number(request['value']), request['source'], request['target'])
            response = format_number(value) + ' ' + label
        elif action == 'date':
            when = today + timedelta(days=request['offset'])
            response = f'{when:%d.%m.%Y}, {WEEKDAYS[when.weekday()]}'
        elif action in ('days_until', 'days_between'):
            first = today if action == 'days_until' else read_date(request['first'])
            last = read_date(request['date'] if action == 'days_until' else request['last'])
            days = (last-first).days
            count = abs(days)
            label = 'дней' if 11 <= count % 100 <= 14 else ('день' if count % 10 == 1 else 'дня' if 2 <= count % 10 <= 4 else 'дней')
            response = f'{count} {label}' + (' назад' if action == 'days_until' and days < 0 else '')
            data = {'days': days}
        elif action == 'random':
            low, high = request['minimum'], request['maximum']
            if low > high:
                raise ValueError('Начало диапазона должно быть не больше конца.')
            response = str(low + secrets.randbelow(high-low+1))
        elif action == 'coin':
            response = 'Орёл' if secrets.randbelow(2) else 'Решка'
        elif action == 'stopwatch':
            response, data = stopwatch.run(request['operation'])
        elif action == 'system_volume':
            import system_volume
            result = system_volume.execute(request['operation'], request.get('value'))
            return dict(result, tool=action)
        else:
            raise ValueError('Неизвестный локальный инструмент.')
        return {'success': True, 'response': response, 'tool': action, 'data': data}
    except DecimalException:
        return {'success': False, 'response': 'Вычисление не удалось: проверьте делитель, корень и размер чисел.', 'tool': request.get('action')}
    except (ValueError, OverflowError):
        import sys
        return {'success': False, 'response': str(sys.exception()), 'tool': request.get('action')}
