import { useRef, useEffect } from "react";
import { Sparkles, Paperclip, Mic, Send, X, Volume2, VolumeX, WifiOff } from "lucide-react";
import { motion } from "framer-motion";
import { open } from "@tauri-apps/plugin-dialog";
import { readFile } from "@tauri-apps/plugin-fs";
import { GhostButton } from "../components/Button";
import { StyledInput } from "../components/Input";
import { Markdown } from "../components/Markdown";
import { useChatStore, type ChatMessage } from "../store/useChatStore";
import { useThemeStore } from "../store/useThemeStore";
import { useSystemStore } from "../store/useSystemStore";
import { extensionToMime, bytesToDataUrl } from "../lib/image";

function Bubble({ message }: { message: ChatMessage }) {
  const accent = useThemeStore((s) => s.accent);

  return (
    <div className={`flex w-full ${message.fromUser ? "justify-end" : "justify-start"}`}>
      <div
        className="flex max-w-[560px] flex-col gap-2 rounded-[var(--radius-md)] px-3.5 py-3"
        style={{
          background: message.fromUser ? accent : "var(--bg-surface)",
          border: message.fromUser ? "none" : "1px solid var(--border)",
        }}
      >
        {message.imageDataUrl && (
          <img src={message.imageDataUrl} alt="attachment" className="h-40 w-[220px] rounded-lg object-cover" />
        )}
        {message.fromUser ? (
          <span className="whitespace-pre-wrap text-[15px] text-white">{message.text}</span>
        ) : (
          <div style={{ color: "var(--text-primary)" }}>
            <Markdown text={message.text} linkColor={accent} />
          </div>
        )}
        <span
          className="self-end text-[11px]"
          style={{ color: message.fromUser ? "rgba(255,255,255,0.7)" : "var(--text-muted)" }}
        >
          {message.time}
        </span>
      </div>
    </div>
  );
}

interface ChatPageProps {
  onSend: () => void;
  onVoiceInput: () => void;
}

export function ChatPage({ onSend, onVoiceInput }: ChatPageProps) {
  const { messages, draft, sending, pendingImage, isRecording, autoSpeak, setDraft, setPendingImage, setAutoSpeak, newChat } =
    useChatStore();
  const accent = useThemeStore((s) => s.accent);
  const hasInternet = useSystemStore((s) => s.hasInternet);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, sending]);

  const handleAttach = async () => {
    const path = await open({
      multiple: false,
      filters: [{ name: "Изображения", extensions: ["png", "jpg", "jpeg", "bmp", "gif"] }],
    });
    if (!path || typeof path !== "string") return;

    const bytes = await readFile(path);
    const dataUrl = bytesToDataUrl(bytes, extensionToMime(path));
    const name = path.split(/[\\/]/).pop() ?? "image";
    setPendingImage({ dataUrl, name });
  };

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[22px] font-bold" style={{ color: "var(--text-primary)" }}>
          Чат со Scott
        </h2>
        <div className="flex items-center gap-2.5">
          <GhostButton
            icon={autoSpeak ? Volume2 : VolumeX}
            text={autoSpeak ? "Озвучка: вкл" : "Озвучка: выкл"}
            active={autoSpeak}
            onClick={() => setAutoSpeak(!autoSpeak)}
          />
          <GhostButton text="Новый чат" icon={Sparkles} onClick={newChat} />
        </div>
      </div>

      {!hasInternet && (
        <div
          className="flex items-center gap-2 rounded-[var(--radius-sm)] border px-3.5 py-2 text-[13px]"
          style={{ background: "var(--bg-elevated)", borderColor: "var(--warning)", color: "var(--warning)" }}
        >
          <WifiOff size={14} />
          <span>
            Нет подключения к интернету — облачные модели (Groq/DeepSeek/OpenAI) недоступны, Scott отвечает в
            ограниченном локальном режиме.
          </span>
        </div>
      )}

      <div
        ref={scrollRef}
        className="glass-panel flex-1 overflow-y-auto rounded-[var(--radius-md)] border p-4"
        style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
      >
        <div className="flex flex-col gap-2.5">
          {messages.map((m) => (
            <Bubble key={m.id} message={m} />
          ))}
          {sending && (
            <div className="flex justify-start">
              <div
                className="flex h-9 w-[70px] items-center justify-center rounded-[var(--radius-sm)] border text-xl"
                style={{ background: "var(--bg-surface)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
              >
                ···
              </div>
            </div>
          )}
        </div>
      </div>

      {pendingImage && (
        <div
          className="flex h-16 items-center justify-between rounded-[var(--radius-sm)] border px-2.5"
          style={{ background: "var(--bg-elevated)", borderColor: accent }}
        >
          <div className="flex items-center gap-2.5">
            <img src={pendingImage.dataUrl} alt="pending" className="h-11 w-11 rounded object-cover" />
            <span className="text-[13px]" style={{ color: "var(--text-primary)" }}>
              {pendingImage.name}
            </span>
          </div>
          <GhostButton text="Убрать" icon={X} onClick={() => setPendingImage(null)} />
        </div>
      )}

      <div className="flex items-center gap-2.5">
        <GhostButton icon={Paperclip} onClick={handleAttach} className="w-11" />
        <motion.div
          animate={isRecording ? { scale: [1, 1.08, 1] } : { scale: 1 }}
          transition={isRecording ? { repeat: Infinity, duration: 1.1 } : undefined}
        >
          <GhostButton icon={Mic} onClick={onVoiceInput} active={isRecording} danger={isRecording} className="w-11" />
        </motion.div>
        <div className="flex-1">
          <StyledInput value={draft} onChange={setDraft} placeholder="Напишите сообщение..." onEnter={onSend} />
        </div>
        <GhostButton text="Отправить" icon={Send} onClick={onSend} disabled={!draft.trim() && !pendingImage} />
      </div>
    </div>
  );
}
