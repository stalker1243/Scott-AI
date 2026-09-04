// Голос без рук: постоянно слушаем микрофон локально (без сети — простая
// детекция голоса по громкости, VAD), и только когда обнаружен отрезок речи,
// прогоняем его через уже существующий backend-пайплайн распознавания
// (whisper), проверяя, прозвучало ли имя "Скотт". Без специальной модели
// wake-word — точность подтверждается настоящим распознаванием речи, а не
// упрощённым локальным детектором.

export type HandsFreeState = "idle" | "listening" | "awaiting-command" | "processing";

const WAKE_WORDS = ["скотт", "скот", "scott"];
// Whisper на коротких/тихих/шумных отрезках иногда «галлюцинирует» и вместо
// тишины возвращает мусор вроде одного "!" или "..." — раньше такой текст
// пролетал проверку `if (text)` (непустая строка) и уходил в чат как реальная
// команда. Считаем текст осмысленным, только если в нём есть хоть одна буква.
const MEANINGFUL_TEXT_RE = /[a-zA-Zа-яёА-ЯЁ]/;

function isMeaningfulText(text: string): boolean {
  return MEANINGFUL_TEXT_RE.test(text);
}

const VOLUME_THRESHOLD = 0.025; // порог RMS, срабатывающий на начало речи
const SILENCE_MS = 1100; // тишина такой длительности — считаем, что фраза закончилась
const MAX_SEGMENT_MS = 9000; // защита от зависшей записи (например, музыка фоном)
const AWAITING_COMMAND_TIMEOUT_MS = 6000; // сколько ждём команду после одиночного "Скотт"
const MIN_BLOB_SIZE = 800; // короче — считаем шумом/щелчком, не отправляем на распознавание

interface HandsFreeOptions {
  micDeviceId: string | null;
  recognize: (audio: Blob) => Promise<string>;
  onWakeCommand: (text: string) => void;
  onStateChange: (state: HandsFreeState) => void;
  onError?: (message: string) => void;
}

export class HandsFreeListener {
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private rafId: number | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private maxSegmentTimer: ReturnType<typeof setTimeout> | null = null;
  private awaitingCommandTimer: ReturnType<typeof setTimeout> | null = null;
  private speaking = false;
  private awaitingCommand = false;
  private stopped = true;

  constructor(private opts: HandsFreeOptions) {}

  async start(): Promise<void> {
    if (!this.stopped) return;
    this.stopped = false;

    const constraints: MediaTrackConstraints | boolean = this.opts.micDeviceId
      ? { deviceId: { exact: this.opts.micDeviceId } }
      : true;

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: constraints });
    this.audioCtx = new AudioContext();
    const source = this.audioCtx.createMediaStreamSource(this.stream);
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 512;
    source.connect(this.analyser);

    this.opts.onStateChange("listening");
    this.loop();
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;

    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;

    if (this.recorder && this.recorder.state !== "inactive") {
      try {
        this.recorder.stop();
      } catch {
        // игнорируем — всё равно останавливаем весь конвейер ниже
      }
    }
    this.recorder = null;
    this.speaking = false;
    this.awaitingCommand = false;

    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    if (this.maxSegmentTimer) clearTimeout(this.maxSegmentTimer);
    if (this.awaitingCommandTimer) clearTimeout(this.awaitingCommandTimer);

    this.stream?.getTracks().forEach((t) => t.stop());
    void this.audioCtx?.close();
    this.audioCtx = null;
    this.analyser = null;
    this.stream = null;

    this.opts.onStateChange("idle");
  }

  private loop = (): void => {
    if (this.stopped || !this.analyser) return;

    const data = new Uint8Array(this.analyser.fftSize);
    this.analyser.getByteTimeDomainData(data);

    let sumSquares = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sumSquares += v * v;
    }
    const rms = Math.sqrt(sumSquares / data.length);

    if (rms > VOLUME_THRESHOLD) {
      if (!this.speaking) this.beginSegment();
      if (this.silenceTimer) {
        clearTimeout(this.silenceTimer);
        this.silenceTimer = null;
      }
    } else if (this.speaking && !this.silenceTimer) {
      this.silenceTimer = setTimeout(() => this.endSegment(), SILENCE_MS);
    }

    this.rafId = requestAnimationFrame(this.loop);
  };

  private beginSegment(): void {
    if (!this.stream) return;
    this.speaking = true;
    this.chunks = [];

    try {
      this.recorder = new MediaRecorder(this.stream);
    } catch (err) {
      this.speaking = false;
      this.opts.onError?.(`Не удалось начать запись: ${String(err)}`);
      return;
    }

    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start();
    this.maxSegmentTimer = setTimeout(() => this.endSegment(), MAX_SEGMENT_MS);
  }

  private endSegment(): void {
    if (!this.speaking || !this.recorder) return;
    this.speaking = false;

    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    if (this.maxSegmentTimer) {
      clearTimeout(this.maxSegmentTimer);
      this.maxSegmentTimer = null;
    }

    const recorder = this.recorder;
    this.recorder = null;
    recorder.onstop = () => void this.processSegment();
    recorder.stop();
  }

  private async processSegment(): Promise<void> {
    if (this.stopped) return;

    const blob = new Blob(this.chunks, { type: "audio/webm" });
    this.chunks = [];
    if (blob.size < MIN_BLOB_SIZE) {
      // слишком короткий отрезок — почти наверняка шум, не тратим время backend'а
      return;
    }

    this.opts.onStateChange("processing");

    try {
      const text = (await this.opts.recognize(blob)).trim();
      const lower = text.toLowerCase();

      if (this.awaitingCommand) {
        this.awaitingCommand = false;
        if (this.awaitingCommandTimer) clearTimeout(this.awaitingCommandTimer);
        if (isMeaningfulText(text)) this.opts.onWakeCommand(text);
        return;
      }

      const matchedWake = WAKE_WORDS.find((w) => lower.includes(w));
      if (!matchedWake) return; // имя не прозвучало — тихо продолжаем слушать

      const idx = lower.indexOf(matchedWake);
      // slice() снимает только само слово-триггер — если после него в
      // транскрипте осталась пунктуация ("Скотт, открой..."), .trim() её не
      // уберёт (это не пробел), и команда доходила до парсера с мусором
      // впереди ("- открой Google Chrome"), что ломало распознавание
      // названия приложения. Снимаем и пунктуацию тоже.
      const rest = text
        .slice(idx + matchedWake.length)
        .replace(/^[\s,.:;!?—-]+/, "")
        .trim();

      if (rest && isMeaningfulText(rest)) {
        this.opts.onWakeCommand(rest);
      } else {
        // сказали только "Скотт" — ждём команду следующим отдельным отрезком речи
        this.awaitingCommand = true;
        this.opts.onStateChange("awaiting-command");
        this.awaitingCommandTimer = setTimeout(() => {
          this.awaitingCommand = false;
          if (!this.stopped) this.opts.onStateChange("listening");
        }, AWAITING_COMMAND_TIMEOUT_MS);
        return;
      }
    } catch (err) {
      // ошибка распознавания одного отрезка — не прерываем прослушивание целиком
      this.opts.onError?.(String(err));
    } finally {
      if (!this.stopped && !this.awaitingCommand) {
        this.opts.onStateChange("listening");
      }
    }
  }
}
