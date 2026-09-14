"""
Мост в Telegram: команды Scott из любой точки, без своего сервера.

ЗАЧЕМ ИМЕННО ТАК. Телефон в дороге и компьютер дома друг друга не видят: у
большинства провайдеров нет белого адреса, а открывать домашнюю машину наружу
нельзя. Нужен посредник, к которому компьютер подключается САМ, изнутри.

Обычно для этого заводят свой сервер. Telegram даёт то же самое даром: Scott
опрашивает его исходящими запросами, ничего не открывая наружу, — и получает
сообщения, отправленные хоть с другого конца света.

ЧЕГО ЗДЕСЬ НЕТ. Мост не решает, что можно делать издалека, и не проверяет, кто
прислал команду: это дело remote_access, общее для всех способов связи. Здесь
только доставка — принять сообщение и отдать ответ.

ПРО БЕЗОПАСНОСТЬ ЧЕСТНО. Токен бота — ключ от вашего Scott. Кто владеет
токеном, тот может писать боту от его имени; поэтому команды принимаются ТОЛЬКО
от привязанных чатов, а привязка делается кодом с экрана компьютера. Потерянный
токен отзывается в BotFather — и мост замолкает.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from . import remote_access
except ImportError:
    import remote_access

API = "https://api.telegram.org/bot{token}/{method}"

# Сколько держать соединение, ожидая сообщений.
#
# Telegram сам отдаёт ответ, как только появится сообщение, поэтому долгое
# ожидание не стоит нам ничего — зато команда приходит сразу, а не через
# интервал опроса. Тридцать секунд — рекомендованное значение.
LONG_POLL_SECONDS = 30

# Пауза после ошибки связи. Без неё при отключённом интернете мост молотил бы
# запросами вхолостую.
ERROR_PAUSE = 5


class TelegramBridge:
    """
    Связь с Telegram: получает команды, отдаёт ответы.

    Живёт в отдельном потоке, потому что ожидание сообщений долгое, а backend в
    это время должен отвечать на всё остальное.
    """

    def __init__(self, token: str, handle: Callable[[str, Dict], str]):
        """
        `handle` получает текст команды и устройство, а возвращает ответ
        человеку. Всё решение о том, можно ли эту команду выполнить, принимается
        там: мост нарочно ничего об этом не знает.
        """
        self._token = (token or "").strip()
        self._handle = handle

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._offset = 0

        self.last_error = ""
        self.username = ""

    # ---- жизнь моста ----

    @property
    def configured(self) -> bool:
        return bool(self._token) and requests is not None

    @property
    def running(self) -> bool:
        return self._running

    def check(self) -> Dict:
        """
        Проверить токен и узнать имя бота.

        Отдельно от запуска: человек, вставивший токен, должен сразу увидеть,
        принят он или нет, — а не гадать, почему ничего не приходит.
        """
        if not self.configured:
            return {"success": False, "error": "Не указан токен бота"}

        try:
            ответ = requests.get(API.format(token=self._token, method="getMe"), timeout=10)
            данные = ответ.json()
        except Exception as e:
            return {"success": False, "error": f"Telegram недоступен: {e}"}

        if not данные.get("ok"):
            return {"success": False, "error": "Telegram не принял токен"}

        self.username = данные["result"].get("username", "")
        return {"success": True, "username": self.username}

    def start(self) -> Dict:
        if not self.configured:
            return {"success": False, "error": "Не указан токен бота"}

        if self._running:
            return {"success": True, "note": "Мост уже работает"}

        проверка = self.check()
        if not проверка.get("success"):
            return проверка

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telegram-bridge")
        self._thread.start()

        return {"success": True, "username": self.username}

    def stop(self) -> None:
        self._running = False

    # ---- разговор с Telegram ----

    def send(self, chat_id, text: str) -> bool:
        """Ответить в чат. Молча не падаем: доставка ответа не должна ронять мост."""
        if not self.configured:
            return False

        try:
            requests.post(
                API.format(token=self._token, method="sendMessage"),
                json={"chat_id": chat_id, "text": text[:4000]},
                timeout=10,
            )
            return True
        except Exception as e:
            self.last_error = f"не удалось ответить: {e}"
            return False

    def _loop(self) -> None:
        while self._running:
            try:
                ответ = requests.get(
                    API.format(token=self._token, method="getUpdates"),
                    params={"offset": self._offset, "timeout": LONG_POLL_SECONDS},
                    timeout=LONG_POLL_SECONDS + 10,
                )
                данные = ответ.json()
            except Exception as e:
                self.last_error = str(e)
                time.sleep(ERROR_PAUSE)
                continue

            if not данные.get("ok"):
                self.last_error = "Telegram отказал в обновлениях"
                time.sleep(ERROR_PAUSE)
                continue

            self.last_error = ""

            for обновление in данные.get("result", []):
                self._offset = обновление["update_id"] + 1

                try:
                    self._handle_update(обновление)
                except Exception as e:
                    # Одно неудачное сообщение не должно ронять мост: следующее
                    # может оказаться важным.
                    self.last_error = f"сообщение не обработано: {e}"

    def _handle_update(self, обновление: Dict) -> None:
        сообщение = обновление.get("message") or обновление.get("edited_message")
        if not сообщение:
            return

        текст = (сообщение.get("text") or "").strip()
        if not текст:
            return

        чат = сообщение["chat"]["id"]
        имя = (сообщение.get("from", {}).get("first_name") or "Телефон").strip()

        # ---- привязка ----
        #
        # Первое, что делает человек: присылает код с экрана компьютера. До
        # этого никакие команды не принимаются — и это главная защита моста.
        if текст.startswith("/start") or текст.isdigit():
            код = текст.replace("/start", "").strip()

            if not код:
                self.send(чат, "Привет! Пришлите код привязки — он показан "
                               "в Scott на компьютере, в разделе «Удалённо».")
                return

            итог = remote_access.pair(код, имя, channel="telegram", address=чат)

            if итог.get("success"):
                self.send(чат, f"Готово. Теперь вы можете командовать Scott отсюда.\n\n"
                               f"Например: «открой браузер» или «что у меня с диском».")
            else:
                self.send(чат, f"Не вышло: {итог.get('error')}")
            return

        # ---- команда ----
        устройство = remote_access.find_by_address("telegram", чат)

        if устройство is None:
            self.send(чат, "Этот чат не привязан. Откройте Scott на компьютере, "
                           "раздел «Удалённо», и пришлите показанный там код.")
            return

        if not remote_access.within_rate_limit(устройство["id"]):
            self.send(чат, "Слишком много команд подряд — подождите минуту.")
            return

        remote_access.touch(устройство["id"])

        ответ = self._handle(текст, устройство)
        self.send(чат, ответ)


# ==================== Один мост на процесс ====================

_bridge: Optional[TelegramBridge] = None


def get_bridge() -> Optional[TelegramBridge]:
    return _bridge


def setup(handle: Callable[[str, Dict], str], token: str = "") -> Optional[TelegramBridge]:
    """
    Поднять мост, если есть токен.

    Токен берётся из настроек или из окружения: человеку удобнее вставить его в
    лаунчере, но в .env он тоже уместен — там же лежат остальные ключи.
    """
    global _bridge

    ключ = (token or remote_access.get_token()).strip()
    if not ключ:
        return None

    if _bridge is not None:
        _bridge.stop()

    _bridge = TelegramBridge(ключ, handle)
    return _bridge
