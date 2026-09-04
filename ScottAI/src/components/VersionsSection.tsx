import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { History, ChevronDown, ChevronUp, RotateCcw, RefreshCw } from "lucide-react";
import { GhostButton } from "./Button";
import { useThemeStore } from "../store/useThemeStore";
import { BackendClient, type VersionItem, type VersionEntry } from "../lib/api";
import { getBackendUrl } from "../lib/settings";

const client = new BackendClient(getBackendUrl());

const ITEM_TYPE_LABELS: Record<string, string> = {
  custom_command: "Кастомная команда",
  ifttt_rule: "IFTTT-правило",
  macro: "Макрос",
  template: "Шаблон",
};

function HistoryRow({ item, onChanged }: { item: VersionItem; onChanged: () => void }) {
  const accent = useThemeStore((s) => s.accent);
  const [expanded, setExpanded] = useState(false);
  const [versions, setVersions] = useState<VersionEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openData, setOpenData] = useState<number | null>(null);
  const [rollingBack, setRollingBack] = useState<number | null>(null);

  const toggle = async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (versions) return;
    setLoading(true);
    setError(null);
    try {
      const history = await client.getVersionHistory(item.item_id);
      setVersions(history?.versions.slice().reverse() ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async (versionNumber: number) => {
    if (!confirm(`Откатить «${item.item_id}» к версии ${versionNumber}? Это создаст новую версию с данными из старой.`)) return;
    setRollingBack(versionNumber);
    setError(null);
    try {
      await client.rollbackVersion(item.item_id, versionNumber);
      setVersions(null);
      const history = await client.getVersionHistory(item.item_id);
      setVersions(history?.versions.slice().reverse() ?? []);
      onChanged();
    } catch (err) {
      setError(String(err));
    } finally {
      setRollingBack(null);
    }
  };

  return (
    <motion.div
      layout
      className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border px-5 py-4"
      style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
    >
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold" style={{ color: "var(--text-primary)" }}>
              {item.item_id}
            </span>
            <span className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ background: "var(--bg-elevated)", color: accent }}>
              {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
            </span>
          </div>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            версий: {item.versions_count} · текущая: {item.current_version}
          </span>
        </div>
        <GhostButton icon={expanded ? ChevronUp : ChevronDown} onClick={toggle} />
      </div>

      {expanded && (
        <div className="flex flex-col gap-2 border-t pt-3" style={{ borderColor: "var(--border)" }}>
          {loading && (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              Загрузка...
            </span>
          )}
          {error && (
            <span className="text-xs" style={{ color: "var(--danger)" }}>
              {error}
            </span>
          )}
          {versions?.map((v) => (
            <div key={v.version_number} className="flex flex-col gap-1.5 rounded-[var(--radius-sm)] border px-3.5 py-2.5" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                    v{v.version_number}
                  </span>
                  <span style={{ color: "var(--text-secondary)" }}>{v.change_description || "без описания"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {new Date(v.created_at).toLocaleString("ru-RU")}
                  </span>
                  <GhostButton
                    text={rollingBack === v.version_number ? "Откат..." : "Откатить"}
                    icon={RotateCcw}
                    onClick={() => handleRollback(v.version_number)}
                    disabled={rollingBack !== null || v.version_number === item.current_version}
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpenData(openData === v.version_number ? null : v.version_number)}
                className="self-start text-[11px] font-semibold hover:underline"
                style={{ color: accent }}
              >
                {openData === v.version_number ? "Скрыть данные" : "Показать данные"}
              </button>
              {openData === v.version_number && (
                <pre
                  className="max-h-[200px] overflow-auto rounded-[var(--radius-sm)] p-3 text-[11px]"
                  style={{ background: "var(--bg-elevated)", color: "var(--text-secondary)" }}
                >
                  {JSON.stringify(v.data, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

/** Секция версионирования — встраивается во вкладку «Настройки» (раньше была отдельной вкладкой). */
export function VersionsSection() {
  const [items, setItems] = useState<VersionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await client.listVersionedItems());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
          Версионирование
        </span>
        <motion.button
          onClick={refresh}
          whileHover={{ rotate: 90 }}
          whileTap={{ scale: 0.9 }}
          className="flex h-8 w-8 items-center justify-center rounded-full"
          style={{ color: "var(--text-secondary)" }}
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </motion.button>
      </div>

      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
        Scott автоматически сохраняет версию при каждом создании или изменении команды, правила, макроса или шаблона — здесь можно посмотреть историю и откатиться к любой из них.
      </span>

      {error && (
        <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {error}
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        {loading && items.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Загрузка...
          </span>
        )}
        {!loading && items.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <History size={28} style={{ color: "var(--text-muted)" }} />
            <span className="text-sm" style={{ color: "var(--text-muted)" }}>
              Пока нет отслеживаемых изменений. Создайте или измените кастомную команду, IFTTT-правило, макрос или шаблон во вкладке «Автоматизация».
            </span>
          </div>
        )}
        {items.map((item) => (
          <HistoryRow key={item.item_id} item={item} onChanged={refresh} />
        ))}
      </div>
    </section>
  );
}
