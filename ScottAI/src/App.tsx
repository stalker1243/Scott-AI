import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { HomePage } from "./pages/HomePage";
import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SystemPage } from "./pages/SystemPage";
import { AutomationPage } from "./pages/AutomationPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { useThemeStore } from "./store/useThemeStore";
import { useSystemStore } from "./store/useSystemStore";
import { useChatStore } from "./store/useChatStore";
import { useDeviceStore } from "./store/useDeviceStore";
import { BackendClient } from "./lib/api";
import { getBackendUrl, loadSettings, saveThemeSettings } from "./lib/settings";
import { playVoiceBlob } from "./lib/voice";
import { pickAcknowledgement } from "./lib/phrases";
import { HandsFreeListener } from "./lib/handsFree";

export type Page = "home" | "chat" | "system" | "automation" | "analytics" | "settings" | "profile";

const PAGE_TITLES: Record<Page, string> = {
  home: "Главная",
  chat: "Чат",
  system: "Система",
  automation: "Автоматизация",
  analytics: "Аналитика",
  settings: "Настройки",
  profile: "Профиль",
};

const client = new BackendClient(getBackendUrl());

function nowTime(): string {
  return new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function describeError(err: unknown): string {
  if (err instanceof Error) {
    return `${err.name}: ${err.message}${err.stack ? `\n${err.stack}` : ""}`;
  }
  return String(err);
}

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [hydrated, setHydrated] = useState(false);

  const { style, darkMode, accent, glassOpacity } = useThemeStore();
  const setStatus = useSystemStore((s) => s.setStatus);
  const { addMessage, setDraft, setSending, pendingImage, setPendingImage, draft, autoSpeak, isRecording, setIsRecording, setHandsFreeStatus } =
    useChatStore();
  const { micDeviceId, speakerDeviceId, handsFreeEnabled, ttsVoice } = useDeviceStore();
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const speakQueueRef = useRef<Promise<void>>(Promise.resolve());
  const handsFreeRef = useRef<HandsFreeListener | null>(null);

  // Загрузка сохранённых настроек при старте
  useEffect(() => {
    loadSettings().finally(() => setHydrated(true));
  }, []);

  // Применение темы к <html> — все компоненты перекрашиваются реактивно через CSS
  useEffect(() => {
    const html = document.documentElement;
    html.dataset.style = style;
    html.dataset.mode = darkMode ? "dark" : "light";
    html.style.setProperty("--accent", accent);
    html.style.setProperty("--glass-opacity", String(glassOpacity));
  }, [style, darkMode, accent, glassOpacity]);

  // Персист настроек темы после гидратации (не пишем поверх ещё не загруженных значений)
  const firstThemeSave = useRef(true);
  useEffect(() => {
    if (!hydrated) return;
    if (firstThemeSave.current) {
      firstThemeSave.current = false;
      return;
    }
    void saveThemeSettings();
  }, [style, darkMode, accent, glassOpacity, hydrated]);

  // Отслеживаем реальное состояние сети (для баннера "нет интернета" в чате —
  // LLM-провайдеры недоступны без сети, даже если backend/локальный ПК в порядке).
  useEffect(() => {
    const update = () => setStatus({ hasInternet: navigator.onLine });
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, [setStatus]);

  // Health polling — различаем "ещё запускается" (никогда не отвечал) и
  // "упал" (отвечал раньше, перестал) — во втором случае в UI имеет смысл
  // предложить кнопку перезапуска backend.
  useEffect(() => {
    let cancelled = false;
    let everOnline = false;
    const check = async () => {
      const online = await client.health();
      if (cancelled) return;
      if (online) everOnline = true;
      setStatus({
        backendOnline: online,
        backendStatus: online ? "online" : everOnline ? "offline" : "starting",
      });
    };
    check();
    const id = setInterval(check, 4000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [setStatus]);

  // Метрики системы (CPU/RAM/процессы) — из backend
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const m = await client.metrics();
        if (!cancelled) {
          setStatus({ cpuPercent: m.cpuPercent, ramPercent: m.ramPercent, processCount: m.processCount });
        }
      } catch {
        // backend недоступен — просто не обновляем метрики
      }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [setStatus]);

  const speakReply = (text: string) => {
    speakQueueRef.current = speakQueueRef.current.then(async () => {
      try {
        const audio = await client.textToSpeech(text, ttsVoice);
        await playVoiceBlob(audio, true, speakerDeviceId);
      } catch (err) {
        console.error("[voice] speakReply failed:", err);
        addMessage({ fromUser: false, text: `⚠ Не удалось озвучить: ${describeError(err)}`, time: nowTime() });
      }
    });
    return speakQueueRef.current;
  };

  const sendMessage = async (text: string, imageDataUrl?: string) => {
    const trimmed = text.trim();
    if (!trimmed && !imageDataUrl) return;

    addMessage({ fromUser: true, text: trimmed, time: nowTime(), imageDataUrl });
    setDraft("");
    setPendingImage(null);

    if (imageDataUrl && !trimmed) {
      addMessage({
        fromUser: false,
        text: "Изображение получено — Scott пока не умеет их анализировать (эта возможность появится, когда backend получит поддержку зрения).",
        time: nowTime(),
      });
      return;
    }

    const ack = pickAcknowledgement();
    addMessage({ fromUser: false, text: ack, time: nowTime() });
    if (autoSpeak) void speakReply(ack);

    setSending(true);
    try {
      const answer = await client.ask(trimmed);
      const reply = answer || "Scott не дал ответа.";
      addMessage({ fromUser: false, text: reply, time: nowTime() });
      if (autoSpeak) void speakReply(reply);
    } catch (err) {
      addMessage({ fromUser: false, text: `Не удалось получить ответ от Scott: ${String(err)}`, time: nowTime() });
    } finally {
      setSending(false);
    }
  };

  const handleSend = () => sendMessage(draft, pendingImage?.dataUrl);

  const handleQuickCommand = (text: string) => {
    setPage("chat");
    sendMessage(text);
  };

  const handleVoiceInput = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }

    try {
      const audioConstraints: MediaTrackConstraints | boolean = micDeviceId ? { deviceId: { exact: micDeviceId } } : true;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);

        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        console.info("[voice] recorded blob:", blob.type, blob.size, "bytes, chunks:", chunksRef.current.length);
        setSending(true);
        try {
          const text = await client.speechToText(blob);
          setSending(false);
          if (text.trim()) {
            await sendMessage(text, undefined);
          } else {
            addMessage({ fromUser: false, text: "Не удалось распознать речь — попробуйте ещё раз.", time: nowTime() });
          }
        } catch (err) {
          setSending(false);
          console.error("[voice] speechToText failed:", err);
          addMessage({ fromUser: false, text: `Ошибка распознавания речи: ${describeError(err)}`, time: nowTime() });
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("[voice] getUserMedia/MediaRecorder failed:", err);
      addMessage({ fromUser: false, text: `Нет доступа к микрофону: ${describeError(err)}`, time: nowTime() });
    }
  };

  // Голос без рук: слушаем постоянно (VAD), при слове "Скотт" пропускаем
  // остаток фразы (или следующую, если сказали только имя) через sendMessage.
  // Не работает одновременно с ручной записью (кнопка микрофона), чтобы не
  // конкурировать за один и тот же MediaStream.
  useEffect(() => {
    if (!handsFreeEnabled) {
      handsFreeRef.current?.stop();
      handsFreeRef.current = null;
      setHandsFreeStatus("idle");
      return;
    }

    const listener = new HandsFreeListener({
      micDeviceId,
      recognize: (audio) => client.speechToText(audio),
      onStateChange: setHandsFreeStatus,
      onWakeCommand: (text) => {
        void sendMessage(text, undefined);
      },
      onError: (message) => {
        console.warn("[hands-free]", message);
      },
    });

    handsFreeRef.current = listener;
    listener.start().catch((err) => {
      console.error("[hands-free] не удалось запустить прослушивание:", err);
      addMessage({
        fromUser: false,
        text: `Не удалось включить голос без рук: ${describeError(err)}`,
        time: nowTime(),
      });
      setHandsFreeStatus("idle");
    });

    return () => {
      listener.stop();
      handsFreeRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handsFreeEnabled, micDeviceId]);

  return (
    <div className="glass-panel flex h-screen w-screen" style={{ background: "var(--bg-window)" }}>
      <Sidebar page={page} onSelect={setPage} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar subtitle={PAGE_TITLES[page]} />
        <div className="relative min-h-0 flex-1">
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className="absolute inset-0"
            >
              {page === "home" && <HomePage onLaunch={() => setPage("chat")} onQuickCommand={handleQuickCommand} />}
              {page === "chat" && <ChatPage onSend={handleSend} onVoiceInput={handleVoiceInput} />}
              {page === "system" && <SystemPage />}
              {page === "automation" && <AutomationPage />}
              {page === "analytics" && <AnalyticsPage />}
              {page === "settings" && <SettingsPage />}
              {page === "profile" && <ProfilePage />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
