import { useEffect, useState } from "react";
import { Check, PanelTop, Gem, Terminal, Pipette, Mic, Speaker, RefreshCw, Ear, Volume2 } from "lucide-react";
import { motion } from "framer-motion";
import { useThemeStore, type AppStyle } from "../store/useThemeStore";
import { useDeviceStore } from "../store/useDeviceStore";
import { useChatStore } from "../store/useChatStore";
import { Switch } from "../components/Switch";
import { GhostButton } from "../components/Button";
import { VersionsSection } from "../components/VersionsSection";
import { AiModelSection } from "../components/AiModelSection";
import { getBackendUrl, saveDeviceSettings } from "../lib/settings";
import { listAudioDevices, requestMicPermission, supportsOutputDeviceSelection, type AudioDeviceInfo } from "../lib/audioDevices";
import { BackendClient } from "../lib/api";
import { playVoiceBlob } from "../lib/voice";

const client = new BackendClient(getBackendUrl());

const STYLE_OPTIONS: { style: AppStyle; name: string; icon: typeof PanelTop; bg: string; accent: string }[] = [
  { style: "classic", name: "Classic", icon: PanelTop, bg: "#1f2937", accent: "#3b82f6" },
  { style: "glass", name: "Glass", icon: Gem, bg: "#0b1220", accent: "#60a5fa" },
  { style: "terminal", name: "Terminal Pro", icon: Terminal, bg: "#05070a", accent: "#00fff2" },
];

const ACCENT_SWATCHES = ["#3b82f6", "#22c55e", "#a855f7", "#f59e0b", "#ef4444", "#dc2626", "#00fff2", "#ff2bd6"];

