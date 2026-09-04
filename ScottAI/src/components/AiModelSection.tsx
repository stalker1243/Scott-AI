import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Brain, Check, KeyRound } from "lucide-react";
import { GhostButton, AccentButton } from "./Button";
import { StyledInput } from "./Input";
import { useThemeStore } from "../store/useThemeStore";
import { BackendClient, type AiProvider } from "../lib/api";
import { getBackendUrl } from "../lib/settings";

const client = new BackendClient(getBackendUrl());

export function AiModelSection() {
  const accent = useThemeStore((s) => s.accent);
  const [providers, setProviders] = useState<AiProvider[]>([]);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [apiKey, setApiKey] = useState("");
  const [applying, setApplying] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { providers: p, active_provider, active_model } = await client.listAiProviders();
      setProviders(p);
      setActiveProvider(active_provider);
      setActiveModel(active_model);
      setSelectedProvider((prev) => prev || active_provider || p[0]?.id || "");
      setSelectedModel((prev) => prev || active_model || "");
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const currentProviderInfo = providers.find((p) => p.id === selectedProvider);

  const handleSelectProvider = (providerId: string) => {
    setSelectedProvider(providerId);
    setApiKey("");
    const info = providers.find((p) => p.id === providerId);
    setSelectedModel(providerId === activeProvider ? activeModel : info?.models[0]?.id ?? "");
  };

  const handleApply = async () => {
    if (!selectedProvider || !selectedModel) return;
    setApplying(true);
    setError(null);
    setStatus(null);
    try {
      const result = await client.configureAi(selectedProvider, selectedModel, apiKey.trim() || undefined);
      if (!result.success) {
        setError(result.error ?? "Не удалось применить настройки");
        return;
      }
      setApiKey("");
      setStatus(`Активна модель: ${selectedProvider} / ${selectedModel}`);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setApplying(false);
    }
  };

  const needsKey = currentProviderInfo && !currentProviderInfo.configured;

  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex items-center gap-1.5">
        <Brain size={14} color="var(--text-secondary)" />
        <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
          Модель ИИ
        </span>
      </div>
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
        {activeProvider ? `Сейчас отвечает: ${activeProvider} / ${activeModel}` : "ИИ-провайдер не настроен"} — у каждой модели свои сильные стороны:
        Groq быстрее всего, OpenAI даёт лучшее качество, DeepSeek силён в логике и математике.
      </span>

      {error && (
        <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {error}
        </div>
      )}
      {status && (
        <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--success)", color: "var(--success)" }}>
          {status}
        </div>
      )}

      {loading && providers.length === 0 && (
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>
          Загрузка...
        </span>
      )}

      {providers.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border p-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="flex flex-wrap gap-2">
            {providers.map((p) => {
              const selected = selectedProvider === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectProvider(p.id)}
                  className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border px-3.5 py-2 text-sm font-semibold transition-colors"
                  style={{
                    borderColor: selected ? accent : "var(--border)",
                    color: selected ? accent : "var(--text-secondary)",
                    background: selected ? "var(--bg-elevated)" : "transparent",
                  }}
                >
                  {p.id === activeProvider && <Check size={13} strokeWidth={3} />}
                  {p.id}
                  {p.configured && <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--success)" }} />}
                </button>
              );
            })}
          </div>

          {currentProviderInfo && (
            <>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {currentProviderInfo.note}
              </span>

              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
                  Модель
                </span>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="h-11 w-full rounded-[var(--radius-sm)] border px-3.5 text-[15px] outline-none"
                  style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", borderColor: "var(--border)" }}
                >
                  {currentProviderInfo.models.length === 0 && <option value="">Нет доступных моделей</option>}
                  {currentProviderInfo.models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id}
                    </option>
                  ))}
                </select>
                {currentProviderInfo.models.find((m) => m.id === selectedModel) && (
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {currentProviderInfo.models.find((m) => m.id === selectedModel)?.note}
                  </span>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-1.5">
                  <KeyRound size={13} color="var(--text-secondary)" />
                  <span className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
                    {needsKey ? "API-ключ (обязателен для этого провайдера)" : "Свой API-ключ (необязательно)"}
                  </span>
                </div>
                <StyledInput
                  value={apiKey}
                  onChange={setApiKey}
                  password
                  placeholder={currentProviderInfo.configured ? "Оставьте пустым, чтобы использовать уже сохранённый ключ" : "Вставьте свой ключ этого провайдера"}
                />
              </div>

              <div className="flex justify-end">
                <AccentButton
                  text={applying ? "Применяю..." : "Применить"}
                  onClick={handleApply}
                  disabled={applying || !selectedModel || (needsKey && !apiKey.trim())}
                  className="h-11"
                />
              </div>
            </>
          )}
        </motion.div>
      )}

      <GhostButton text="Обновить список" onClick={refresh} disabled={loading} className="self-start" />
    </section>
  );
}
