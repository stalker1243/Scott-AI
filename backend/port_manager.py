"""
Менеджер портов - проверка занятости, поиск свободных портов
"""

import socket
import subprocess
import sys
import os
from typing import Tuple, List

def is_port_open(port: int, host: str = '127.0.0.1') -> bool:
    """
    Проверить, открыт ли порт
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"❌ Ошибка проверки порта {port}: {e}")
        return False

def find_free_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """
    Найти свободный порт начиная с start_port
    """
    for port in range(start_port, start_port + max_attempts):
        if not is_port_open(port):
            print(f"✅ Найден свободный порт: {port}")
            return port
    
    print(f"❌ Не найдено свободных портов в диапазоне {start_port}-{start_port + max_attempts}")
    return start_port

def kill_process_on_port(port: int) -> bool:
    """
    Убить процесс на портпе (Windows)
    """
    try:
        if sys.platform == 'win32':
            # Windows
            result = subprocess.run(
                f'netstat -ano | findstr :{port}',
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                # Получить PID
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split()
                    if len(parts) > 0:
                        pid = parts[-1]
                        try:
                            subprocess.run(f'taskkill /PID {pid} /F', shell=True, capture_output=True)
                            print(f"✅ Убит процесс PID {pid} на порту {port}")
                            return True
                        except:
                            pass
        else:
            # Linux/Mac
            result = subprocess.run(
                f'lsof -i :{port}',
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                lines = result.stdout.strip().split('\n')[1:]  # Пропустить header
                for line in lines:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        try:
                            subprocess.run(f'kill -9 {pid}', shell=True, capture_output=True)
                            print(f"✅ Убит процесс PID {pid} на порту {port}")
                            return True
                        except:
                            pass
    except Exception as e:
        print(f"⚠️ Ошибка при убийстве процесса: {e}")
        return False
    
    return False

def ensure_port_free(port: int, force_kill: bool = False) -> int:
    """
    Убедиться что порт свободен. Если занят - убить процесс или найти другой
    """
    if not is_port_open(port):
        print(f"✅ Порт {port} свободен")
        return port
    
    print(f"⚠️ Порт {port} занят")
    
    if force_kill:
        if kill_process_on_port(port):
            import time
            time.sleep(1)  # Дождаться освобождения
            if not is_port_open(port):
                return port
    
    # Если не удалось освободить - найти другой
    new_port = find_free_port(port, max_attempts=10)
    print(f"🔄 Используем альтернативный порт: {new_port}")
    return new_port


if __name__ == '__main__':
    # Тестирование
    port = 8000
    print(f"Проверка порта {port}...")
    print(f"Занят: {is_port_open(port)}")
    
    free_port = find_free_port(8000, 5)
    print(f"Свободный порт: {free_port}")
