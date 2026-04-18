"""Система управления ПК для Скотта."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import subprocess
import sys
import time
import webbrowser

from .activity_coach import ActivityCoach
from .assistant_memory import AssistantMemory
from .app_discovery import find_app_command
from .assistant_phrases import phrase_for_action
from .game_policy import GameMode, GamePolicy, GameSession


@dataclass
class SystemCommandResult:
    handled: bool
    message: str = ""


class SystemController:
    """Контроллер системных команд для Windows."""

    def __init__(
        self,
        offline_game_limit_minutes: int = 90,
        advice_cooldown_minutes: int = 20,
        enable_power_confirmation: bool = True,
        memory_path: Optional[Path] = None,
        user_name: str = "",
        user_title: str = "сэр",
    ) -> None:
        self.desktop = Path.home() / "OneDrive" / "Рабочий стол"
        if not self.desktop.exists():
            self.desktop = Path.home() / "Desktop"
        self.project_root = self.desktop / "neyro"

        self.known_folders = {
            "рабочий стол": self.desktop,
            "проект": self.project_root,
        }
        self.known_sites = {
            "youtube": "https://www.youtube.com",
            "ютуб": "https://www.youtube.com",
            "google": "https://www.google.com",
            "гугл": "https://www.google.com",
            "github": "https://github.com",
            "почта": "https://mail.google.com",
        }

        self.power_confirmation_enabled = enable_power_confirmation
        self.pending_power_action: Optional[str] = None
        self.pending_power_until: float = 0.0

        self.game_policy = GamePolicy(offline_limit_minutes=offline_game_limit_minutes)
        self.activity_coach = ActivityCoach(
            advice_cooldown_minutes=advice_cooldown_minutes,
            offline_game_limit_minutes=offline_game_limit_minutes,
        )
        self.current_game: Optional[GameSession] = None
        self.memory = AssistantMemory(memory_path or (Path("./data") / "assistant_profile.json"))
        self.pending_work_offer: bool = False
        self.waiting_work_topic: bool = False
        self.user_name = (user_name or "").strip()
        self.user_title = (user_title or "сэр").strip()

    def handle_command(self, text: str) -> SystemCommandResult:
        t = (text or "").lower().strip()
        # Быстрая нормализация частых ASR-искажений команд.
        t = (
            t.replace("откроет ", "открой ")
            .replace("заблокирует ", "заблокируй ")
            .replace("видит поиск ", "поиск ")
            .replace("видишь поиск ", "поиск ")
        )
        if not t:
            return SystemCommandResult(False, "")

        confirm = self._handle_power_confirmation(t)
        if confirm is not None:
            return confirm
        coaching = self._handle_coaching_dialog(t)
        if coaching is not None:
            return coaching

        if self._looks_like_open_site(t):
            return self._handle_open_site(t)
        if "найди в интернете" in t or "поиск в интернете" in t or t.startswith("поиск "):
            query = (
                t.replace("найди в интернете", "")
                .replace("поиск в интернете", "")
                .replace("поиск", "", 1)
                .strip()
            )
            return self._handle_web_search(query)
        web_question = self._extract_web_question(t)
        if web_question:
            return self._handle_web_search(web_question, open_in_chrome=True)

        if any(k in t for k in ("сделай громче", "прибавь громкость", "увеличь громкость")):
            return self._handle_volume("up")
        if any(k in t for k in ("сделай тише", "убавь громкость", "уменьши громкость")):
            return self._handle_volume("down")
        if any(k in t for k in ("выключи звук", "отключи звук", "без звука")):
            return self._handle_volume("mute")

        if "сверни все окна" in t or "покажи рабочий стол" in t:
            return self._handle_show_desktop()
        if "закрой окно" in t or "закрой текущее окно" in t:
            return self._handle_close_window()
        if "переключись на следующее окно" in t or "переключи окно" in t:
            return self._handle_next_window()
        if "сверни окно" in t or "минимизируй окно" in t:
            return self._handle_minimize_window()
        if "разверни окно" in t or "максимизируй окно" in t:
            return self._handle_maximize_window()
        if "на весь экран" in t or "полный экран" in t:
            return self._handle_fullscreen()
        if "закрепи слева" in t or t == "влево":
            return self._handle_snap("left")
        if "закрепи справа" in t or t == "вправо":
            return self._handle_snap("right")

        if any(k in t for k in ("пауза", "поставь на паузу", "продолжи", "воспроизведение")):
            return self._handle_media("play_pause")
        if "следующий трек" in t or "следующая песня" in t:
            return self._handle_media("next")
        if "предыдущий трек" in t or "предыдущая песня" in t:
            return self._handle_media("prev")

        if "перезагрузи компьютер" in t or "перезагрузка" in t:
            return self._handle_shutdown("restart")
        if "выключи компьютер" in t or "выключение" in t:
            return self._handle_shutdown("shutdown")
        if "режим сна" in t or "усыпи компьютер" in t:
            return self._handle_shutdown("sleep")
        if "режим гибернации" in t or "гибернация" in t:
            return self._handle_shutdown("hibernate")
        if "заблокируй экран" in t or "заблокировать экран" in t:
            return self._handle_lock_screen()
        if "создай файл" in t or "создать файл" in t:
            return self._handle_create_file(t)

        if (
            t.startswith("открой ")
            or t.startswith("запусти ")
            or " открой " in t
            or " запусти " in t
            or " включи " in t
        ):
            return self._handle_open_app_or_folder(t)

        if t.startswith("закрой игру") or t.startswith("останови игру"):
            return self._handle_stop_game(t)

        if "дай совет" in t or "что делать" in t:
            return self._handle_general_advice()
        if t.startswith("моя цель ") or t.startswith("запомни цель "):
            goal = t.replace("моя цель", "", 1).replace("запомни цель", "", 1).strip()
            return self._remember_goal(goal)

        return SystemCommandResult(False, "")

    def poll_activity(self) -> Optional[SystemCommandResult]:
        if not self.current_game:
            return None
        decision = self.game_policy.evaluate(self.current_game)
        if decision.should_stop and self.current_game.mode is GameMode.OFFLINE:
            self._close_active_window()
            self.current_game = None
            self.pending_work_offer = True
            return SystemCommandResult(
                True,
                f"{phrase_for_action('game_stop')} Я остановил игру. Вы слишком долго играли. Не желаете поработать?",
            )
        if decision.should_advise and self.activity_coach.can_speak():
            self.activity_coach.mark_spoken()
            self.pending_work_offer = True
            return SystemCommandResult(
                True,
                f"{phrase_for_action('advice')} Вы слишком долго играете. Такими темпами вы отдаляетесь от целей. Не желаете поработать?",
            )
        return None

    def _respond(self, action: str, details: str) -> SystemCommandResult:
        address = self._user_address()
        msg = f"{phrase_for_action(action)} {details}".strip()
        if address and address not in msg.lower():
            msg = f"{msg} {address}."
        return SystemCommandResult(True, msg.strip())

    def _user_address(self) -> str:
        if self.user_name:
            return self.user_name
        return self.user_title

    def _looks_like_open_site(self, text: str) -> bool:
        triggers = ("открой сайт", "открой страницу", "открой вкладку", "зайди на сайт", "перейди на")
        return any(k in text for k in triggers)

    def _handle_open_site(self, text: str) -> SystemCommandResult:
        for name, url in self.known_sites.items():
            if name in text:
                try:
                    webbrowser.open(url)
                    return self._respond("site_open", f"Открываю сайт {name}.")
                except Exception as exc:
                    return self._respond("error", f"Не удалось открыть сайт {name}: {exc}")

        candidate = text
        for token in ("открой сайт", "открой страницу", "открой вкладку", "зайди на сайт", "перейди на"):
            candidate = candidate.replace(token, "")
        candidate = candidate.strip()
        if not candidate:
            return self._respond("advice", "Уточни сайт, например: открой сайт github.")

        if "." not in candidate and " " not in candidate:
            candidate = f"https://{candidate}.com"
        elif not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"

        try:
            webbrowser.open(candidate)
            return self._respond("site_open", f"Открываю {candidate}.")
        except Exception as exc:
            return self._respond("error", f"Не удалось открыть сайт: {exc}")

    def _handle_web_search(self, query: str, open_in_chrome: bool = False) -> SystemCommandResult:
        if not query:
            return self._respond("advice", "Скажи, что именно искать в интернете.")
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        try:
            if open_in_chrome:
                self._open_google_chrome_with_url(url)
            else:
                webbrowser.open(url)
            return self._respond("site_open", f"Ищу в Google: {query}.")
        except Exception as exc:
            return self._respond("error", f"Не удалось выполнить поиск: {exc}")

    def _handle_open_app_or_folder(self, text: str) -> SystemCommandResult:
        for name, path in self.known_folders.items():
            if name in text and path.exists():
                try:
                    os.startfile(str(path))
                    return self._respond("open", f"Открываю папку {name}.")
                except Exception as exc:
                    return self._respond("error", f"Не удалось открыть папку {name}: {exc}")

        raw_query = (
            text.replace("открой", "")
            .replace("запусти", "")
            .replace("включи", "")
            .replace("программу", "")
            .replace("приложение", "")
            .strip()
        )
        if not raw_query:
            return self._respond("advice", "Уточни приложение, которое нужно запустить.")

        game_mode = self._extract_game_mode(text)
        if self._is_game_query(raw_query):
            if game_mode is GameMode.ONLINE:
                self.activity_coach.mark_online_start_warning()

        match = find_app_command(raw_query)
        if not match:
            return self._respond("error", f"Не нашел приложение {raw_query}.")
        try:
            cmd = match.command
            if isinstance(cmd, str) and cmd.lower().endswith(".lnk") and os.path.exists(cmd):
                os.startfile(cmd)
            elif isinstance(cmd, str) and os.path.exists(cmd) and not cmd.lower().endswith(".exe"):
                os.startfile(cmd)
            else:
                subprocess.Popen(cmd)
        except Exception as exc:
            return self._respond("error", f"Не удалось запустить {raw_query}: {exc}")

        if self._is_game_query(raw_query):
            self.current_game = GameSession(
                name=raw_query,
                mode=game_mode,
                started_at=time.time(),
            )
            decision = self.game_policy.pre_start_message(self.current_game)
            if decision:
                return self._respond("game_start", decision)
            return self._respond("game_start", f"Запускаю игру {raw_query}.")

        return self._respond("open", f"Запускаю {raw_query}.")

    def _handle_create_file(self, text: str) -> SystemCommandResult:
        """
        Быстрый системный интент: создание файла без ухода в LLM.
        Пример: "создай файл test.txt на рабочем столе"
        """
        raw = (
            text.replace("создай файл", "", 1)
            .replace("создать файл", "", 1)
            .replace("на рабочем столе", "")
            .replace("в рабочем столе", "")
            .strip(" .,!?:;")
        )
        if not raw:
            raw = "new_file.txt"
        if "." not in raw:
            raw = f"{raw}.txt"
        safe_name = "".join(ch for ch in raw if ch not in '<>:"/\\|?*').strip()
        if not safe_name:
            safe_name = "new_file.txt"
        target = self.desktop / safe_name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)
            return self._respond("open", f"Файл создан: {target.name}.")
        except Exception as exc:
            return self._respond("error", f"Не удалось создать файл: {exc}")

    def _handle_stop_game(self, text: str) -> SystemCommandResult:
        if not self.current_game:
            self._close_active_window()
            return self._respond("game_stop", "Останавливаю активную игру.")
        decision = self.game_policy.can_stop_by_command(self.current_game)
        if not decision.allowed:
            return self._respond("advice", decision.message)
        self._close_active_window()
        stopped_name = self.current_game.name
        self.current_game = None
        return self._respond("game_stop", f"Останавливаю {stopped_name}.")

    def _handle_power_confirmation(self, text: str) -> Optional[SystemCommandResult]:
        if not self.pending_power_action:
            return None
        if time.time() > self.pending_power_until:
            self.pending_power_action = None
            return self._respond("advice", "Подтверждение устарело. Повтори команду питания.")
        if any(k in text for k in ("подтверждаю", "да", "выполняй")):
            action = self.pending_power_action
            self.pending_power_action = None
            return self._execute_shutdown(action)
        if any(k in text for k in ("отмена", "не надо", "стоп")):
            self.pending_power_action = None
            return self._respond("cancel", "Команда питания отменена.")
        return self._respond("advice", "Скажи 'подтверждаю' или 'отмена'.")

    def _handle_shutdown(self, action: str) -> SystemCommandResult:
        if not self.power_confirmation_enabled:
            return self._execute_shutdown(action)
        self.pending_power_action = action
        self.pending_power_until = time.time() + 20.0
        return self._respond("confirm", "Подтверди команду: скажи 'подтверждаю' или 'отмена'.")

    def _execute_shutdown(self, action: str) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Команды питания поддерживаются только в Windows.")
        commands = {
            "shutdown": ["shutdown", "/s", "/t", "0"],
            "restart": ["shutdown", "/r", "/t", "0"],
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "hibernate": ["shutdown", "/h"],
        }
        messages = {
            "shutdown": "Выключаю компьютер.",
            "restart": "Перезагружаю компьютер.",
            "sleep": "Перевожу компьютер в режим сна.",
            "hibernate": "Перевожу компьютер в гибернацию.",
        }
        try:
            subprocess.Popen(commands[action], shell=False)
            return self._respond("power", messages[action])
        except Exception as exc:
            return self._respond("error", f"Не удалось выполнить команду питания: {exc}")

    def _handle_lock_screen(self) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Блокировка экрана поддерживается только в Windows.")
        try:
            import ctypes

            ctypes.windll.user32.LockWorkStation()
            return self._respond("lock", "Блокирую экран.")
        except Exception as exc:
            return self._respond("error", f"Не удалось заблокировать экран: {exc}")

    def _handle_volume(self, action: str) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Команда громкости поддерживается только в Windows.")
        try:
            import ctypes

            user32 = ctypes.windll.user32
            keys = {"mute": 0xAD, "down": 0xAE, "up": 0xAF}
            vk = keys[action]
            repeats = 5 if action in ("down", "up") else 1
            for _ in range(repeats):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, 2, 0)
            messages = {"mute": "Отключаю звук.", "up": "Делаю громче.", "down": "Делаю тише."}
            return self._respond("media", messages[action])
        except Exception as exc:
            return self._respond("error", f"Не удалось изменить громкость: {exc}")

    def _handle_show_desktop(self) -> SystemCommandResult:
        return self._press_win_arrow("d", "Показываю рабочий стол.")

    def _handle_close_window(self) -> SystemCommandResult:
        if self.current_game and self.current_game.mode is GameMode.ONLINE:
            return self._respond("advice", "Онлайн-игру после старта не закрываю автоматически.")
        self._close_active_window()
        return self._respond("window", "Закрываю текущее окно.")

    def _close_active_window(self) -> None:
        if not sys.platform.startswith("win"):
            return
        import ctypes

        user32 = ctypes.windll.user32
        vk_alt = 0x12
        vk_f4 = 0x73
        user32.keybd_event(vk_alt, 0, 0, 0)
        user32.keybd_event(vk_f4, 0, 0, 0)
        user32.keybd_event(vk_f4, 0, 2, 0)
        user32.keybd_event(vk_alt, 0, 2, 0)

    def _handle_next_window(self) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Переключение окон поддерживается только в Windows.")
        try:
            import ctypes

            user32 = ctypes.windll.user32
            vk_alt = 0x12
            vk_tab = 0x09
            user32.keybd_event(vk_alt, 0, 0, 0)
            user32.keybd_event(vk_tab, 0, 0, 0)
            user32.keybd_event(vk_tab, 0, 2, 0)
            user32.keybd_event(vk_alt, 0, 2, 0)
            return self._respond("window", "Переключаю окно.")
        except Exception as exc:
            return self._respond("error", f"Не удалось переключить окно: {exc}")

    def _handle_minimize_window(self) -> SystemCommandResult:
        return self._press_win_arrow("down", "Сворачиваю текущее окно.")

    def _handle_maximize_window(self) -> SystemCommandResult:
        return self._press_win_arrow("up", "Разворачиваю окно.")

    def _handle_fullscreen(self) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Полноэкранный режим поддерживается только в Windows.")
        try:
            import ctypes

            user32 = ctypes.windll.user32
            vk = 0x7A
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)
            return self._respond("window", "Переключаю полный экран.")
        except Exception as exc:
            return self._respond("error", f"Не удалось включить полноэкранный режим: {exc}")

    def _handle_snap(self, side: str) -> SystemCommandResult:
        direction = "left" if side == "left" else "right"
        msg = "Закрепляю окно слева." if direction == "left" else "Закрепляю окно справа."
        return self._press_win_arrow(direction, msg)

    def _press_win_arrow(self, direction: str, ok_message: str) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Управление окнами поддерживается только в Windows.")
        try:
            import ctypes

            if direction == "d":
                vk = 0x44
            else:
                vk = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}.get(direction)
            if vk is None:
                return self._respond("error", "Неизвестное направление.")
            user32 = ctypes.windll.user32
            vk_win = 0x5B
            user32.keybd_event(vk_win, 0, 0, 0)
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)
            user32.keybd_event(vk_win, 0, 2, 0)
            return self._respond("window", ok_message)
        except Exception as exc:
            return self._respond("error", f"Не удалось выполнить оконную команду: {exc}")

    def _handle_media(self, action: str) -> SystemCommandResult:
        if not sys.platform.startswith("win"):
            return self._respond("error", "Медиа-команды поддерживаются только в Windows.")
        try:
            import ctypes

            user32 = ctypes.windll.user32
            vk_map = {"play_pause": 0xB3, "next": 0xB0, "prev": 0xB1}
            vk = vk_map[action]
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)
            messages = {
                "play_pause": "Переключаю воспроизведение.",
                "next": "Следующий трек.",
                "prev": "Предыдущий трек.",
            }
            return self._respond("media", messages[action])
        except Exception as exc:
            return self._respond("error", f"Не удалось выполнить медиа-команду: {exc}")

    def _extract_game_mode(self, text: str) -> GameMode:
        if any(k in text for k in ("офлайн", "offline", "одиноч", "singleplayer")):
            return GameMode.OFFLINE
        if any(k in text for k in ("онлайн", "online", "мультиплеер", "multiplayer")):
            return GameMode.ONLINE
        return GameMode.UNKNOWN

    def _is_game_query(self, query: str) -> bool:
        markers = ("игр", "game", "steam", "epic", "cs2", "dota", "minecraft", "gta", "witcher")
        q = query.lower()
        return any(m in q for m in markers)

    def _extract_web_question(self, text: str) -> Optional[str]:
        """
        Вопросы, требующие актуальных данных из интернета.
        Пример: "какой сейчас курс доллара".
        """
        realtime_markers = (
            "курс доллара",
            "курс евро",
            "курс валют",
            "погода",
            "новости",
            "цена",
            "сколько стоит",
        )
        question_prefixes = ("какой", "какая", "какие", "сколько", "что", "где", "когда")
        cleaned = text.strip(" ?!.")
        if any(m in cleaned for m in realtime_markers):
            return cleaned
        if cleaned.startswith(question_prefixes) and "сейчас" in cleaned:
            return cleaned
        return None

    def _open_google_chrome_with_url(self, url: str) -> None:
        chrome_match = find_app_command("chrome")
        if chrome_match:
            cmd = chrome_match.command
            if isinstance(cmd, str):
                subprocess.Popen([cmd, url])
            else:
                subprocess.Popen(cmd + [url])  # type: ignore[operator]
            return
        webbrowser.open(url)

    def _handle_coaching_dialog(self, text: str) -> Optional[SystemCommandResult]:
        yes_words = ("да", "ага", "конечно", "давай", "согласен", "поехали")
        no_words = ("нет", "не хочу", "потом", "не сейчас", "отмена")

        if self.pending_work_offer:
            if any(w in text for w in yes_words):
                self.pending_work_offer = False
                self.waiting_work_topic = True
                return self._respond("advice", "Отлично. С чем будем работать: код, учеба, задачи или планирование?")
            if any(w in text for w in no_words):
                self.pending_work_offer = False
                return self._respond("advice", "Принято. Тогда хотя бы сделайте короткий перерыв и глоток воды.")

        if self.waiting_work_topic:
            self.waiting_work_topic = False
            topic = self._normalize_topic(text)
            self.memory.remember_topic(topic)
            plan = self._build_focus_plan(topic)
            return self._respond("advice", plan)

        return None

    def _normalize_topic(self, text: str) -> str:
        t = text.lower()
        if "код" in t or "программ" in t or "разработ" in t:
            return "код"
        if "учеб" in t or "экзам" in t:
            return "учеба"
        if "план" in t:
            return "планирование"
        if "работ" in t or "задач" in t:
            return "задачи"
        return t.strip() or "задачи"

    def _build_focus_plan(self, topic: str) -> str:
        if topic == "код":
            return "Предлагаю режим 25 минут: открыть проект, выбрать одну задачу, и написать рабочий кусок кода без отвлечений."
        if topic == "учеба":
            return "Сделаем так: 20 минут теории, 20 минут практики, затем короткая проверка, что вы запомнили."
        if topic == "планирование":
            return "Отлично. Сначала формулируем одну главную цель на сегодня, затем разбиваем на 3 конкретных шага."
        return "Хорошо. Выберите одну конкретную задачу на 20 минут и начнем с самого простого шага."

    def _handle_general_advice(self) -> SystemCommandResult:
        last_topic = self.memory.profile.last_focus_topic
        if last_topic:
            return self._respond("advice", f"По вашему прошлому фокусу '{last_topic}' советую начать с короткой сессии 20-25 минут прямо сейчас.")
        if self.memory.profile.goals:
            return self._respond("advice", f"Ориентир на вашу цель '{self.memory.profile.goals[-1]}': сделайте один маленький шаг в ближайшие 15 минут.")
        return self._respond("advice", "Выберите одну важную задачу и выполните ее 20 минут без уведомлений.")

    def _remember_goal(self, goal: str) -> SystemCommandResult:
        if not goal:
            return self._respond("advice", "Сформулируйте цель, например: моя цель закончить модуль оплаты.")
        self.memory.remember_goal(goal)
        return self._respond("advice", f"Запомнил вашу цель: {goal}. Буду ориентировать советы на нее.")
