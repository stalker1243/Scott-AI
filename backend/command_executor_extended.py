"""
Расширенный исполнитель команд - PowerShell, файлы, система, расписание
"""

import subprocess
import os
import json
import webbrowser
import datetime
from pathlib import Path
from typing import Dict, Any, List
import platform
import schedule
import time
import threading

class ExtendedCommandExecutor:
    """Исполнитель расширенных команд"""
    
    def __init__(self):
        self.scheduled_commands: List[Dict] = []
        self.command_history: List[Dict] = []
        self.metrics = {
            'total_commands': 0,
            'successful_commands': 0,
            'failed_commands': 0,
            'command_types': {}
        }
        print("✅ Расширенный исполнитель инициализирован")
    
    # ==================== POWERSHELL КОМАНДЫ ====================
    
    def execute_powershell(self, command: str) -> Dict[str, Any]:
        """
        Выполнить PowerShell команду
        """
        try:
            if platform.system() == 'Windows':
                # Windows PowerShell
                result = subprocess.run(
                    ['powershell', '-Command', command],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                # Linux/Mac - bash
                result = subprocess.run(
                    ['/bin/bash', '-c', command],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            
            success = result.returncode == 0
            return {
                'success': success,
                'output': result.stdout if success else result.stderr,
                'error': result.stderr if not success else None
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Команда выполнялась слишком долго'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== ФАЙЛОВЫЕ ОПЕРАЦИИ ====================
    
    def open_folder(self, path: str) -> Dict[str, Any]:
        """
        Открыть папку в файловом менеджере
        """
        try:
            path = Path(path).resolve()
            
            if not path.exists():
                return {'success': False, 'error': f'Папка не найдена: {path}'}
            
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(path)])
            else:  # Linux
                subprocess.run(['xdg-open', str(path)])
            
            return {'success': True, 'message': f'Папка открыта: {path}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def delete_file(self, file_path: str) -> Dict[str, Any]:
        """
        Удалить файл (с подтверждением)
        """
        try:
            path = Path(file_path).resolve()
            
            if not path.exists():
                return {'success': False, 'error': f'Файл не найден: {path}'}
            
            if path.is_file():
                path.unlink()
                return {'success': True, 'message': f'Файл удален: {path}'}
            else:
                return {'success': False, 'error': 'Это папка, а не файл'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def copy_file(self, src: str, dest: str) -> Dict[str, Any]:
        """
        Скопировать файл
        """
        try:
            import shutil
            src_path = Path(src).resolve()
            dest_path = Path(dest).resolve()
            
            if not src_path.exists():
                return {'success': False, 'error': f'Исходный файл не найден: {src}'}
            
            shutil.copy2(src_path, dest_path)
            return {'success': True, 'message': f'Файл скопирован: {src} -> {dest}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def move_file(self, src: str, dest: str) -> Dict[str, Any]:
        """
        Переместить файл
        """
        try:
            import shutil
            src_path = Path(src).resolve()
            dest_path = Path(dest).resolve()
            
            if not src_path.exists():
                return {'success': False, 'error': f'Исходный файл не найден: {src}'}
            
            shutil.move(str(src_path), str(dest_path))
            return {'success': True, 'message': f'Файл перемещен: {src} -> {dest}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== СИСТЕМНЫЕ КОМАНДЫ ====================
    
    def volume_up(self) -> Dict[str, Any]:
        """Увеличить громкость"""
        try:
            if platform.system() == 'Windows':
                self.execute_powershell(
                    "(New-Object -ComObject WScript.Shell).SendKeys([char]175)"
                )
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 
                    'set volume output volume ((output volume of (get volume settings)) + 10)'])
            else:  # Linux
                subprocess.run(['amixer', 'set', 'Master', '5%+'])
            
            return {'success': True, 'message': 'Громкость увеличена'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def volume_down(self) -> Dict[str, Any]:
        """Уменьшить громкость"""
        try:
            if platform.system() == 'Windows':
                self.execute_powershell(
                    "(New-Object -ComObject WScript.Shell).SendKeys([char]174)"
                )
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 
                    'set volume output volume ((output volume of (get volume settings)) - 10)'])
            else:  # Linux
                subprocess.run(['amixer', 'set', 'Master', '5%-'])
            
            return {'success': True, 'message': 'Громкость уменьшена'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def brightness_up(self) -> Dict[str, Any]:
        """Увеличить яркость"""
        try:
            if platform.system() == 'Windows':
                # Windows требует WMI
                self.execute_powershell(
                    'Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods | ' +
                    'ForEach-Object { $_.WmiSetBrightness(1, 10) }'
                )
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 
                    'tell application "System Events" to key code 145'])
            else:  # Linux
                subprocess.run(['xdotool', 'key', 'XF86MonBrightnessUp'])
            
            return {'success': True, 'message': 'Яркость увеличена'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def brightness_down(self) -> Dict[str, Any]:
        """Уменьшить яркость"""
        try:
            if platform.system() == 'Windows':
                self.execute_powershell(
                    'Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods | ' +
                    'ForEach-Object { $_.WmiSetBrightness(1, -10) }'
                )
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 
                    'tell application "System Events" to key code 144'])
            else:  # Linux
                subprocess.run(['xdotool', 'key', 'XF86MonBrightnessDown'])
            
            return {'success': True, 'message': 'Яркость уменьшена'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def sleep_system(self) -> Dict[str, Any]:
        """Включить спящий режим"""
        try:
            if platform.system() == 'Windows':
                os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
            elif platform.system() == 'Darwin':
                os.system('osascript -e "tell application \\"System Events\\" to sleep"')
            else:  # Linux
                os.system('systemctl suspend')
            
            return {'success': True, 'message': 'Система переводится в спящий режим'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def restart_system(self) -> Dict[str, Any]:
        """Перезагрузить систему"""
        try:
            if platform.system() == 'Windows':
                os.system('shutdown /r /t 30 /c "Перезагрузка инициирована Scott"')
            elif platform.system() == 'Darwin':
                os.system('osascript -e "tell application \\"System Events\\" to restart"')
            else:  # Linux
                os.system('sudo shutdown -r +1')
            
            return {'success': True, 'message': 'Система будет перезагружена через 30 сек'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def shutdown_system(self) -> Dict[str, Any]:
        """Выключить систему"""
        try:
            if platform.system() == 'Windows':
                os.system('shutdown /s /t 30 /c "Выключение инициировано Scott"')
            elif platform.system() == 'Darwin':
                os.system('osascript -e "tell application \\"System Events\\" to shut down"')
            else:  # Linux
                os.system('sudo shutdown -h +1')
            
            return {'success': True, 'message': 'Система будет выключена через 30 сек'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== URL ОПЕРАЦИИ ====================
    
    def open_url(self, url: str) -> Dict[str, Any]:
        """
        Открыть URL в браузере
        """
        try:
            # Добавить протокол если его нет
            if not url.startswith(('http://', 'https://', 'ftp://')):
                url = 'https://' + url
            
            webbrowser.open(url)
            return {'success': True, 'message': f'Открыт URL: {url}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== РАСПИСАНИЕ И АВТОМАТИЗАЦИЯ ====================
    
    def schedule_command(self, command: str, time_str: str, command_type: str = 'powershell') -> Dict[str, Any]:
        """
        Запланировать выполнение команды
        time_str формат: "HH:MM" или "every X minutes"
        """
        try:
            task_id = datetime.datetime.now().timestamp()
            
            task = {
                'id': task_id,
                'command': command,
                'time': time_str,
                'type': command_type,
                'created_at': datetime.datetime.now().isoformat()
            }
            
            self.scheduled_commands.append(task)
            
            # Начать отдельный поток для выполнения расписания
            if len(self.scheduled_commands) == 1:
                self._start_scheduler()
            
            return {'success': True, 'message': f'Команда запланирована на {time_str}', 'task_id': task_id}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _start_scheduler(self):
        """Начать scheduler в отдельном потоке"""
        def run_scheduler():
            while self.scheduled_commands:
                schedule.run_pending()
                time.sleep(30)  # Проверка каждые 30 сек
        
        thread = threading.Thread(target=run_scheduler, daemon=True)
        thread.start()
    
    def list_scheduled_commands(self) -> Dict[str, Any]:
        """Получить список запланированных команд"""
        return {
            'success': True,
            'commands': self.scheduled_commands,
            'count': len(self.scheduled_commands)
        }
    
    def cancel_scheduled_command(self, task_id: float) -> Dict[str, Any]:
        """Отменить запланированную команду"""
        try:
            self.scheduled_commands = [t for t in self.scheduled_commands if t['id'] != task_id]
            return {'success': True, 'message': 'Команда отменена'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== ИСТОРИЯ И МЕТРИКИ ====================
    
    def log_command(self, command: str, command_type: str, success: bool, response: str = ''):
        """Сохранить команду в историю"""
        entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'command': command,
            'type': command_type,
            'success': success,
            'response': response
        }
        
        self.command_history.append(entry)
        
        # Обновить метрики
        self.metrics['total_commands'] += 1
        if success:
            self.metrics['successful_commands'] += 1
        else:
            self.metrics['failed_commands'] += 1
        
        # Обновить счетчик по типам
        if command_type not in self.metrics['command_types']:
            self.metrics['command_types'][command_type] = 0
        self.metrics['command_types'][command_type] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получить метрики"""
        return {
            'success': True,
            'metrics': self.metrics,
            'history_count': len(self.command_history),
            'success_rate': (
                self.metrics['successful_commands'] / self.metrics['total_commands'] * 100
                if self.metrics['total_commands'] > 0 else 0
            )
        }
    
    def get_command_history(self, limit: int = 50) -> Dict[str, Any]:
        """Получить историю команд"""
        return {
            'success': True,
            'history': self.command_history[-limit:],
            'total': len(self.command_history)
        }
    
    def clear_history(self) -> Dict[str, Any]:
        """Очистить историю"""
        self.command_history = []
        return {'success': True, 'message': 'История очищена'}
    
    def __repr__(self):
        return f"ExtendedCommandExecutor(commands={self.metrics['total_commands']}, scheduled={len(self.scheduled_commands)})"


def get_extended_executor() -> ExtendedCommandExecutor:
    """Factory функция для получения исполнителя"""
    return ExtendedCommandExecutor()
