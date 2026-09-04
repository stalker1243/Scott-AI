"""
Мониторинг системы в реальном времени
CPU, RAM, GPU, Диск и другие метрики
"""

import os
import shutil
import psutil
from typing import Dict
import threading
import time

try:
    import GPUtil
except Exception:  # pragma: no cover - optional dependency
    GPUtil = None


class SystemMonitor:
    """Мониторинг системы"""
    
    def __init__(self):
        self.metrics = {
            "cpu": 0,
            "ram": 0,
            "gpu": 0,
            "disk": 0,
            "processes": 0,
            "network_sent": 0,
            "network_recv": 0
        }
        
        self.monitoring = False
        self.monitor_thread = None
        
        print("✅ Монитор системы инициализирован")
    
    def get_metrics(self) -> Dict[str, float]:
        """Получить текущие метрики"""
        try:
            self.metrics["cpu"] = psutil.cpu_percent(interval=0.1)
            self.metrics["ram"] = psutil.virtual_memory().percent
            disk_path = 'C:' if os.name == 'nt' else '/'
            self.metrics["disk"] = psutil.disk_usage(disk_path).percent
            self.metrics["processes"] = len(psutil.pids())
            
            # GPU (если доступна)
            try:
                if GPUtil is not None and shutil.which('nvidia-smi'):
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        self.metrics["gpu"] = max(0, min(100, gpus[0].load * 100))
                    else:
                        self.metrics["gpu"] = 0
                else:
                    self.metrics["gpu"] = 0
            except Exception:
                self.metrics["gpu"] = 0
            
            # Сеть
            net_io = psutil.net_io_counters()
            self.metrics["network_sent"] = net_io.bytes_sent
            self.metrics["network_recv"] = net_io.bytes_recv
            
            return self.metrics
            
        except Exception as e:
            print(f"⚠️ Ошибка получения метрик: {e}")
            return self.metrics
    
    def get_process_info(self, top_n: int = 5) -> list:
        """Получить информацию о топ процессах по CPU"""
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.as_dict(attrs=['pid', 'name', 'cpu_percent', 'memory_percent'])
                    processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Сортировать по CPU
            processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)
            
            return processes[:top_n]
            
        except Exception as e:
            print(f"⚠️ Ошибка получения процессов: {e}")
            return []
    
    def get_cpu_info(self) -> Dict:
        """Получить информацию о ЦП"""
        cpu_freq = psutil.cpu_freq()
        return {
            "cpu_count": psutil.cpu_count(),
            "cpu_freq": cpu_freq.current if cpu_freq else 0,
            "cpu_percent": psutil.cpu_percent(interval=0.2)
        }
    
    def get_memory_info(self) -> Dict:
        """Получить информацию об оперативной памяти"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total / (1024 ** 3),  # GB
            "used": mem.used / (1024 ** 3),
            "available": mem.available / (1024 ** 3),
            "percent": mem.percent
        }
    
    def get_disk_info(self) -> Dict:
        """Получить информацию о диске"""
        disk_path = 'C:' if os.name == 'nt' else '/'
        disk = psutil.disk_usage(disk_path)
        return {
            "total": disk.total / (1024 ** 3),  # GB
            "used": disk.used / (1024 ** 3),
            "free": disk.free / (1024 ** 3),
            "percent": disk.percent
        }
    
    def format_metrics(self) -> str:
        """Форматировать метрики для отображения"""
        m = self.get_metrics()
        
        return f"""
╔════════════════════════════════╗
║     SYSTEM METRICS             ║
├────────────────────────────────┤
│ CPU:      {m['cpu']:6.1f}%        │
│ RAM:      {m['ram']:6.1f}%        │
│ GPU:      {m['gpu']:6.1f}%        │
│ DISK:     {m['disk']:6.1f}%       │
│ PROCESS:  {int(m['processes']):5d}         │
╚════════════════════════════════╝
"""
    
    def start_monitoring(self, interval: int = 5):
        """Начать мониторинг в отдельном потоке"""
        if self.monitoring:
            return
        
        self.monitoring = True
        
        def monitor_loop():
            while self.monitoring:
                self.get_metrics()
                time.sleep(interval)
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("✅ Мониторинг начат")
    
    def stop_monitoring(self):
        """Остановить мониторинг"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        print("⏸️ Мониторинг остановлен")


# Глобальный экземпляр
_monitor = None


def get_system_monitor() -> SystemMonitor:
    """Получить глобальный экземпляр SystemMonitor"""
    global _monitor
    if _monitor is None:
        _monitor = SystemMonitor()
    return _monitor


if __name__ == "__main__":
    monitor = get_system_monitor()
    
    # Примеры
    print(monitor.format_metrics())
    print("\nТоп процессы:")
    for proc in monitor.get_process_info(3):
        print(f"  {proc['name']}: CPU {proc['cpu_percent']:.1f}%, RAM {proc['memory_percent']:.1f}%")
