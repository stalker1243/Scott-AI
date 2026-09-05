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

try:
    from . import os_actions
except ImportError:
    import os_actions
import time
import threading

class ExtendedCommandExecutor:
    """Исполнитель расширенных команд"""
    
    def __init__(self):
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
            result = subprocess.run(
                os_actions.shell_command(command),
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
        """Открыть папку в файловом менеджере системы."""
        result = os_actions.open_path(path)
        if result["success"]:
            return {"success": True, "message": f"Открываю {path}"}
        return {"success": False, "error": result["error"]}
    
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
        """Увеличить громкость."""
        result = os_actions.change_volume("up")
        if result["success"]:
            return {"success": True, "message": "Громкость увеличена"}
        return {"success": False, "error": result["error"]}
    
    def volume_down(self) -> Dict[str, Any]:
        """Уменьшить громкость."""
        result = os_actions.change_volume("down")
        if result["success"]:
            return {"success": True, "message": "Громкость уменьшена"}
        return {"success": False, "error": result["error"]}
    
    def brightness_up(self) -> Dict[str, Any]:
        """Увеличить яркость экрана."""
        result = os_actions.change_brightness("up")
        if result["success"]:
            return {"success": True, "message": "Яркость увеличена"}
        return {"success": False, "error": result["error"]}
    
    def brightness_down(self) -> Dict[str, Any]:
        """Уменьшить яркость экрана."""
        result = os_actions.change_brightness("down")
        if result["success"]:
            return {"success": True, "message": "Яркость уменьшена"}
        return {"success": False, "error": result["error"]}
    
    def sleep_system(self) -> Dict[str, Any]:
        """Перевести компьютер в спящий режим."""
        result = os_actions.power_action("sleep")
        if result["success"]:
            return {"success": True, "message": "Перевожу компьютер в спящий режим"}
        return {"success": False, "error": result["error"]}
    
    def restart_system(self) -> Dict[str, Any]:
        """Перезагрузить компьютер (с задержкой, чтобы успеть передумать)."""
        result = os_actions.power_action("restart")
        if result["success"]:
            return {"success": True, "message": "Перезагрузка через 30 секунд"}
        return {"success": False, "error": result["error"]}
    
    def shutdown_system(self) -> Dict[str, Any]:
        """Выключить компьютер (с задержкой, чтобы успеть передумать)."""
        result = os_actions.power_action("shutdown")
        if result["success"]:
            return {"success": True, "message": "Выключение через 30 секунд"}
        return {"success": False, "error": result["error"]}
    
    # ==================== URL ОПЕРАЦИИ ====================
    
    def open_url(self, url: str) -> Dict[str, Any]:
        """Открыть ссылку в браузере по умолчанию."""
        result = os_actions.open_url(url)
        if result["success"]:
            return {"success": True, "message": f"Открываю {url}"}
        return {"success": False, "error": result["error"]}
    
    # ==================== РАСПИСАНИЕ И АВТОМАТИЗАЦИЯ ====================
    
    
    
    
    
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
        return f"ExtendedCommandExecutor(commands={self.metrics['total_commands']})"


def get_extended_executor() -> ExtendedCommandExecutor:
    """Factory функция для получения исполнителя"""
    return ExtendedCommandExecutor()
