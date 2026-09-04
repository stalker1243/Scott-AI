"""
Расширенный исполнитель команд
Открытие программ, создание файлов, веб-поиск, валюты, погода и т.д.
"""

import subprocess
import os
import webbrowser
import psutil
import re
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import platform
import shutil

# Импортируем веб-скрейпер
try:
    from web_scraper import get_web_scraper
except ImportError:
    get_web_scraper = None

# Импортируем расширенный исполнитель
try:
    from command_executor_extended import get_extended_executor
    HAS_EXTENDED = True
except ImportError:
    HAS_EXTENDED = False
    get_extended_executor = None


class CommandExecutor:
    """Расширенный исполнитель системных команд"""
    
    # Карта приложений (название -> исполняемый файл)
    APP_MAP = {
        'блокнот': 'notepad.exe',
        'notepad': 'notepad.exe',
        'текстредактор': 'notepad.exe',
        
        'chrome': 'chrome.exe',
        'гугл': 'chrome.exe',
        'браузер': 'chrome.exe',
        
        'firefox': 'firefox.exe',
        
        'edge': 'msedge.exe',
        
        'visual studio code': 'code.exe',
        'vscode': 'code.exe',
        'vs code': 'code.exe',
        'код': 'code.exe',
        
        'cmd': 'cmd.exe',
        'командная строка': 'cmd.exe',
        'терминал': 'powershell.exe',
        'powershell': 'powershell.exe',
        
        'paint': 'mspaint.exe',
        'рисование': 'mspaint.exe',
        
        'excel': 'excel.exe',
        'таблица': 'excel.exe',
        
        'word': 'winword.exe',
        'документ': 'winword.exe',
        
        'vlc': 'vlc.exe',
        'плеер': 'vlc.exe',
        
        'проводник': 'explorer.exe',
        'explorer': 'explorer.exe',
        'файлы': 'explorer.exe',
        
        'параметры': 'ms-settings:',
        'settings': 'ms-settings:',
        'настройки': 'ms-settings:',
    }
    
    def __init__(self):
        self.web_scraper = get_web_scraper() if get_web_scraper else None
        self.last_search_results = {}
        print("✅ Расширенный исполнитель команд инициализирован")
    
    def execute(self, command_type: str, **params) -> str:
        """Главный метод выполнения команд"""
        
        handlers = {
            # Приложения
            "open_app": self.open_app,
            "open_program": self.open_app,  # Алиас
            "close_app": self.close_app,
            
            # Файлы
            "open_file": self.open_file,
            "create_file": self.create_file,
            "create_folder": self.create_folder,
            "delete_file": self.delete_file,
            "list_files": self.list_files,
            
            # Интернет
            "search_browser": self.search_browser,
            "open_website": self.open_website,
            
            # Информация с веб-сайтов
            "get_currency": self.get_currency,
            "get_weather": self.get_weather,
            "get_news": self.get_news,
            
            # Система
            "get_system_info": self.get_system_info,
            "get_cpu_info": self.get_cpu_info,
            "get_ram_info": self.get_ram_info,
            "get_disk_info": self.get_disk_info,
            
            # Управление окнами
            "list_processes": self.list_processes,
            "kill_process": self.kill_process,
            
            # Рабочий стол
            "create_desktop_file": self.create_desktop_file,
            "open_desktop": self.open_desktop,
            
            # Расширенные команды (v3.1)
            "powershell": self.route_to_extended,
            "file_operation": self.route_to_extended,
            "system_command": self.route_to_extended,
            "run_script": self.route_to_extended,
            "open_url": self.route_to_extended,
        }
        
        handler = handlers.get(command_type)
        if handler:
            try:
                result = handler(**params)
                return result if isinstance(result, str) else str(result)
            except Exception as e:
                return f"❌ Ошибка при выполнении {command_type}: {str(e)}"
        else:
            return f"❌ Неизвестная команда: {command_type}"
    
    # ============= ПРИЛОЖЕНИЯ =============
    
    def open_app(self, name: str, args: str = "") -> str:
        """
        Открыть приложение по названию.

        Раньше здесь был единственный жёсткий APP_MAP плюс `subprocess.Popen(name,
        shell=True)` для всего остального — второе почти всегда "успешно"
        завершалось, даже если приложение не находилось (shell=True не бросает
        исключение, если команда не найдена). Теперь: APP_MAP остаётся быстрым
        путём для явно заданных алиасов (и ms-URI схем), а для всего остального —
        универсальный резолвер (app_resolver.py): реестр App Paths + нечёткий
        поиск по ярлыкам меню "Пуск", то есть работает для ЛЮБОГО установленного
        приложения без ручного добавления в список.
        """
        name_lower = name.lower().strip()

        if platform.system() != "Windows":
            try:
                subprocess.Popen([name] + (args.split() if args else []))
                return f"✅ Открыл приложение: {name}"
            except Exception as e:
                return f"❌ Не смог открыть {name}: {str(e)}"

        if name_lower in self.APP_MAP:
            executable = self.APP_MAP[name_lower]
            if executable.startswith("ms-"):
                try:
                    os.startfile(executable)
                    print(f"🚀 Открыл через APP_MAP (URI): {name} → {executable}")
                    return f"✅ Открыл приложение: {name}"
                except Exception as e:
                    print(f"⚠️ APP_MAP-URI не сработал для «{name}» ({e}), пробую универсальный поиск")
            else:
                # shell=True не бросает исключение, если программа не найдена —
                # поэтому сначала проверяем через shutil.which, что она реально
                # есть в PATH, а не молча "успешно" ничего не запускаем.
                found_path = shutil.which(executable)
                if found_path:
                    try:
                        subprocess.Popen([found_path], shell=False)
                        print(f"🚀 Открыл через APP_MAP: {name} → {found_path}")
                        return f"✅ Открыл приложение: {name}"
                    except Exception as e:
                        print(f"⚠️ APP_MAP-запуск не сработал для «{name}» ({e}), пробую универсальный поиск")
                else:
                    print(f"⚠️ APP_MAP указывает «{name}» → «{executable}», но такой программы нет в PATH — пробую универсальный поиск")

        try:
            from app_resolver import launch_app
        except ImportError:
            print("⚠️ app_resolver недоступен")
            return f"❌ Не смог найти приложение «{name}»"

        result = launch_app(name)
        if result["success"]:
            print(f"🚀 Открыл через resolver ({result['source']}): {name} → {result['matched_name']}")
            return f"✅ Открыл приложение: {result['matched_name']}"

        print(f"❌ Резолвер не нашёл «{name}»: {result['error']}")
        return f"❌ {result['error']}"
    
    def close_app(self, name: str) -> str:
        """Закрыть приложение по названию"""
        try:
            name_lower = name.lower().strip()
            
            # Получаем имя процесса
            if name_lower in self.APP_MAP:
                process_name = self.APP_MAP[name_lower].replace('.exe', '')
            else:
                process_name = name.split('.')[0]
            
            print(f"🛑 Закрываю приложение: {name}")
            
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /IM {process_name}.exe /F", shell=True)
            else:
                subprocess.run(["killall", process_name])
            
            return f"✅ Закрыл приложение: {name}"
        except Exception as e:
            return f"❌ Не смог закрыть {name}: {str(e)}"
    
    # ============= ФАЙЛЫ =============
    
    def open_file(self, path: str) -> str:
        """Открыть файл в приложении по умолчанию"""
        try:
            if not os.path.exists(path):
                return f"❌ Файл не найден: {path}"
            
            print(f"📄 Открываю файл: {path}")
            
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
            
            return f"✅ Открыл файл: {path}"
        except Exception as e:
            return f"❌ Ошибка при открытии файла: {str(e)}"
    
    def create_file(self, path: str, content: str = "", location: str = None) -> str:
        """Создать файл"""
        try:
            # Если нужно создать на рабочем столе
            if location == 'desktop':
                desktop = Path.home() / "Desktop"
                path = desktop / Path(path).name
            
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"📝 Создал файл: {path}")
            return f"✅ Создал файл: {path}"
        except Exception as e:
            return f"❌ Ошибка при создании файла: {str(e)}"
    
    def create_folder(self, path: str) -> str:
        """Создать папку"""
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            print(f"📁 Создал папку: {path}")
            return f"✅ Создал папку: {path}"
        except Exception as e:
            return f"❌ Ошибка при создании папки: {str(e)}"
    
    def delete_file(self, path: str) -> str:
        """Удалить файл"""
        try:
            if not os.path.exists(path):
                return f"❌ Файл не найден: {path}"
            
            os.remove(path)
            print(f"🗑️ Удалил файл: {path}")
            return f"✅ Удалил файл: {path}"
        except Exception as e:
            return f"❌ Ошибка при удалении файла: {str(e)}"
    
    def list_files(self, path: str = ".", limit: int = 10) -> str:
        """Список файлов в папке"""
        try:
            files = []
            for item in Path(path).iterdir():
                if item.is_file():
                    files.append(f"📄 {item.name}")
                else:
                    files.append(f"📁 {item.name}/")
            
            result = "\n".join(files[:limit])
            if len(files) > limit:
                result += f"\n... и ещё {len(files) - limit}"
            
            return result if result else "📭 Папка пуста"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    def create_desktop_file(self, filename: str, content: str = "") -> str:
        """Создать файл на рабочем столе"""
        desktop = Path.home() / "Desktop"
        desktop.mkdir(exist_ok=True)
        
        filepath = desktop / filename
        return self.create_file(str(filepath), content)
    
    def open_desktop(self) -> str:
        """Открыть папку рабочего стола"""
        desktop = Path.home() / "Desktop"
        return self.open_file(str(desktop))
    
    # ============= ИНТЕРНЕТ =============
    
    def search_browser(self, query: str) -> str:
        """Поиск в браузере (Google)"""
        try:
            print(f"🔍 Ищу в браузере: {query}")
            url = f"https://www.google.com/search?q={query}"
            webbrowser.open(url)
            return f"✅ Ищу в браузере: {query}"
        except Exception as e:
            return f"❌ Ошибка при поиске: {str(e)}"
    
    def open_website(self, url: str) -> str:
        """Открыть сайт"""
        try:
            if not url.startswith("http"):
                url = f"https://{url}"
            
            print(f"🌐 Открываю сайт: {url}")
            webbrowser.open(url)
            
            return f"✅ Открыл сайт: {url}"
        except Exception as e:
            return f"❌ Ошибка при открытии сайта: {str(e)}"
    
    # ============= ВЕБ-ИНФОРМАЦИЯ =============
    
    def get_currency(self, currency: str = "dollar") -> str:
        """Получить курс валюты"""
        if not self.web_scraper:
            return "❌ Веб-скрейпер недоступен"
        
        try:
            currency = currency.lower().strip()
            
            if currency in ['доллар', 'dollar', 'usd', '$']:
                result = self.web_scraper.get_dollar_rate()
            elif currency in ['евро', 'euro', 'eur', '€']:
                result = self.web_scraper.get_euro_rate()
            elif currency in ['bitcoin', 'биткоин', 'btc']:
                result = self.web_scraper.get_bitcoin_price()
            else:
                result = self.web_scraper.get_dollar_rate()  # Default
            
            if result.get('status') == 'success':
                if 'rate' in result:
                    rate = result['rate']
                    return f"✅ {result['currency']}: {rate:.2f} RUB (Источник: {result.get('source', 'N/A')})"
                elif 'price_usd' in result:
                    return f"✅ Bitcoin: ${result['price_usd']} / {result['price_rub']} RUB"
            else:
                return f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}"
        except Exception as e:
            return f"❌ Ошибка при получении курса: {str(e)}"
    
    def get_weather(self, city: str = "Moscow") -> str:
        """Получить погоду"""
        if not self.web_scraper:
            return "❌ Веб-скрейпер недоступен"
        
        try:
            result = self.web_scraper.get_weather(city)
            
            if result.get('status') == 'success':
                temp = result['temperature']
                weather = result['weather']
                wind = result['wind_speed']
                return f"✅ В городе {city}: {temp}°C, {weather}. Ветер: {wind} м/с"
            else:
                return f"❌ Ошибка: {result.get('message')}"
        except Exception as e:
            return f"❌ Ошибка при получении погоды: {str(e)}"
    
    def get_news(self, topic: str = "technology") -> str:
        """Получить новости"""
        if not self.web_scraper:
            return "❌ Веб-скрейпер недоступен"
        
        try:
            result = self.web_scraper.get_news(topic)
            
            if result.get('status') == 'success':
                news = result['news']
                if not news:
                    return "ℹ️ Новостей не найдено"
                
                output = f"📰 Новости по теме '{topic}':\n"
                for i, article in enumerate(news[:3], 1):
                    output += f"\n{i}. {article['title']}\n"
                    output += f"   {article['description'][:100]}...\n"
                
                return output
            else:
                return f"❌ Ошибка: {result.get('message')}"
        except Exception as e:
            return f"❌ Ошибка при получении новостей: {str(e)}"
    
    # ============= СИСТЕМА =============
    
    def get_system_info(self) -> str:
        """Получить информацию о системе"""
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            
            # GPU информация
            gpu_info = "N/A"
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_info = f"{gpus[0].load * 100:.1f}%"
            except:
                pass
            
            output = f"💻 Информация о системе:\n"
            output += f"CPU: {cpu:.1f}%\n"
            output += f"RAM: {ram:.1f}%\n"
            output += f"Disk: {disk:.1f}%\n"
            output += f"GPU: {gpu_info}"
            
            return output
        except Exception as e:
            return f"❌ Ошибка при получении информации: {str(e)}"
    
    def get_cpu_info(self) -> str:
        """Получить информацию о CPU"""
        try:
            cpu_count = psutil.cpu_count()
            cpu_percent = psutil.cpu_percent(interval=1)
            freq = psutil.cpu_freq()
            
            return f"CPU: {cpu_count} ядер, {cpu_percent:.1f}% нагрузки, {freq.current:.0f} MHz"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    def get_ram_info(self) -> str:
        """Получить информацию об ОЗУ"""
        try:
            ram = psutil.virtual_memory()
            
            used_gb = ram.used / (1024 ** 3)
            total_gb = ram.total / (1024 ** 3)
            
            return f"RAM: {used_gb:.1f}/{total_gb:.1f} GB ({ram.percent:.1f}%)"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    def get_disk_info(self) -> str:
        """Получить информацию о диске"""
        try:
            disk = psutil.disk_usage('/')
            
            used_gb = disk.used / (1024 ** 3)
            total_gb = disk.total / (1024 ** 3)
            
            return f"Диск: {used_gb:.1f}/{total_gb:.1f} GB ({disk.percent:.1f}%)"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    # ============= ПРОЦЕССЫ =============
    
    def list_processes(self, limit: int = 10) -> str:
        """Список запущенных процессов"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    processes.append((proc.info['name'], proc.info['cpu_percent']))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            processes.sort(key=lambda x: x[1], reverse=True)
            
            output = "🔄 Топ процессов по CPU:\n"
            for i, (name, cpu) in enumerate(processes[:limit], 1):
                output += f"{i}. {name}: {cpu:.1f}%\n"
            
            return output
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    def kill_process(self, name: str) -> str:
        """Закрыть процесс по названию"""
        try:
            found = False
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if name.lower() in proc.info['name'].lower():
                        proc.kill()
                        found = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if found:
                return f"✅ Закрыл процесс(ы): {name}"
            else:
                return f"❌ Процесс не найден: {name}"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    # ============= МАРШРУТИЗАЦИЯ В РАСШИРЕННЫЙ ИСПОЛНИТЕЛЬ =============
    
    def route_to_extended(self, command_type: str = "", **params) -> str:
        """
        Маршрутизировать команду в расширенный исполнитель
        """
        if not HAS_EXTENDED or not get_extended_executor:
            return "❌ Расширенный исполнитель не доступен"
        
        try:
            executor = get_extended_executor()
            
            # Маршрутизировать по типам команд
            if command_type == 'powershell':
                command = params.get('main_param', '')
                result = executor.execute_powershell(command)
                return f"✅ {result.get('output', '')}" if result['success'] else f"❌ {result.get('error', '')}"
            
            elif command_type == 'file_operation':
                main_param = params.get('main_param', '')
                if 'open_folder' in main_param:
                    result = executor.open_folder(params.get('path', '.'))
                elif 'delete_file' in main_param:
                    result = executor.delete_file(params.get('path', ''))
                elif 'copy_file' in main_param:
                    result = executor.copy_file(params.get('src', ''), params.get('dest', ''))
                else:
                    result = {'success': False, 'error': 'Неизвестная операция с файлами'}
                
                return f"✅ {result.get('message', '')}" if result['success'] else f"❌ {result.get('error', '')}"
            
            elif command_type == 'system_command':
                main_param = params.get('main_param', '')
                if main_param == 'volume_up':
                    result = executor.volume_up()
                elif main_param == 'volume_down':
                    result = executor.volume_down()
                elif main_param == 'brightness_up':
                    result = executor.brightness_up()
                elif main_param == 'brightness_down':
                    result = executor.brightness_down()
                elif main_param == 'sleep':
                    result = executor.sleep_system()
                elif main_param == 'restart':
                    result = executor.restart_system()
                elif main_param == 'shutdown':
                    result = executor.shutdown_system()
                else:
                    result = {'success': False, 'error': 'Неизвестная системная команда'}
                
                return f"✅ {result.get('message', '')}" if result['success'] else f"❌ {result.get('error', '')}"
            
            elif command_type == 'open_url':
                url = params.get('main_param', '')
                result = executor.open_url(url)
                return f"✅ {result.get('message', '')}" if result['success'] else f"❌ {result.get('error', '')}"
            
            elif command_type == 'run_script':
                script_lang = params.get('main_param', 'python')
                result = executor.execute_powershell(f"python script.py" if script_lang == 'python' else f"node script.js")
                return f"✅ {result.get('output', '')}" if result['success'] else f"❌ {result.get('error', '')}"
            
            else:
                return f"❌ Неизвестный тип расширенной команды: {command_type}"
        
        except Exception as e:
            return f"❌ Ошибка при выполнении расширенной команды: {str(e)}"


def get_command_executor() -> CommandExecutor:
    """Factory функция для получения исполнителя команд"""
    return CommandExecutor()
