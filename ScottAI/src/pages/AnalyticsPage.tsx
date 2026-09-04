import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Clock, TrendingUp, TrendingDown, Minus, Lightbulb, RefreshCw } from "lucide-react";
import { StatCard } from "../components/Card";
import { useThemeStore } from "../store/useThemeStore";
import { BackendClient, type Analytics, type AnalyticsTrend, type AnalyticsRecommendation } from "../lib/api";
import { getBackendUrl } from "../lib/settings";

const client = new BackendClient(getBackendUrl());

function Bars({ labels, values, formatLabel }: { labels: string[]; values: number[]; formatLabel?: (l: string) => string }) {
  const accent = useThemeStore((s) => s.accent);
  const max = Math.max(1, ...values);

  return (
    <div className="flex h-[140px] items-end gap-1.5">
      {values.map((v, i) => (
        <div key={i} className="group relative flex flex-1 flex-col items-center gap-1.5">
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: `${Math.max(2, (v / max) * 100)}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="w-full rounded-t-[3px]"
            style={{ background: v > 0 ? accent : "var(--bg-elevated)", opacity: v > 0 ? 0.85 : 1, minHeight: 2 }}
            title={`${formatLabel ? formatLabel(labels[i]) : labels[i]}: ${v}`}
          />
          <span className="text-[9px]" style={{ color: "var(--text-muted)" }}>
            {formatLabel ? formatLabel(labels[i]) : labels[i]}
          </span>
        </div>
      ))}
    </div>
  );
}

function DistributionList({ labels, values, percentages }: { labels: string[]; values: number[]; percentages?: number[] }) {
  const accent = useThemeStore((s) => s.accent);
  if (labels.length === 0) {
    return (
      <span className="text-sm" style={{ color: "var(--text-muted)" }}>
        Пока нет данных.
      </span>
    );
  }
  return (
    <div className="flex flex-col gap-2.5">
      {labels.map((label, i) => (
        <div key={label} className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-sm">
            <span style={{ color: "var(--text-primary)" }}>{label}</span>
            <span style={{ color: "var(--text-muted)" }}>
              {values[i]} {percentages ? `(${percentages[i]}%)` : ""}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--bg-elevated)" }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${percentages ? percentages[i] : (values[i] / Math.max(1, ...values)) * 100}%` }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              className="h-full rounded-full"
              style={{ background: accent }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border p-5" style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}>
      <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
        {title}
      </span>
      {children}
    </section>
  );
}

export function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [trend, setTrend] = useState<AnalyticsTrend | null>(null);
  const [recommendations, setRecommendations] = useState<AnalyticsRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, t, r] = await Promise.all([client.getAnalytics(), client.getAnalyticsTrend(), client.getAnalyticsRecommendations()]);
      setAnalytics(a);
      setTrend(t);
      setRecommendations(r);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const TrendIcon = trend?.trend === "up" ? TrendingUp : trend?.trend === "down" ? TrendingDown : Minus;
  const trendColor = trend?.trend === "up" ? "var(--success)" : trend?.trend === "down" ? "var(--danger)" : "var(--text-muted)";

  return (
    <div className="h-full overflow-y-auto p-10">
      <div className="flex max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-[30px] font-bold" style={{ color: "var(--text-primary)" }}>
            Аналитика
          </h1>
          <motion.button
            onClick={refresh}
            whileHover={{ rotate: 90 }}
            whileTap={{ scale: 0.9 }}
            className="flex h-9 w-9 items-center justify-center rounded-full"
            style={{ color: "var(--text-secondary)" }}
          >
            <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
          </motion.button>
        </div>

        {error && (
          <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            {error}
          </div>
        )}

        {!analytics && loading && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Загрузка...
          </span>
        )}

        {analytics && (
          <>
            <div className="flex flex-wrap gap-4">
              <StatCard title="Команд всего" value={String(analytics.total_commands)} icon={Activity} />
              <StatCard title="Ср. время отклика" value={`${analytics.response_time.average}с`} icon={Clock} />
              <StatCard
                title="Тренд (3 дня)"
                value={trend && trend.trend !== "insufficient_data" ? `${trend.trend_percentage > 0 ? "+" : ""}${trend.trend_percentage}%` : "—"}
                icon={TrendIcon}
                accentColor={trendColor}
              />
            </div>

            <Section title="Команды по дням (последние 7 дней)">
              <Bars
                labels={analytics.daily.dates}
                values={analytics.daily.commands}
                formatLabel={(d) => d.slice(5)}
              />
            </Section>

            <Section title="Команды по часам (последние 24 часа)">
              <Bars
                labels={analytics.hourly.hours}
                values={analytics.hourly.commands}
                formatLabel={(h) => h.slice(11, 13)}
              />
            </Section>

            <div className="grid grid-cols-2 gap-4">
              <Section title="Типы команд">
                <DistributionList
                  labels={analytics.command_types.types}
                  values={analytics.command_types.counts}
                  percentages={analytics.command_types.percentages}
                />
              </Section>

              <Section title="Самые открываемые приложения">
                <DistributionList labels={analytics.top_apps.apps} values={analytics.top_apps.usage_count} />
              </Section>
            </div>

            {recommendations.length > 0 && (
              <Section title="Рекомендации">
                <div className="flex flex-col gap-2.5">
                  {recommendations.map((rec, i) => (
                    <div key={i} className="flex items-start gap-2.5 rounded-[var(--radius-sm)] border px-4 py-3" style={{ borderColor: "var(--border)" }}>
                      <Lightbulb size={16} className="mt-0.5 shrink-0" style={{ color: "var(--warning)" }} />
                      <div className="flex flex-col">
                        <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                          {rec.title}
                        </span>
                        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                          {rec.message}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