export function SettingsPage() {
  const { style, darkMode, accent, glassOpacity, setStyle, setDarkMode, setAccent, setGlassOpacity } = useThemeStore();

  return (
    <div className="h-full overflow-y-auto p-10">
      <div className="flex max-w-3xl flex-col gap-8">
        <h1 className="text-[30px] font-bold" style={{ color: "var(--text-primary)" }}>
          Настройки
        </h1>

        <section className="flex flex-col gap-3.5">
          <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
            Стиль лаунчера
          </span>
          <div className="flex flex-wrap gap-4">
            {STYLE_OPTIONS.map(({ style: s, name, icon: Icon, bg, accent: previewAccent }) => {
              const selected = style === s;
              return (
                <motion.button
                  key={s}
                  type="button"
                  onClick={() => setStyle(s)}
                  whileHover={{ scale: 1.035, y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  transition={{ type: "spring", stiffness: 450, damping: 26 }}
                  className="flex h-[150px] w-[190px] flex-col justify-between rounded-[var(--radius-md)] border-2 p-4 text-left"
                  style={{
                    background: bg,
                    borderColor: selected ? accent : "var(--border)",
                    boxShadow: selected ? `0 0 14px ${accent}66` : "none",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <Icon size={22} color="white" strokeWidth={1.8} />
                    {selected && <Check size={18} color={accent} strokeWidth={3} />}
                  </div>
                  <div className="h-6 rounded-md" style={{ background: previewAccent }} />
                  <span className="text-[15px] font-bold text-white">{name}</span>
                </motion.button>
              );
            })}
          </div>
        </section>

        {style === "glass" && (
          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="text-[15px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  Прозрачность Glass
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Ниже — прозрачнее и чётче виден рабочий стол; выше — более матовое, размытое стекло
                </span>
              </div>
              <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
                {Math.round((1 - glassOpacity) * 100)}%
              </span>
            </div>
            <input
              type="range"
              min={0.05}
              max={0.9}
              step={0.05}
              value={glassOpacity}
              onChange={(e) => setGlassOpacity(Number(e.target.value))}
              className="w-full accent-current"
              style={{ color: accent }}
            />
          </section>
        )}

        {style === "classic" && (
          <section className="flex items-center justify-between">
            <div className="flex flex-col gap-0.5">
              <span className="text-[15px] font-semibold" style={{ color: "var(--text-primary)" }}>
                Тёмная тема
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                Только для стиля Classic
              </span>
            </div>
            <Switch checked={darkMode} onToggle={setDarkMode} />
          </section>
        )}

        <section className="flex flex-col gap-3.5">
          <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
            Цветовой акцент
          </span>
          <div className="flex flex-wrap items-center gap-3.5">
            {ACCENT_SWATCHES.map((c) => {
              const selected = accent.toLowerCase() === c.toLowerCase();
              return (
                <motion.button
                  key={c}
                  type="button"
                  onClick={() => setAccent(c)}
                  whileHover={{ scale: 1.15 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 500, damping: 22 }}
                  className="h-9 w-9 rounded-full border-[3px]"
                  style={{
                    background: c,
                    borderColor: selected ? "white" : "transparent",
                    boxShadow: selected ? `0 0 8px ${c}` : "none",
                  }}
                />
              );
            })}

            <div className="mx-1 h-8 w-px" style={{ background: "var(--border)" }} />

            <motion.label
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.94 }}
              className="relative flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border"
              style={{ borderColor: "var(--border)", background: "var(--bg-elevated)" }}
              title="Любой цвет"
            >
              <Pipette size={16} color="var(--text-secondary)" strokeWidth={2} />
              <input
                type="color"
                value={accent}
                onChange={(e) => setAccent(e.target.value)}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              />
            </motion.label>
          </div>
        </section>

        <DevicesSection />

        <AiModelSection />

        <VersionsSection />

        <section className="flex flex-col gap-1.5">
          <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
            Backend
          </span>
          <span className="text-[13px]" style={{ color: "var(--text-muted)" }}>
            {getBackendUrl()}
          </span>
        </section>
      </div>
    </div>
  );
}

function DeviceSelect({
  icon: Icon,
  label,
  devices,
  value,
  onChange,
  placeholder,
}: {
  icon: typeof Mic;
  label: string;
  devices: AudioDeviceInfo[];
  value: string | null;
  onChange: (id: string | null) => void;
  placeholder: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <Icon size={14} color="var(--text-secondary)" />
        <span className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
          {label}
        </span>
      </div>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="h-11 rounded-[var(--radius-sm)] border px-3 text-sm outline-none"
        style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", borderColor: "var(--border)" }}
      >
        <option value="">{placeholder}</option>
        {devices.map((d) => (
          <option key={d.deviceId} value={d.deviceId}>
            {d.label}
          </option>
        ))}
      </select>
    </div>
  );
}

const HANDS_FREE_LABELS: Record<string, string> = {
  idle: "Выключено",
  listening: "Слушаю — скажите «Скотт»",
  "awaiting-command": "Слышу вас — говорите команду",
  processing: "Распознаю...",
};

function DevicesSection() {
  const { micDeviceId, speakerDeviceId, handsFreeEnabled, ttsVoice, setMicDeviceId, setSpeakerDeviceId, setHandsFreeEnabled, setTtsVoice } =
    useDeviceStore();
  const handsFreeStatus = useChatStore((s) => s.handsFreeStatus);
  const [mics, setMics] = useState<AudioDeviceInfo[]>([]);
  const [speakers, setSpeakers] = useState<AudioDeviceInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const outputSelectable = supportsOutputDeviceSelection();

  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);
  const [defaultVoice, setDefaultVoice] = useState<string>("");
  const [previewing, setPreviewing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const { mics: m, speakers: s } = await listAudioDevices();
      setMics(m);
      setSpeakers(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    client
      .listVoices()
      .then(({ voices: v, default: d }) => {
        setVoices(v);
        setDefaultVoice(d);
      })
      .catch((err) => setVoiceError(String(err)));
  }, []);

  const handleRequestPermission = async () => {
    try {
      await requestMicPermission();
      await refresh();
    } catch (err) {
      console.error("Нет доступа к микрофону:", err);
    }
  };

  const handlePreviewVoice = async () => {
    setPreviewing(true);
    setVoiceError(null);
    try {
      const audio = await client.textToSpeech("Здравствуйте! Это голос Скотта.", ttsVoice);
      await playVoiceBlob(audio, true, speakerDeviceId);
    } catch (err) {
      setVoiceError(String(err));
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
          Аудио-устройства
        </span>
        <div className="flex gap-2">
          <GhostButton text="Разрешить доступ" onClick={handleRequestPermission} />
          <GhostButton icon={RefreshCw} onClick={refresh} disabled={loading} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <DeviceSelect
          icon={Mic}
          label="Микрофон"
          devices={mics}
          value={micDeviceId}
          onChange={(id) => {
            setMicDeviceId(id);
            void saveDeviceSettings();
          }}
          placeholder="Системный по умолчанию"
        />
        <DeviceSelect
          icon={Speaker}
          label={outputSelectable ? "Вывод звука" : "Вывод звука (не поддерживается)"}
          devices={outputSelectable ? speakers : []}
          value={speakerDeviceId}
          onChange={(id) => {
            setSpeakerDeviceId(id);
            void saveDeviceSettings();
          }}
          placeholder="Системный по умолчанию"
        />
      </div>

      {mics.length === 0 && (
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Список пуст — нажмите «Разрешить доступ», чтобы увидеть названия устройств.
        </span>
      )}

      <div className="my-1 h-px" style={{ background: "var(--border)" }} />

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <Volume2 size={14} color="var(--text-secondary)" />
          <span className="text-[15px] font-semibold" style={{ color: "var(--text-primary)" }}>
            Голос Scott
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          <select
            value={ttsVoice ?? defaultVoice}
            onChange={(e) => {
              setTtsVoice(e.target.value);
              void saveDeviceSettings();
            }}
            className="h-11 flex-1 rounded-[var(--radius-sm)] border px-3 text-sm outline-none"
            style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", borderColor: "var(--border)" }}
          >
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
          <GhostButton text={previewing ? "Играю..." : "Прослушать"} onClick={handlePreviewVoice} disabled={previewing || voices.length === 0} />
        </div>
        {voiceError && (
          <span className="text-xs" style={{ color: "var(--danger)" }}>
            {voiceError}
          </span>
        )}
      </div>

      <div className="my-1 h-px" style={{ background: "var(--border)" }} />

      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5">
            <Ear size={14} color="var(--text-secondary)" />
            <span className="text-[15px] font-semibold" style={{ color: "var(--text-primary)" }}>
              Голос без рук
            </span>
          </div>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Скажите «Скотт», не нажимая на микрофон — работает в любой вкладке
          </span>
          {handsFreeEnabled && (
            <span className="mt-1 text-xs font-semibold" style={{ color: "var(--accent, var(--text-secondary))" }}>
              {HANDS_FREE_LABELS[handsFreeStatus]}
            </span>
          )}
        </div>
        <Switch
          checked={handsFreeEnabled}
          onToggle={(v) => {
            setHandsFreeEnabled(v);
            void saveDeviceSettings();
          }}
        />
      </div>
    </section>
  );
}
