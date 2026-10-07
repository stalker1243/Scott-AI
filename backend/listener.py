"""
Постоянное прослушивание микрофона с активацией по имени.

До сих пор голосового ввода в проекте не было вовсе: `/speech_to_text` умел
распознать присланный файл, но записывать звук было некому — ни backend, ни
лаунчер микрофон не трогали. Система активации по имени (`voice_name_trigger`)
при этом была написана давно и лежала мёртвым кодом.

Здесь эти две половины соединяются. Модуль слушает микрофон, сам решает, где
во входящем потоке началась и закончилась фраза, отдаёт её распознавателю и,
если человек назвал Scott по имени, выполняет команду.

Устроено на трёх нитях, и это не усложнение ради усложнения:

* **Захват** только складывает блоки в очередь — задерживать его нельзя, иначе
  звук начнёт теряться кусками.
* **Разбор** собирает из блоков фразы по уровню громкости.
* **Обработка** распознаёт и выполняет. Whisper занимает сотни миллисекунд, и
  делать это в потоке захвата означало бы глохнуть на время каждой команды.

Порог громкости не константа: тихий микрофон в наушниках и открытый микрофон
в комнате дают разный фон, поэтому уровень тишины замеряется при старте и
дальше подстраивается.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except Exception:  # pragma: no cover — на машине без звуковой подсистемы
    sd = None
    HAS_SOUNDDEVICE = False


# Whisper обучен на 16 кГц — записывать выше смысла нет, а ниже нельзя.
SAMPLE_RATE = 16000

# Блок в 30 мс: достаточно мелкий, чтобы вовремя заметить начало речи, и
# достаточно крупный, чтобы не гонять поток впустую.
BLOCK_MS = 30
BLOCK_SIZE = SAMPLE_RATE * BLOCK_MS // 1000


@dataclass
class ListenerConfig:
    """Настройки прослушивания. Значения подобраны под обычную речь."""

    # Во сколько раз громче фона должен быть звук, чтобы считаться речью.
    # Множитель, а не абсолютный порог: фон у разных микрофонов различается на
    # порядки, и одно и то же число было бы то слишком строгим, то бесполезным.
    speech_threshold: float = 3.0

    # Ниже этого уровня не реагируем даже при тихом фоне — иначе Scott начнёт
    # распознавать шорохи в полной тишине.
    absolute_floor: float = 0.006

    # Сколько подряд блоков должны быть громкими, чтобы признать начало речи.
    # Отсекает щелчки и одиночные стуки по столу.
    onset_blocks: int = 3

    # Пауза, после которой фраза считается законченной. Меньше — Scott будет
    # обрывать на вдохе, больше — заметно задумываться перед ответом. Это
    # начальное значение: дальше оно подстраивается под человека.
    silence_to_end: float = 0.8

    # Подстройка паузы под темп речи.
    #
    # Жёсткая пауза плоха для обеих сторон: кто говорит слитно, ждёт лишнюю
    # треть секунды всегда, а кому свойственно задумываться посреди фразы —
    # того Scott обрывает на вдохе и выполняет половину сказанного.
    adaptive_silence: bool = True

    # Границы подстройки. Ниже нижней Scott начнёт рубить обычную речь, выше
    # верхней — ощутимо тормозить на каждой фразе.
    min_silence_to_end: float = 0.45
    max_silence_to_end: float = 1.2

    # Шаги нарочно неравные. Обрыв — это выполненная половина команды, и
    # реакция на него резкая. Лишнее ожидание всего лишь неприятно, поэтому
    # вниз пауза сползает медленно.
    silence_step_up: float = 0.15
    silence_step_down: float = 0.03

    # Речь возобновилась быстрее этого — значит человека оборвали на вдохе.
    resume_gap: float = 0.5

    # Тишина держалась дольше этого — значит фраза кончилась сама, и паузу
    # можно было выждать короче.
    clean_gap: float = 2.0

    # Границы длины фразы: слишком короткое — случайный звук, слишком
    # длинное — разговор не с ассистентом.
    min_phrase: float = 0.35
    max_phrase: float = 15.0

    # ==================== Конец речи, а не конец звука ====================
    #
    # Фраза закрывалась по тишине — то есть по падению громкости. Пока в
    # комнате играет музыка или идёт разговор, громкость не падает никогда, и
    # запись растёт до предела в пятнадцать секунд: человек сказал «открой
    # браузер» за полторы секунды, а ждал ответа все пятнадцать. В живом
    # журнале такими оказались 429 записей из 715.
    #
    # Поэтому конец фразы определяется ещё и по тому, кончилась ли РЕЧЬ.
    # Проверка окна в секунду стоит около пяти миллисекунд, так что делать её
    # можно хоть четыре раза в секунду.

    # Сколько звука проверять за раз. Секунда — чтобы пауза на вдох не
    # сходила за конец речи: в окне остаётся сказанное до неё.
    speech_window: float = 1.0

    # Как часто проверять. Чаще — лишняя работа, реже — человек ждёт.
    speech_check_every: float = 0.25

    # Сколько держаться «речи нет», чтобы закрыть фразу. Меньше — оборвём на
    # вдохе, больше — вернёмся к ожиданию, ради избавления от которого всё и
    # затевалось.
    speech_gone_to_end: float = 0.6

    # С какой длины фразы включать проверку. Короткая команда закрывается
    # обычным путём, по тишине, и трогать этот путь незачем: он работает.
    speech_check_from: float = 2.0

    # ==================== Продолжение разговора ====================
    #
    # Сколько секунд после ответа Scott слушает продолжение без имени.
    #
    # В журнале услышанного видно, как это мешает: человек сказал «открой сайт
    # ggsl.com» сразу после разговора, Scott промолчал — имени не было, — и
    # через полминуты фразу пришлось повторять целиком.
    #
    # Десять секунд — столько длится пауза между «открой браузер» и «а теперь
    # почту». Больше — и Scott начнёт подхватывать разговор, который к нему не
    # обращён.
    followup_window: float = 10.0

    # Хвост звука перед началом речи: человек начинает говорить раньше, чем громкость
    # переваливает порог, и без этого запаса теряется первый слог — как раз тот,
    # в котором чаще всего и звучит имя.
    preroll: float = 0.4

    # Перебивание: насколько громче колонок должен говорить человек.
    #
    # Порог считается не от тишины, а от громкости самого Scott — иначе всё
    # зависело бы от того, насколько громко выкручены колонки. Меньше — Scott
    # начнёт перебивать себя сам, больше — придётся кричать.
    interrupt_threshold: float = 2.2

    # Перебивают одним-двумя словами. Всё, что длиннее, — не перебивание, а
    # обычная реплика, и разбирать её во время речи незачем.
    interrupt_max_phrase: float = 1.6

    # Пауза, после которой перебивание считается законченным. Короче обычной:
    # ждать здесь нечего, слово уже сказано.
    interrupt_silence: float = 0.35

    # Сколько начала ответа уходит на замер громкости колонок.
    #
    # Это заведомо голос Scott: так быстро человек отреагировать не успевает.
    # Замер нужен, чтобы планка перебивания встала на нужную высоту сразу, а не
    # подстраивалась по ходу — подстраиваясь, она успевала впитать голос
    # человека и переставала его слышать.
    interrupt_calibration: float = 0.35

    # Вычитать ли из записи то, что Scott произносит сам.
    #
    # Микрофон слышит колонки, и собственный ответ возвращается как новая
    # фраза. Пока этого не было, приходилось глушить микрофон почти наглухо и
    # требовать от человека говорить громче колонок.
    #
    # Замерено на речи с моделью комнаты: эхо тише на 10-12 дБ, голос человека
    # — на 0.8 дБ, расход времени около трёх процентов реального.
    cancel_echo: bool = True

    device: Optional[int] = None


@dataclass
class ListenerStats:
    """Что происходило — для вкладки диагностики и отладки."""

    phrases_heard: int = 0
    triggered: int = 0

    # Что ушло на исполнение и чем кончилось.
    #
    # Без этого на вопрос «слышит, но не отвечает» ответить нечем: счётчик
    # обращений растёт и когда команда выполнена, и когда позвали по имени,
    # ничего не попросив.
    last_command: str = ""
    last_command_at: float = 0.0
    last_dispatch: str = ""      # 'выполнена' | 'имя без команды' | 'мимо' | 'ошибка'
    ignored: int = 0
    last_text: str = ""
    last_error: str = ""
    noise_floor: float = 0.0

    # Текущая пауза и сколько раз речь возобновлялась сразу после закрытия
    # фразы. Второе — признак того, что Scott обрывал человека; по нему видно,
    # работает ли подстройка.
    silence_to_end: float = 0.0
    cutoffs: int = 0

    # Сколько раз Scott перебили и сколько раз он отверг собственное эхо.
    # Второе важно не меньше первого: по нему видно, что щель работает узко.
    interruptions: int = 0
    echo_ignored: int = 0

    # Сколько длилась последняя фраза и сколько их закрылось по пределу длины.
    #
    # Второе — главный признак того, что Scott отвечает медленно НЕ из-за
    # распознавания. Фраза, дошедшая до предела, означает, что тишина после
    # речи так и не наступила: человек сказал «открой браузер» за полторы
    # секунды, а запись шла все пятнадцать — и ровно столько он ждал ответа.
    # В живом журнале такими оказались 429 записей из 715, и замеры
    # распознавания этого не видели вовсе: они начинаются, когда запись уже
    # закрыта.
    last_phrase_seconds: float = 0.0
    closed_by_length: int = 0

    # Сколько фраз закрыла проверка речи — тех, что при прежнем порядке росли
    # бы до предела, потому что в комнате не становилось тихо.
    closed_by_speech_end: int = 0

    # Сколько прошло от конца речи до готового ответа — то самое «медленно»,
    # на которое жалуется человек. Ни один замер по этапам этого не показывал.
    last_answer_seconds: float = 0.0

    started_at: float = 0.0
    recent: List[str] = field(default_factory=list)


class VoiceListener:
    """
    Слушает микрофон и выполняет команды, обращённые к Scott по имени.

    Распознавание и обработку модуль не реализует — они передаются функциями.
    Так его можно проверить без микрофона и без Whisper, скормив заранее
    записанный звук через `feed`.
    """

    def __init__(
        self,
        transcribe: Callable[[np.ndarray], str],
        handle_command: Callable[[str], None],
        check_trigger: Optional[Callable[[str], object]] = None,
        config: Optional[ListenerConfig] = None,
        on_interrupt: Optional[Callable[[str], None]] = None,
        has_speech: Optional[Callable[[np.ndarray], bool]] = None,
        looks_like_command: Optional[Callable[[str], bool]] = None,
    ):
        self.transcribe = transcribe
        self.handle_command = handle_command
        self.check_trigger = check_trigger
        self.config = config or ListenerConfig()

        # Захват того, что звучит в колонках. Поднимается при первом блоке:
        # раньше незачем, а в конструкторе это лишний поток у слушателя,
        # которого могли создать только ради проверок.
        self._loopback = None

        # Жаловались ли уже на сломавшуюся проверку речи: она ломается на
        # каждом блоке, и без этого журнал утонет.
        self._speech_check_complained = False

        # Как узнать, звучит ли в куске звука речь.
        #
        # Передаётся снаружи, как и распознавание: слушатель не должен тянуть
        # за собой Whisper и его зависимости — тогда его не проверить без них.
        # Не передали — работает прежний путь, по громкости.
        self.has_speech = has_speech

        # Похожа ли фраза на команду — нужно для продолжения разговора.
        #
        # Сразу после ответа Scott слушает продолжение без имени, и в это окно
        # попадает всё, что сказано в комнате. Выполнять оттуда можно только
        # ДЕЙСТВИЯ: случайный вопрос из разговора рядом заставил бы Scott
        # влезть в него с ответом, а это хуже, чем промолчать.
        #
        # Передаётся снаружи, как и распознавание: слушатель не разбирает
        # смысл фраз и знать о нём не должен.
        self.looks_like_command = looks_like_command

        # Когда Scott последний раз ответил — от этого мгновения отсчитывается
        # окно продолжения.
        self._answered_at = 0.0

        # Что делать, когда Scott перебили. По умолчанию — ничего: сам
        # слушатель речью не управляет, это дело того, кто его создал.
        self.on_interrupt = on_interrupt

        self.stats = ListenerStats()

        # Живое значение паузы: начинается с настроенного и подстраивается по
        # ходу разговора. В конфигурации остаётся точка отсчёта, чтобы её было
        # с чем сравнивать.
        self._silence_to_end = self.config.silence_to_end
        self.stats.silence_to_end = self._silence_to_end

        self._running = False
        self._blocks: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        # В очереди не только звук, но и метка «сказано во время речи Scott»:
        # пока фраза ждёт разбора, он успевает договорить, и по состоянию уже
        # не понять, перебивали его или нет.
        self._phrases: "queue.Queue[tuple]" = queue.Queue(maxsize=8)
        self._threads: List[threading.Thread] = []
        self._stream = None
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()

        self._noise_floor = self.config.absolute_floor

        # Эхоподавление: вычитает из записи то, что звучит в колонках.
        # Создаётся лениво — на машине без микрофона оно не понадобится.
        self._echo = None
        self._echo_ref = None

        # Пока Scott говорит, входящий звук не разбирается: иначе он слышит
        # собственный ответ из колонок и принимает его за новую фразу.
        self._suspended = False

        # Речь Scott, которую он произносит прямо сейчас. Нужна, чтобы отличить
        # человека от эха: услышанное, найденное внутри этого текста, — не
        # перебивание.
        self._speaking_text = ""
        self._expecting_interrupt = False

        # Когда Scott в последний раз замолчал.
        #
        # «Стоп» человек говорит на последних словах ответа, а фраза
        # закрывается уже в тишине — и приходит обычной командой, без имени, то
        # есть мимо. В журнале услышанного так и записано: «Стоп!» → мимо.
        self._stopped_speaking_at = 0.0

        # Огибающая громкости колонок: быстро вверх, медленно вниз. По ней и
        # считается порог перебивания, поэтому громкость колонок значения не
        # имеет.
        self._playback_level = 0.0

        # Сколько блоков ответа уже прошло. Первые несколько — заведомо голос
        # Scott, по ним и замеряется громкость колонок.
        self._playback_blocks = 0

    # ==================== Управление ====================

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> dict:
        with self._lifecycle_lock:
            return self._start()

    def _start(self) -> dict:
        if self._running:
            return {"success": True, "message": "Scott уже слушает"}
        if any(thread.is_alive() for thread in self._threads):
            return {"success": False, "message": "Завершается предыдущий сеанс прослушивания. Попробуйте ещё раз"}
        if not HAS_SOUNDDEVICE:
            return {"success": False, "message": "Библиотека sounddevice не установлена — записывать звук нечем"}

        # Old audio must not be executed after resuming from a tray pause.
        for pending in (self._blocks, self._phrases):
            while True:
                try:
                    pending.get_nowait()
                except queue.Empty:
                    break

        # Слушаем заодно и колонки — чтобы вычитать из микрофона всё, что из
        # них звучит: не только собственную речь Scott, но и видео, музыку,
        # чужой разговор.
        #
        # Поднимается именно здесь, при настоящем запуске микрофона. В
        # проверках слушателя потоки дёргают напрямую, и захват колонок там
        # только мешал бы: он трогает живое устройство и вычитает настоящий
        # звук комнаты из придуманного тестового сигнала.
        self._включить_слух_на_колонки()

        # Микрофон берётся из настроек при каждом запуске, а не запоминается
        # раз и навсегда: гарнитуру втыкают и вынимают, и номер устройства в
        # системе от этого меняется. В настройках хранится имя, а номер по нему
        # ищется здесь и сейчас.
        device = self.config.device
        if device is None:
            device = _preferred_input_device()

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                device=device,
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            return {"success": False, "message": f"Не удалось открыть микрофон: {e}"}

        self._running = True
        # Подстроенная пауза переносится в новые показатели: сама она живёт в
        # _silence_to_end и перезапуск прослушивания переживает, а вот из
        # диагностики пропала бы.
        self.stats = ListenerStats(
            started_at=time.time(),
            noise_floor=self._noise_floor,
            silence_to_end=self._silence_to_end,
        )

        self._threads = [
            threading.Thread(target=self._segment_loop, name="scott-segment", daemon=True),
            threading.Thread(target=self._process_loop, name="scott-process", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

        print("🎧 Scott слушает микрофон")
        return {"success": True, "message": "Scott слушает"}

    def stop(self) -> dict:
        with self._lifecycle_lock:
            if self.on_interrupt is not None:
                try:
                    self.on_interrupt("")
                except Exception as e:
                    self.stats.last_error = f"Не удалось прервать ответ: {e}"
            return self._stop()

    def _stop(self) -> dict:
        if not self._running:
            return {"success": True, "message": "Scott и так не слушает"}

        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"⚠️ Ошибка при остановке потока: {e}")
            self._stream = None

        # Будим разборщик, чтобы он вышел из ожидания блока.
        try:
            self._blocks.put_nowait(np.zeros(BLOCK_SIZE, dtype=np.float32))
        except queue.Full:
            pass

        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=0.6)

        print("🎧 Scott перестал слушать")
        return {"success": True, "message": "Scott больше не слушает"}

    # ==================== Собственный голос ====================

    def suspend(self) -> None:
        """
        Перестать разбирать входящий звук, пока Scott говорит сам.

        Микрофон слышит колонки: собственный ответ Scott возвращается к нему же
        как новая фраза. На живой проверке это выглядело так — он произнёс
        ответ, а следующей строкой в логе появилось «Мимо: "Попробую открыть
        Google Chrome"», то есть он распознал сам себя. Пока в ответе не звучит
        его имя, дело кончается лишней работой Whisper, но стоит Scott сказать
        «Скотт» — и он начнёт разговаривать сам с собой без остановки.

        Поток не закрывается: открывать микрофон заново на каждую реплику
        долго и чревато щелчками. Блоки просто перестают складываться в очередь.
        """
        self._suspended = True

    def expect_interruption(self, spoken_text: str = "") -> None:
        """
        Слушать, не перебьют ли, пока Scott говорит.

        Раньше на это время микрофон приглушался наглухо, и человек не мог
        остановить ответ, даже поняв его с первых слов. Теперь звук продолжает
        разбираться, но щель узкая: порог поднимается до громкости самого
        Scott, фраза принимается только короткая, и она должна распознаться как
        просьба замолчать.

        `spoken_text` — то, что Scott произносит прямо сейчас. По нему
        отличается эхо: услышанное, найденное внутри этого текста, человеком не
        является.
        """
        self._speaking_text = (spoken_text or "").lower()
        self._expecting_interrupt = True

        # Огибающая начинается с тишины и поднимется сама на первых же блоках
        # речи Scott. Начинать с прошлого значения нельзя: громкость могли
        # поменять, да и ответ бывает тише предыдущего.
        self._playback_level = self._noise_floor
        self._playback_blocks = 0

    def stop_expecting(self) -> None:
        """
        Scott договорил — слушать как обычно.

        Очередь блоков очищается: в ней осталась вторая половина собственного
        ответа, разбирать её теперь незачем.
        """
        self._expecting_interrupt = False
        self._speaking_text = ""
        self._playback_level = 0.0
        self._playback_blocks = 0
        self._stopped_speaking_at = time.time()

        while True:
            try:
                self._blocks.get_nowait()
            except queue.Empty:
                break

    @property
    def is_expecting_interruption(self) -> bool:
        return self._expecting_interrupt

    def resume(self) -> None:
        """
        Снова слушать.

        Очередь блоков очищается: за время ответа там накопился собственный
        голос Scott, и разбирать его теперь незачем.
        """
        while True:
            try:
                self._blocks.get_nowait()
            except queue.Empty:
                break
        self._suspended = False

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def status(self) -> dict:
        return {
            "listening": self._running,
            "speaking": self._suspended,
            "available": HAS_SOUNDDEVICE,
            "noise_floor": round(self._noise_floor, 5),
            "phrases_heard": self.stats.phrases_heard,
            "triggered": self.stats.triggered,

            # Чем кончилась последняя услышанная фраза. По одному счётчику
            # обращений этого не понять: он растёт и при выполненной команде,
            # и при «позвали, но ничего не попросили».
            "last_command": self.stats.last_command,
            "last_dispatch": self.stats.last_dispatch,
            "since_command_sec": (round(time.time() - self.stats.last_command_at, 1)
                                  if self.stats.last_command_at else None),
            "ignored": self.stats.ignored,
            "last_text": self.stats.last_text,
            "last_error": self.stats.last_error,
            # Пауза меняется сама, поэтому её видно снаружи: иначе разбираться,
            # почему Scott стал медлительнее, будет негде.
            "silence_to_end": round(self._silence_to_end, 2),
            "cutoffs": self.stats.cutoffs,

            # Длина последней фразы и сколько их оборвалось по пределу.
            #
            # Сюда смотрят, когда Scott «отвечает медленно»: фраза, дошедшая до
            # предела, означает, что тишина после речи не наступила, и человек
            # ждал ответа все пятнадцать секунд записи. Замеры распознавания
            # этого не показывают — они начинаются, когда запись уже закрыта.
            "last_phrase_sec": self.stats.last_phrase_seconds,
            "last_answer_sec": self.stats.last_answer_seconds,
            "closed_by_length": self.stats.closed_by_length,
            "closed_by_speech_end": self.stats.closed_by_speech_end,
            "max_phrase": self.config.max_phrase,
            "interruptions": self.stats.interruptions,
            "echo_ignored": self.stats.echo_ignored,
            "recent": list(self.stats.recent[-10:]),
            "uptime_sec": round(time.time() - self.stats.started_at, 1) if self.stats.started_at else 0,
        }

    # ==================== Захват ====================

    def _on_audio(self, indata, frames, time_info, status) -> None:
        """
        Callback звукового потока. Обязан быть быстрым.

        Всё, что здесь делается, — копирование блока в очередь. Любая
        задержка (распознавание, запись на диск, печать) приводит к пропускам
        в записи, которые потом слышны как проглоченные слоги.
        """
        if status:
            self.stats.last_error = str(status)
        # Приглушение полное — блоки не копятся вовсе. Но пока Scott говорит и
        # ждёт перебивания, звук должен идти дальше: иначе перебить его нечем.
        if self._suspended and not self._expecting_interrupt:
            return
        try:
            self._blocks.put_nowait(indata[:, 0].copy())
        except queue.Full:
            # Очередь переполнена — значит разбор не успевает. Лучше потерять
            # блок, чем копить задержку, которая уже никогда не рассосётся.
            pass

    def feed(self, samples: np.ndarray) -> None:
        """
        Подать звук напрямую, минуя микрофон.

        Нужно для проверок: без этого модуль нельзя было бы протестировать
        нигде, кроме машины с микрофоном и живым человеком рядом.
        """
        for start in range(0, len(samples), BLOCK_SIZE):
            block = samples[start:start + BLOCK_SIZE]
            if len(block) < BLOCK_SIZE:
                block = np.pad(block, (0, BLOCK_SIZE - len(block)))
            self._blocks.put(block.astype(np.float32))

    # ==================== Собственное эхо ====================

    def _without_echo(self, block: np.ndarray) -> np.ndarray:
        """
        Убрать из блока то, что звучит в колонках.

        Работает, только пока Scott говорит: в тишине вычитать нечего, а
        гонять фильтр вхолостую значит расшатывать его настройку.

        При любой беде возвращается исходный блок. Эхоподавление — улучшение,
        а не условие того, что Scott слышит: если оно откажет, микрофон должен
        продолжать работать, пусть и со старыми костылями.
        """
        if not self.config.cancel_echo:
            return block

        try:
            if self._echo_ref is None:
                try:
                    from . import echo_cancel, echo_reference
                except ImportError:
                    import echo_cancel
                    import echo_reference

                self._echo_ref = echo_reference.get_reference()
                self._echo = echo_cancel.EchoCanceller()

            # Сперва колонки целиком, если их удалось услышать.
            #
            # Прежний путь берёт опорой только речь самого Scott — от неё он и
            # защищает. Но из тех же колонок звучит всё остальное: видео,
            # музыка, разговор в Discord, чужой помощник. 18 сентября из
            # динамиков пришла команда «Скотт, открой программу», и Scott её
            # выполнил: сказал её не человек, а чужая копия у собеседника.
            если_колонки = self._опора_из_колонок(block)
            if если_колонки is not None:
                return если_колонки

            ссылка = self._echo_ref

            if not ссылка.playing:
                # Scott молчит. Сбрасываем фильтр: к следующему ответу
                # громкость могли поменять, и прежняя настройка станет мешать.
                if self._echo is not None and self._echo.blocks:
                    self._echo.reset()
                return block

            # Задержка меряется один раз за ответ, по первым блокам. Пока она
            # неизвестна, вычитать нельзя: невыровненный опорный сигнал не
            # уберёт эхо, а добавит к нему свою копию.
            if not ссылка.delay_known:
                ссылка.learn_delay(block)
                return block

            опорный = ссылка.window(len(block))
            if опорный.size != len(block):
                return block

            return self._echo.process(block, опорный)
        except Exception as e:
            # Один раз сообщим и больше не будем: если оно ломается, оно
            # ломается на каждом блоке, и лог утонет.
            if not getattr(self, "_echo_complained", False):
                self._echo_complained = True
                print(f"⚠️ Эхоподавление отключилось: {e}")
            return block

    def _включить_слух_на_колонки(self) -> None:
        """
        Начать слушать то, что уходит в колонки.

        Нужно, чтобы вычитать из микрофона не только собственную речь Scott, но
        и всё остальное, что из них звучит: видео, музыку, разговор в Discord.

        Неудача — обычное дело и не беда: нет библиотеки, устройство не умеет
        отдавать свой выход на запись. Тогда остаётся прежний путь, где опорой
        служит только речь Scott.
        """
        if self._loopback is not None or not self.config.cancel_echo:
            return

        try:
            try:
                from . import loopback_reference
            except ImportError:
                import loopback_reference

            петля = loopback_reference.get_loopback()

            if петля.start():
                self._loopback = петля
                print(f"🔇 Слышу колонки — вычитаю их из микрофона ({петля.device_name})")
            else:
                print(f"ℹ️ Звук колонок не слышен ({петля.last_error}) — "
                      f"вычитаю только собственную речь")
        except Exception as e:
            print(f"ℹ️ Слух на колонки не включился: {e}")

    # Задержка тракта для звука из колонок, в миллисекундах.
    #
    # Путь короче, чем у сигнала от проигрывателя: там отсчёт идёт от «начали
    # играть», а здесь — от «услышали на выходе звуковой карты». Остаются
    # колонки, воздух и буфер записи — это десятки миллисекунд.
    LOOPBACK_DELAY_MS = 60

    def _опора_из_колонок(self, block: np.ndarray):
        """
        Вычесть из блока всё, что звучит в колонках.

        Возвращает обработанный блок — или None, если колонок не слышно и надо
        идти прежним путём (вычитать только речь самого Scott).

        ЗАЧЕМ ЭТО ШИРЕ ПРЕЖНЕГО. Прежняя опора — речь Scott, и она защищает
        только от «услышал сам себя». Из тех же колонок звучит всё остальное:
        видео, музыка, разговор в Discord, чужой помощник. В журнале 18
        сентября половина записей оказалась обрывками такой речи, а одна
        команда — «Скотт, открой программу» — пришла из динамиков и была
        выполнена.

        При любой беде — None: Scott продолжает слышать, просто по-старому.
        """
        if self._loopback is None:
            return None

        try:
            if not self._loopback.available:
                return None

            # В колонках тихо — вычитать нечего, а гонять фильтр вхолостую
            # значит расшатывать его настройку.
            if self._loopback.is_quiet():
                if self._echo is not None and self._echo.blocks:
                    self._echo.reset()
                return None

            задержка = SAMPLE_RATE * self.LOOPBACK_DELAY_MS // 1000
            опорный = self._loopback.window(len(block), delay=задержка)

            if опорный.size != len(block):
                return None

            return self._echo.process(block, опорный)
        except Exception as e:
            if not getattr(self, "_loopback_complained", False):
                self._loopback_complained = True
                print(f"⚠️ Звук колонок не вычитается: {e}")
            return None

    # ==================== Разбор на фразы ====================

    @staticmethod
    def _level(block: np.ndarray) -> float:
        """Громкость блока — среднеквадратичное значение."""
        return float(np.sqrt(np.mean(np.square(block)))) if len(block) else 0.0

    def _segment_loop(self) -> None:
        """
        Собрать из потока блоков законченные фразы.

        Речь начинается, когда несколько блоков подряд заметно громче фона, и
        заканчивается, когда тишина держится дольше паузы. Пока речи нет, фон
        медленно подстраивается — иначе включённый вентилятор или шум улицы
        через полчаса сделали бы порог бессмысленным.
        """
        preroll_blocks = max(1, int(self.config.preroll * 1000 / BLOCK_MS))
        max_blocks = int(self.config.max_phrase * 1000 / BLOCK_MS)
        min_blocks = max(1, int(self.config.min_phrase * 1000 / BLOCK_MS))

        calibration_blocks = max(1, int(self.config.interrupt_calibration * 1000 / BLOCK_MS))
        resume_blocks = max(1, int(self.config.resume_gap * 1000 / BLOCK_MS))
        clean_blocks = max(1, int(self.config.clean_gap * 1000 / BLOCK_MS))

        # Проверка конца речи — см. настройки с тем же именем.
        window_blocks = max(1, int(self.config.speech_window * 1000 / BLOCK_MS))
        check_every_blocks = max(1, int(self.config.speech_check_every * 1000 / BLOCK_MS))
        gone_blocks = max(1, int(self.config.speech_gone_to_end * 1000 / BLOCK_MS))
        speech_from_blocks = max(1, int(self.config.speech_check_from * 1000 / BLOCK_MS))

        blocks_since_check = 0
        speech_gone_blocks = 0

        # Говорил ли Scott, когда началась текущая фраза. Смотреть это при
        # закрытии поздно: он успевает договорить, и сказанное под его ответ
        # выглядит обычной командой.
        начата_под_речь = False

        # Для начала фразы счёт отдельный и начинается готовым: первая проверка
        # должна случиться сразу, иначе начало речи ждёт лишнюю четверть
        # секунды — ровно ту задержку, ради избавления от которой всё и
        # затевалось.
        blocks_since_onset_check = check_every_blocks

        preroll: List[np.ndarray] = []
        phrase: List[np.ndarray] = []
        loud_streak = 0
        silence_streak = 0
        loud_in_phrase = 0
        in_speech = False
        calibrating = False

        # Сколько блоков тишины прошло с закрытия предыдущей фразы: по этому
        # промежутку видно, оборвали ли человека.
        gap_blocks = 0

        # Сколько тишины успело накопиться к моменту закрытия. Нужно для
        # второго признака — спокойного окончания: его отсчитывать надо от
        # последнего громкого блока, а не от закрытия фразы. К закрытию пауза
        # ожидания уже прошла, и без этой поправки порог в две секунды
        # требовал почти трёх секунд настоящей тишины.
        silence_at_close = 0

        had_phrase = False
        closed_by_length = False

        while self._running:
            try:
                block = self._blocks.get(timeout=0.5)
            except queue.Empty:
                continue

            # Вычитаем из записи то, что Scott произносит сам.
            #
            # Делается до всего остального: и громкость, и порог, и фон должны
            # считаться по звуку комнаты, а не по собственному ответу из
            # колонок. Иначе планка уезжает вверх до громкости Scott, и
            # человека рядом становится не слышно вовсе.
            block = self._without_echo(block)

            level = self._level(block)

            if self._expecting_interrupt:
                # Планка считается от громкости самого Scott, а не от тишины:
                # иначе всё зависело бы от того, насколько выкручены колонки.
                self._playback_blocks += 1
                calibrating = self._playback_blocks <= calibration_blocks

                if calibrating:
                    # Начало ответа — заведомо голос Scott: так быстро человек
                    # отреагировать не успевает. По этим блокам и замеряется
                    # громкость колонок.
                    self._playback_level = max(level, self._playback_level)

                threshold = max(
                    self._playback_level * self.config.interrupt_threshold,
                    self._noise_floor * self.config.speech_threshold,
                    self.config.absolute_floor,
                )
            else:
                threshold = max(
                    self._noise_floor * self.config.speech_threshold,
                    self.config.absolute_floor,
                )

            loud = level > threshold

            # После замера планка только опускается — вслед за тем, как ответ
            # становится тише. Подниматься ей нельзя, и это выяснилось не
            # сразу: между речью Scott и голосом человека есть переходный блок,
            # где слышно и то и другое. Он оказывается ниже порога, а значит
            # «тихим», — и поднимал планку настолько, что остальные слова
            # человека уже не проходили. Перебивание не начиналось вовсе.
            if (self._expecting_interrupt and not calibrating
                    and not loud and level < self._playback_level):
                self._playback_level = 0.92 * self._playback_level + 0.08 * level

            if not in_speech:
                # Фон обновляем только по тишине и очень медленно: резкий
                # пересчёт по громкому блоку поднял бы порог так, что речь
                # перестала бы его преодолевать.
                # Фон обновляется только в настоящей тишине. Пока Scott
                # говорит, в микрофон идёт его собственный голос, и принимать
                # его за фон комнаты нельзя: порог уезжает вверх до его
                # громкости, и человека рядом становится не слышно вовсе.
                #
                # Прежде эта беда не всплывала, потому что во время речи блоки
                # отбрасывались целиком. Щель для перебивания её и открыла:
                # порог доехал до 0.286 при голосе человека 0.247.
                if not loud and not self._expecting_interrupt:
                    self._noise_floor = 0.95 * self._noise_floor + 0.05 * level
                    self.stats.noise_floor = self._noise_floor

                preroll.append(block)
                if len(preroll) > preroll_blocks:
                    preroll.pop(0)

                gap_blocks += 1

                loud_streak = loud_streak + 1 if loud else 0

                # Громко — ещё не значит, что заговорили. Под музыку громкость
                # держится постоянно, и фраза открывалась бы снова и снова,
                # едва закрывшись: одна запись в пятнадцать секунд сменилась
                # бы десятком коротких, и каждая пошла бы на распознавание.
                #
                # Начало фразы поэтому тоже проверяется на речь. Отказ ничего
                # не теряет: запас перед фразой продолжает копиться, и когда
                # речь всё-таки прозвучит, она войдёт в запись целиком.
                речь_началась = True
                if (self.has_speech is not None
                        and loud_streak >= self.config.onset_blocks
                        and not self._expecting_interrupt):
                    blocks_since_onset_check += 1

                    if blocks_since_onset_check >= check_every_blocks:
                        blocks_since_onset_check = 0
                        окно = np.concatenate(preroll[-window_blocks:]) if preroll else block

                        try:
                            речь_началась = bool(self.has_speech(окно))
                        except Exception as e:
                            if not self._speech_check_complained:
                                self._speech_check_complained = True
                                print(f"⚠️ Проверка речи отключилась: {e}")
                            self.has_speech = None
                    else:
                        # Между проверками фразу не открываем: иначе первая же
                        # громкая нота музыки заведёт её мимо проверки.
                        речь_началась = False

                if loud_streak >= self.config.onset_blocks and речь_началась:
                    # Человек заговорил снова. Если это случилось почти сразу
                    # после закрытия предыдущей фразы — значит её закрыли рано,
                    # на вдохе. Долгая тишина, наоборот, означает, что фраза
                    # кончилась сама и паузу можно выждать короче.
                    #
                    # Обрыв по длине фразы сюда не относится: пауза его не
                    # вызывала, и удлинять её незачем.
                    if had_phrase and not closed_by_length:
                        if gap_blocks <= resume_blocks:
                            self.stats.cutoffs += 1
                            self._adjust_silence(cut=True)
                        elif silence_at_close + gap_blocks >= clean_blocks:
                            self._adjust_silence(cut=False)

                    in_speech = True
                    phrase = list(preroll)
                    preroll.clear()
                    silence_streak = 0
                    loud_in_phrase = loud_streak

                    # Говорил ли Scott, когда фраза НАЧАЛАСЬ.
                    #
                    # Прежде это смотрелось при закрытии — и фраза, начатая под
                    # его ответ, но договорённая в тишине, считалась обычной
                    # командой. Так из колонок пришло «Скотт, открой программу.
                    # Скотт, закрой программу.»: Scott в эту секунду произносил
                    # свой ответ длиной семь секунд, а запись закрылась через
                    # девять — уже в тишине — и была выполнена как приказ.
                    #
                    # Хозяин этих слов не он и не человек рядом: их сказал
                    # чужой помощник из динамиков.
                    начата_под_речь = self._expecting_interrupt

                    # Новая фраза — счёт молчания начинается заново.
                    blocks_since_check = 0
                    speech_gone_blocks = 0
                    blocks_since_onset_check = check_every_blocks
            else:
                phrase.append(block)
                if loud:
                    loud_in_phrase += 1
                silence_streak = 0 if loud else silence_streak + 1

                # Пауза живая: подстройка меняет её между фразами, и значение
                # берётся заново на каждом блоке.
                if self._expecting_interrupt:
                    # Перебивают одним-двумя словами: ждать здесь нечего, слово
                    # уже сказано, и лишняя пауза — это лишние секунды речи,
                    # которую человек просил прекратить.
                    silence_blocks = max(1, int(self.config.interrupt_silence * 1000 / BLOCK_MS))
                    limit_blocks = int(self.config.interrupt_max_phrase * 1000 / BLOCK_MS)
                else:
                    silence_blocks = max(1, int(self._silence_to_end * 1000 / BLOCK_MS))
                    limit_blocks = max_blocks

                # Кончилась ли речь. Проверяется только у длинной фразы: у
                # короткой прежний путь по тишине работает, и трогать его
                # незачем.
                речь_кончилась = False
                if (self.has_speech is not None
                        and len(phrase) >= speech_from_blocks
                        and not self._expecting_interrupt):
                    blocks_since_check += 1

                    if blocks_since_check >= check_every_blocks:
                        blocks_since_check = 0
                        окно = np.concatenate(phrase[-window_blocks:])

                        try:
                            if self.has_speech(окно):
                                speech_gone_blocks = 0
                            else:
                                speech_gone_blocks += check_every_blocks
                        except Exception as e:
                            # Сломавшаяся проверка не должна лишать Scott слуха:
                            # возвращаемся к прежнему пути, по громкости.
                            if not self._speech_check_complained:
                                self._speech_check_complained = True
                                print(f"⚠️ Проверка речи отключилась: {e}")
                            self.has_speech = None

                        речь_кончилась = speech_gone_blocks >= gone_blocks

                too_long = len(phrase) >= limit_blocks
                if silence_streak >= silence_blocks or too_long or речь_кончилась:
                    in_speech = False
                    loud_streak = 0
                    gap_blocks = 0
                    silence_at_close = silence_streak
                    closed_by_length = too_long
                    # Считаются именно ГРОМКИЕ блоки, а не длина буфера: в него
                    # входят запас перед фразой и пауза после неё, вместе почти
                    # полторы секунды. Проверка по длине буфера пропускала любой
                    # щелчок — тот выглядел как фраза за счёт этой тишины.
                    if too_long:
                        self.stats.closed_by_length += 1
                    elif речь_кончилась:
                        self.stats.closed_by_speech_end += 1

                    if loud_in_phrase >= min_blocks:
                        had_phrase = True
                        audio = np.concatenate(phrase)
                        self.stats.last_phrase_seconds = round(len(audio) / SAMPLE_RATE, 2)
                        try:
                            # Метка ставится здесь, а не при разборе: пока фраза
                            # ждёт очереди, Scott успевает договорить, и по
                            # состоянию уже не понять, перебивали его или нет.
                            # Время закрытия фразы едет вместе со звуком: по
                            # нему считается то, чего не показывал ни один
                            # замер, — сколько человек ждёт от конца своей речи
                            # до ответа. Замеры по этапам этого не давали:
                            # каждый из них быстрый, а ждать человеку всё равно
                            # приходится.
                            # Признак берётся с НАЧАЛА фразы, а не с конца:
                            # к концу Scott успевает договорить, и сказанное
                            # под его ответ выглядит обычной командой.
                            self._phrases.put_nowait(
                                (audio,
                                 начата_под_речь or self._expecting_interrupt,
                                 time.time()))
                        except queue.Full:
                            self.stats.last_error = "Не успеваю обрабатывать — фраза пропущена"
                    phrase = []
                    loud_in_phrase = 0

    def _adjust_silence(self, cut: bool) -> None:
        """
        Сдвинуть паузу: вверх при обрыве, вниз при спокойном окончании.

        Шаги неравные намеренно. Обрыв означает, что Scott выполнил половину
        команды, — на это реакция резкая. Лишняя пауза всего лишь неприятна,
        поэтому вниз значение сползает медленно и только после настоящей
        тишины.
        """
        if not self.config.adaptive_silence:
            return

        было = self._silence_to_end

        if cut:
            стало = было + self.config.silence_step_up
        else:
            стало = было - self.config.silence_step_down

        стало = max(self.config.min_silence_to_end,
                    min(self.config.max_silence_to_end, стало))

        if abs(стало - было) < 0.001:
            return

        self._silence_to_end = стало
        self.stats.silence_to_end = стало

        if cut:
            print(f"⏳ Похоже, оборвал на вдохе — жду дольше: "
                  f"{было:.2f} -> {стало:.2f} с")

    # ==================== Распознавание и выполнение ====================

    def _process_loop(self) -> None:
        while self._running:
            try:
                audio, while_speaking, закрыта = self._phrases.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                text = (self.transcribe(audio) or "").strip()
            except Exception as e:
                self.stats.last_error = f"Распознавание не удалось: {e}"
                print(f"⚠️ {self.stats.last_error}")
                continue

            if not self._running:
                break

            if not text:
                continue

            # Фраза, услышанная во время речи Scott, — особый случай: это либо
            # просьба замолчать, либо его собственное эхо. Обычной командой она
            # быть не может, и разбирать её как команду нельзя.
            if while_speaking:
                self._handle_interruption(text)
                continue

            with self._lock:
                self.stats.phrases_heard += 1
                self.stats.last_text = text
                self.stats.recent.append(text)
                del self.stats.recent[:-20]

            # Человек заговорил снова — значит прошлый ответ ему больше не
            # нужен. Обрываем всё, что ещё звучит и ждёт очереди: иначе
            # ответы копятся, и Scott выпаливает их подряд, один поверх
            # другого.
            try:
                from speech_player import get_player
            except ImportError:
                from .speech_player import get_player

            get_player().stop()

            self._dispatch(text)

            # Сколько прошло от конца речи до готового ответа. Это и есть
            # «быстро» или «медленно» с точки зрения человека: он не знает и
            # знать не хочет, сколько заняли распознавание, разбор и синтез по
            # отдельности.
            self.stats.last_answer_seconds = round(time.time() - закрыта, 2)

    def _handle_interruption(self, text: str) -> None:
        """
        Решить, перебил ли человек — или Scott услышал сам себя.

        Две проверки поверх громкости и длины. Сначала эхо: если услышанное
        встречается в том, что Scott произносит, — это его собственный голос из
        колонок. Затем слово: даже прорвавшись через громкость, звук должен
        распознаться как просьба замолчать.

        Цена ошибки невелика — в худшем случае Scott замолчит, когда его не
        просили, — но и такой ошибки лучше избежать.
        """
        try:
            import vocabulary
        except ImportError:
            from . import vocabulary

        услышано = text.lower().strip(" .,!?…")

        if self._speaking_text and услышано and услышано in self._speaking_text:
            with self._lock:
                self.stats.echo_ignored += 1
            print(f"🔇 Своё эхо, не перебивание: «{text}»")
            return

        if not vocabulary.has_any_word(услышано, vocabulary.INTERRUPT_WORDS):
            with self._lock:
                self.stats.echo_ignored += 1
            return

        with self._lock:
            self.stats.interruptions += 1
            self.stats.last_text = text

        print(f"✋ Перебили: «{text}» — замолкаю")

        if self.on_interrupt is not None:
            try:
                self.on_interrupt(text)
            except Exception as e:
                self.stats.last_error = f"Не удалось замолчать: {e}"
                print(f"⚠️ {self.stats.last_error}")

    def _dispatch(self, text: str) -> None:
        """
        Решить, обращались ли к Scott, и выполнить команду.

        Без имени команда игнорируется молча: Scott слышит всю комнату, и
        реагировать на любой разговор рядом — худшее, что он может делать.
        """
        # Просьба замолчать, сказанная на последних словах ответа.
        #
        # Человек говорит «стоп», пока Scott ещё договаривает, но фраза
        # закрывается уже в тишине — и приходит сюда обычной командой, без
        # имени, то есть мимо. В журнале услышанного так и записано: «Стоп!» →
        # мимо, и выглядит это как «он меня не слышит».
        #
        # Имени здесь не требуем намеренно: «Скотт, стоп» никто не говорит,
        # когда хочет прервать на полуслове.
        if self._просят_замолчать(text):
            self._handle_interruption(text)
            self._записать_услышанное(text, "выполнена", "замолчи")
            return

        command = text
        if self.check_trigger is not None:
            result = self.check_trigger(text)
            if not getattr(result, "has_trigger", False):
                # Имени нет — но, может быть, это продолжение разговора.
                #
                # Сразу после ответа человек договаривает: «открой браузер»,
                # потом «а теперь почту». Требовать имя каждый раз — значит
                # заставлять повторять фразу целиком, что и было видно в
                # журнале: «открой сайт ggsl.com» прошло мимо, и через
                # полминуты его пришлось сказать снова, уже с именем.
                if self._продолжение(text):
                    command = text.strip()
                    print(f"🎧 Продолжение разговора: «{command}»")
                else:
                    self.stats.ignored += 1
                    self.stats.last_dispatch = "мимо"
                    print(f"🔇 Мимо: «{text}»")
                    self._записать_услышанное(text, "мимо")
                    return
            else:
                command = (getattr(result, "command_text", "") or "").strip()

                if not command:
                    # Позвали по имени, но ничего не попросили.
                    self.stats.triggered += 1
                    self.stats.last_dispatch = "имя без команды"
                    print("🎧 Scott слышит своё имя, но команды не было")
                    self._записать_услышанное(text, "имя без команды")
                    return

        self.stats.triggered += 1
        self.stats.last_command = command
        self.stats.last_command_at = time.time()
        self.stats.last_dispatch = "выполнена"

        # Окно продолжения отсчитывается от ответа: следующую фразу можно
        # сказать без имени.
        self._answered_at = time.time()

        print(f"🎤 Команда: «{command}»")
        try:
            self.handle_command(command)
            self._записать_услышанное(text, "выполнена", command)
        except Exception as e:
            self.stats.last_dispatch = "ошибка"
            self.stats.last_error = f"Команда не выполнена: {e}"
            print(f"⚠️ {self.stats.last_error}")
            self._записать_услышанное(text, "ошибка", command)

    # Сколько после окончания речи «стоп» ещё считается перебиванием.
    #
    # Полторы секунды — столько проходит от последнего слова ответа до
    # закрытия фразы по тишине. Больше — и «стоп», сказанное в разговоре через
    # минуту, заставило бы Scott оборвать что-то постороннее.
    INTERRUPT_AFTER_SPEECH = 1.5

    def _просят_замолчать(self, text: str) -> bool:
        """
        Просьба прервать ответ, сказанная на его последних словах.

        Пока Scott говорит, такие фразы приходят особым путём и разбираются в
        `_handle_interruption`. Но человек чаще всего говорит «стоп» под конец
        ответа: Scott успевает договорить, фраза закрывается уже в тишине — и
        приходит обычной командой без имени, то есть мимо.

        Чтобы «стоп», сказанное в разговоре через минуту, ничего не обрывало,
        окно короткое: полторы секунды после последнего слова.
        """
        if self._stopped_speaking_at <= 0:
            return False

        if time.time() - self._stopped_speaking_at > self.INTERRUPT_AFTER_SPEECH:
            return False

        try:
            import vocabulary
        except ImportError:
            from . import vocabulary

        сказанное = (text or "").lower().strip(" .,!?…")

        # Фраза должна быть короткой: «стоп» — это одно слово, а «стоит ли
        # открывать браузер» тоже содержит нужный корень.
        if len(сказанное.split()) > 3:
            return False

        return vocabulary.has_any_word(сказанное, vocabulary.INTERRUPT_WORDS)

    def _продолжение(self, text: str) -> bool:
        """
        Можно ли принять фразу без имени — как продолжение разговора.

        Два условия, и оба обязательны.

        ПЕРВОЕ: с ответа прошло немного. Человек договаривает сразу — «открой
        браузер», потом «а теперь почту», — и требовать имя каждый раз значит
        заставлять повторять фразу целиком. В журнале услышанного это видно
        буквально: «открой сайт ggsl.com» прошло мимо, и через полминуты его
        сказали снова, уже с именем.

        ВТОРОЕ, и оно важнее: это должна быть КОМАНДА. В окно продолжения
        попадает всё, что сказано в комнате, и вопрос из чужого разговора
        заставил бы Scott влезть в него с ответом — хуже, чем промолчать.
        Поэтому без способа отличить команду от прочего окно не работает
        вовсе: молчание безопаснее самодеятельности.
        """
        if self.looks_like_command is None:
            return False

        прошло = time.time() - self._answered_at
        if self._answered_at <= 0 or прошло > self.config.followup_window:
            return False

        сказанное = (text or "").strip()
        if not сказанное:
            return False

        try:
            return bool(self.looks_like_command(сказанное))
        except Exception as e:
            # Сломавшаяся проверка означает «имя обязательно»: это прежнее
            # поведение, и оно безопасное.
            self.stats.last_error = f"Проверка продолжения не удалась: {e}"
            return False

    def _записать_услышанное(self, text: str, исход: str, command: str = "") -> None:
        """
        Сохранить услышанное вместе с исходом.

        Без этого о том, что Scott расслышал, узнать неоткуда: распознанное
        уходило в вывод и нигде не оставалось. За один вечер таким образом
        пропали девятнадцать фраз из двадцати девяти — и почему именно, сказать
        было нечего.

        Сбой записи не должен мешать слушать, поэтому ошибки глохнут здесь же.
        """
        try:
            try:
                from . import heard_log
            except ImportError:
                import heard_log

            heard_log.record(text, исход, command,
                             seconds=self.stats.last_phrase_seconds or None)
        except Exception:
            pass


def _preferred_input_device() -> Optional[int]:
    """
    Микрофон, выбранный человеком в настройках, — или None, если выбран
    системный. Настроек может не быть вовсе (например, в тестах), и это не
    повод не слушать.
    """
    try:
        try:
            from . import audio_settings
        except ImportError:
            import audio_settings
        return audio_settings.get_input_device()
    except Exception:
        return None


def list_input_devices() -> List[dict]:
    """Микрофоны, доступные в системе, — чтобы можно было выбрать нужный."""
    if not HAS_SOUNDDEVICE:
        return []
    devices = []
    try:
        default = sd.default.device[0]
        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0:
                devices.append({
                    "index": index,
                    "name": info.get("name", ""),
                    "channels": info.get("max_input_channels", 0),
                    "default": index == default,
                })
    except Exception as e:
        print(f"⚠️ Не удалось получить список устройств: {e}")
    return devices
