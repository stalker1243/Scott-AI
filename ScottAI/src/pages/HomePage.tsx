import { Zap, Cpu, MemoryStick, ListTree, Bot, Lightbulb, TrendingUp, StickyNote, Sparkles } from "lucide-react";
import { AccentButton, GhostButton } from "../components/Button";
import { StatCard } from "../components/Card";
import { useSystemStore } from "../store/useSystemStore";
import { useProfileStore } from "../store/useProfileStore";

interface HomePageProps {
  onLaunch: () => void;
  onQuickCommand: (text: string) => void;
}

const QUICK_COMMANDS = [
  { text: "Что нового?", icon: Lightbulb },
  { text: "Статус системы", icon: TrendingUp },
  { text: "Открой блокнот", icon: StickyNote },
  { text: "Расскажи анекдот", icon: Sparkles },
];

export function HomePage({ onLaunch, onQuickCommand }: HomePageProps) {
  const { backendOnline, cpuPercent, ramPercent, processCount } = useSystemStore();
  const profileName = useProfileStore((s) => s.name);

  return (
    <div className="h-full overflow-y-auto p-10">
      <div className="flex max-w-4xl flex-col gap-[34px]">
        <div className="flex flex-col gap-2">
          <h1 className="text-[38px] font-bold" style={{ color: "var(--text-primary)" }}>
            {profileName ? `С возвращением, ${profileName}.` : "С возвращением."}
          </h1>
          <p className="text-base" style={{ color: backendOnline ? "var(--text-secondary)" : "var(--danger)" }}>
            {backendOnline ? "Scott готов к работе." : "Backend недоступен — запустите сервер."}
          </p>
        </div>

        <div>
          <AccentButton text="Запустить Scott" icon={Zap} onClick={onLaunch} className="w-[250px]" />
        </div>

        <div className="flex flex-wrap gap-5">
          <StatCard title="CPU" value={cpuPercent != null ? `${Math.round(cpuPercent)}%` : "—"} icon={Cpu} accentColor="#3b82f6" />
          <StatCard title="RAM" value={ramPercent != null ? `${Math.round(ramPercent)}%` : "—"} icon={MemoryStick} accentColor="#22c55e" />
          <StatCard title="Процессы" value={processCount != null ? String(processCount) : "—"} icon={ListTree} accentColor="#f59e0b" />
          <StatCard
            title="Scott"
            value={backendOnline ? "ONLINE" : "OFFLINE"}
            icon={Bot}
            accentColor={backendOnline ? "var(--success)" : "var(--danger)"}
          />
        </div>

        <div className="flex flex-col gap-3.5">
          <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
            Быстрые команды
          </span>
          <div className="flex flex-wrap gap-3.5">
            {QUICK_COMMANDS.map(({ text, icon }) => (
              <GhostButton key={text} text={text} icon={icon} onClick={() => onQuickCommand(text)} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
