import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Plus,
  Trash2,
  Zap,
  Terminal,
  X,
  Check,
  Circle,
  Square,
  Play,
  ChevronDown,
  ChevronUp,
  LayoutTemplate,
  Sparkles,
} from "lucide-react";
import { GhostButton, AccentButton } from "../components/Button";
import { StyledInput } from "../components/Input";
import { Switch } from "../components/Switch";
import { useThemeStore } from "../store/useThemeStore";
import { BackendClient, type CustomCommand, type IftttRule, type Macro, type Template } from "../lib/api";
import { getBackendUrl } from "../lib/settings";

const client = new BackendClient(getBackendUrl());

type Tab = "commands" | "ifttt" | "macros" | "templates";

/** Записать снимок версии — не критично для основного флоу, поэтому ошибки только логируются. */
function trackVersionSafe(itemType: string, name: string, data: object, description: string) {
  void client.trackVersion(`${itemType}:${name}`, itemType, data, description).catch((err) => {
    console.warn("[versions] не удалось записать версию:", err);
  });
}

const TRIGGER_TYPES: { value: string; label: string }[] = [
  { value: "command_contains", label: "Команда содержит" },
  { value: "command_equals", label: "Команда равна" },
  { value: "app_opened", label: "Открыто приложение" },
  { value: "time", label: "Время (ЧЧ:ММ)" },
];

const ACTION_TYPES: { value: string; label: string }[] = [
  { value: "execute_command", label: "Выполнить команду" },
  { value: "open_app", label: "Открыть приложение" },
  { value: "send_notification", label: "Показать уведомление" },
  { value: "send_message", label: "Отправить сообщение" },
  { value: "run_script", label: "Запустить скрипт" },
  { value: "custom_action", label: "Кастомное действие" },
];

const MACRO_ACTION_TYPES: { value: string; label: string; placeholder: string }[] = [
  { value: "click", label: "Клик мышью", placeholder: "название кнопки/элемента" },
  { value: "type", label: "Ввод текста", placeholder: "текст для ввода" },
  { value: "wait", label: "Пауза", placeholder: "миллисекунды, напр. 500" },
  { value: "command", label: "Команда Scott", placeholder: "открой Chrome" },
  { value: "key_press", label: "Нажатие клавиши", placeholder: "enter, ctrl+c..." },
  { value: "open_app", label: "Открыть приложение", placeholder: "notepad" },
  { value: "screenshot", label: "Скриншот", placeholder: "(необязательно)" },
];

function StyledSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  const accent = useThemeStore((s) => s.accent);
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-11 w-full rounded-[var(--radius-sm)] border px-3.5 text-[15px] outline-none transition-colors"
      style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", borderColor: "var(--border)" }}
      onFocus={(e) => (e.currentTarget.style.borderColor = accent)}
      onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      {children}
    </div>
  );
}

function EntityCard({
  title,
  subtitle,
  description,
  meta,
  enabled,
  onToggle,
  onDelete,
}: {
  title: string;
  subtitle: string;
  description?: string;
  meta: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="glass-panel flex items-center gap-4 rounded-[var(--radius-md)] border px-5 py-4"
      style={{ borderColor: "var(--border)", background: "var(--bg-surface)", opacity: enabled ? 1 : 0.55 }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold" style={{ color: "var(--text-primary)" }}>
            {title}
          </span>
          <span className="shrink-0 text-xs" style={{ color: "var(--text-muted)" }}>
            {meta}
          </span>
        </div>
        <div className="truncate text-sm" style={{ color: "var(--text-secondary)" }}>
          {subtitle}
        </div>
        {description && (
          <div className="truncate text-xs" style={{ color: "var(--text-muted)" }}>
            {description}
          </div>
        )}
      </div>
      <Switch checked={enabled} onToggle={onToggle} />
      <GhostButton icon={Trash2} danger onClick={onDelete} />
    </motion.div>
  );
}

function CustomCommandsSection() {
  const [commands, setCommands] = useState<CustomCommand[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("");
  const [action, setAction] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setCommands(await client.listCustomCommands());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const resetForm = () => {
    setName("");
    setTrigger("");
    setAction("");
    setDescription("");
    setShowForm(false);
  };

  const handleAdd = async () => {
    if (!name.trim() || !trigger.trim() || !action.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await client.addCustomCommand({ name: name.trim(), trigger: trigger.trim(), action: action.trim(), description: description.trim() });
      trackVersionSafe("custom_command", created.name, created, "Команда создана");
      resetForm();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (cmd: CustomCommand, enabled: boolean) => {
    setCommands((prev) => prev.map((c) => (c.name === cmd.name ? { ...c, enabled } : c)));
    try {
      const updated = await client.updateCustomCommand(cmd.name, { enabled });
      trackVersionSafe("custom_command", cmd.name, updated, enabled ? "Включена" : "Отключена");
    } catch (err) {
      setError(String(err));
      await refresh();
    }
  };

  const handleDelete = async (cmd: CustomCommand) => {
    if (!confirm(`Удалить команду «${cmd.name}»?`)) return;
    try {
      await client.deleteCustomCommand(cmd.name);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Свои голосовые команды: скажи триггер-фразу — Scott выполнит указанное действие.
        </span>
        <GhostButton text={showForm ? "Отмена" : "Добавить команду"} icon={showForm ? X : Plus} onClick={() => setShowForm((v) => !v)} />
      </div>

      {error && (
        <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {error}
        </div>
      )}

      {showForm && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border p-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="Название">
              <StyledInput value={name} onChange={setName} placeholder="утренний_режим" />
            </Field>
            <Field label="Триггер-фраза">
              <StyledInput value={trigger} onChange={setTrigger} placeholder="доброе утро" />
            </Field>
          </div>
          <Field label="Действие (что выполнить)">
            <StyledInput value={action} onChange={setAction} placeholder="открой Chrome и Telegram" />
          </Field>
          <Field label="Описание (необязательно)">
            <StyledInput value={description} onChange={setDescription} placeholder="Запуск утренних приложений" />
          </Field>
          <div className="flex justify-end">
            <AccentButton text="Сохранить" icon={Check} onClick={handleAdd} disabled={saving || !name.trim() || !trigger.trim() || !action.trim()} />
          </div>
        </motion.div>
      )}

      <div className="flex flex-col gap-2.5">
        {loading && commands.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Загрузка...
          </span>
        )}
        {!loading && commands.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Кастомных команд пока нет.
          </span>
        )}
        {commands.map((cmd) => (
          <EntityCard
            key={cmd.name}
            title={cmd.name}
            subtitle={`«${cmd.trigger}» → ${cmd.action}`}
            description={cmd.description}
            meta={`использовано: ${cmd.usage_count}`}
            enabled={cmd.enabled}
            onToggle={(v) => handleToggle(cmd, v)}
            onDelete={() => handleDelete(cmd)}
          />
        ))}
      </div>
    </div>
  );
}

function IftttSection() {
  const [rules, setRules] = useState<IftttRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState(TRIGGER_TYPES[0].value);
  const [triggerValue, setTriggerValue] = useState("");
  const [actionType, setActionType] = useState(ACTION_TYPES[0].value);
  const [actionValue, setActionValue] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRules(await client.listIftttRules());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const resetForm = () => {
    setName("");
    setTriggerValue("");
    setActionValue("");
    setDescription("");
    setShowForm(false);
  };

  const handleAdd = async () => {
    if (!name.trim() || !triggerValue.trim() || !actionValue.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await client.addIftttRule({
        name: name.trim(),
        trigger_type: triggerType,
        trigger_value: triggerValue.trim(),
        action_type: actionType,
        action_value: actionValue.trim(),
        description: description.trim(),
      });
      trackVersionSafe("ifttt_rule", created.name, created, "Правило создано");
      resetForm();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (rule: IftttRule, enabled: boolean) => {
    setRules((prev) => prev.map((r) => (r.name === rule.name ? { ...r, enabled } : r)));
    try {
      const updated = await client.updateIftttRule(rule.name, { enabled });
      trackVersionSafe("ifttt_rule", rule.name, updated, enabled ? "Включено" : "Отключено");
    } catch (err) {
      setError(String(err));
      await refresh();
    }
  };

  const handleDelete = async (rule: IftttRule) => {
    if (!confirm(`Удалить правило «${rule.name}»?`)) return;
    try {
      await client.deleteIftttRule(rule.name);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  const describeConditions = (rule: IftttRule) =>
    rule.conditions
      .map((c) => `${c.negate ? "НЕ " : ""}${TRIGGER_TYPES.find((t) => t.value === c.trigger_type)?.label ?? c.trigger_type}: ${c.trigger_value}`)
      .join(` ${rule.logic} `) || "без условий";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Если выполнено условие — Scott автоматически выполнит действие.
        </span>
        <GhostButton text={showForm ? "Отмена" : "Добавить правило"} icon={showForm ? X : Plus} onClick={() => setShowForm((v) => !v)} />
      </div>

      {error && (
        <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {error}
        </div>
      )}

      {showForm && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border p-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <Field label="Название правила">
            <StyledInput value={name} onChange={setName} placeholder="напоминание-обед" />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Если (тип условия)">
              <StyledSelect value={triggerType} onChange={setTriggerType} options={TRIGGER_TYPES} />
            </Field>
            <Field label="Значение условия">
              <StyledInput value={triggerValue} onChange={setTriggerValue} placeholder={triggerType === "time" ? "13:00" : "обед"} />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="То (тип действия)">
              <StyledSelect value={actionType} onChange={setActionType} options={ACTION_TYPES} />
            </Field>
            <Field label="Значение действия">
              <StyledInput value={actionValue} onChange={setActionValue} placeholder="напомни про обед" />
            </Field>
          </div>

          <Field label="Описание (необязательно)">
            <StyledInput value={description} onChange={setDescription} placeholder="" />
          </Field>

          <div className="flex justify-end">
            <AccentButton text="Сохранить" icon={Check} onClick={handleAdd} disabled={saving || !name.trim() || !triggerValue.trim() || !actionValue.trim()} />
          </div>
        </motion.div>
      )}

      <div className="flex flex-col gap-2.5">
        {loading && rules.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Загрузка...
          </span>
        )}
        {!loading && rules.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            IFTTT-правил пока нет.
          </span>
        )}
        {rules.map((rule) => (
          <EntityCard
            key={rule.name}
            title={rule.name}
            subtitle={`${describeConditions(rule)} → ${ACTION_TYPES.find((a) => a.value === rule.action_type)?.label ?? rule.action_type}: ${rule.action_value}`}
            description={rule.description}
            meta={`сработало: ${rule.execution_count}`}
            enabled={rule.enabled}
            onToggle={(v) => handleToggle(rule, v)}
            onDelete={() => handleDelete(rule)}
          />
        ))}
      </div>
    </div>
  );
}

function MacrosSection() {
  const [macros, setMacros] = useState<Macro[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const [isRecording, setIsRecording] = useState(false);
  const [currentMacroName, setCurrentMacroName] = useState<string | null>(null);
  const [actionsRecorded, setActionsRecorded] = useState(0);
  const [newMacroName, setNewMacroName] = useState("");

  const [actionType, setActionType] = useState(MACRO_ACTION_TYPES[0].value);
  const [actionTarget, setActionTarget] = useState("");
  const [actionX, setActionX] = useState("");
  const [actionY, setActionY] = useState("");
  const [busy, setBusy] = useState(false);

  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setMacros(await client.listMacros());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const status = await client.macroRecordingStatus();
      setIsRecording(status.is_recording);
      setCurrentMacroName(status.current_macro);
      setActionsRecorded(status.actions_recorded ?? 0);
    } catch {
      // backend недоступен — не трогаем текущее состояние
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshStatus();
    pollRef.current = window.setInterval(refreshStatus, 2000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [refresh, refreshStatus]);

  const handleStartRecording = async () => {
    if (!newMacroName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await client.startMacroRecording(newMacroName.trim());
      setNewMacroName("");
      await refreshStatus();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStopRecording = async () => {
    setBusy(true);
    setError(null);
    try {
      const macro = await client.stopMacroRecording();
      trackVersionSafe("macro", macro.name, macro, "Макрос записан");
      await refreshStatus();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleAddAction = async () => {
    if (!actionTarget.trim() && actionType !== "screenshot") return;
    setBusy(true);
    setError(null);
    try {
      await client.recordMacroAction({
        action_type: actionType,
        target: actionTarget.trim(),
        x: actionX ? Number(actionX) : 0,
        y: actionY ? Number(actionY) : 0,
      });
      setActionTarget("");
      setActionX("");
      setActionY("");
      await refreshStatus();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleExecute = async (macro: Macro) => {
    setError(null);
    try {
      await client.executeMacro(macro.name, macro.loop_count);
    } catch (err) {
      setError(String(err));
    }
  };

  const handleDelete = async (macro: Macro) => {
    if (!confirm(`Удалить макрос «${macro.name}»?`)) return;
    try {
      await client.deleteMacro(macro.name);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
        Запишите последовательность действий шаг за шагом и воспроизводите её одной командой.
      </span>

      {error && (
        <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {error}
        </div>
      )}

      <div
        className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border p-5"
        style={{ borderColor: isRecording ? "var(--danger)" : "var(--border)", background: "var(--bg-surface)" }}
      >
        {!isRecording ? (
          <div className="flex items-center gap-2.5">
            <div className="flex-1">
              <StyledInput value={newMacroName} onChange={setNewMacroName} placeholder="название нового макроса" onEnter={handleStartRecording} />
            </div>
            <GhostButton text="Начать запись" icon={Circle} onClick={handleStartRecording} disabled={busy || !newMacroName.trim()} />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <motion.span
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.2, repeat: Infinity }}
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: "var(--danger)" }}
                />
                <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                  Запись: {currentMacroName}
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  действий: {actionsRecorded}
                </span>
              </div>
              <GhostButton text="Остановить" icon={Square} danger onClick={handleStopRecording} disabled={busy} />
            </div>

            <div className="grid grid-cols-[1fr_2fr_80px_80px] gap-2.5">
              <StyledSelect value={actionType} onChange={setActionType} options={MACRO_ACTION_TYPES} />
              <StyledInput
                value={actionTarget}
                onChange={setActionTarget}
                placeholder={MACRO_ACTION_TYPES.find((a) => a.value === actionType)?.placeholder}
                onEnter={handleAddAction}
              />
              {actionType === "click" ? (
                <>
                  <StyledInput value={actionX} onChange={setActionX} placeholder="X" />
                  <StyledInput value={actionY} onChange={setActionY} placeholder="Y" />
                </>
              ) : (
                <div className="col-span-2" />
              )}
            </div>
            <div className="flex justify-end">
              <AccentButton text="Добавить действие" icon={Plus} onClick={handleAddAction} disabled={busy} />
            </div>
          </>
        )}
      </div>

      <div className="flex flex-col gap-2.5">
        {loading && macros.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Загрузка...
          </span>
        )}
        {!loading && macros.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Макросов пока нет.
          </span>
        )}
        {macros.map((macro) => (
          <motion.div
            key={macro.name}
            layout
            className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border px-5 py-4"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="flex items-center gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-semibold" style={{ color: "var(--text-primary)" }}>
                    {macro.name}
                  </span>
                  <span className="shrink-0 text-xs" style={{ color: "var(--text-muted)" }}>
                    {macro.actions.length} действ. · {(macro.duration_ms / 1000).toFixed(1)}с · запусков: {macro.execution_count}
                  </span>
                </div>
                {macro.description && (
                  <div className="truncate text-xs" style={{ color: "var(--text-muted)" }}>
                    {macro.description}
                  </div>
                )}
              </div>
              <GhostButton icon={expanded === macro.name ? ChevronUp : ChevronDown} onClick={() => setExpanded((v) => (v === macro.name ? null : macro.name))} />
              <GhostButton text="Играть" icon={Play} onClick={() => handleExecute(macro)} disabled={macro.actions.length === 0} />
              <GhostButton icon={Trash2} danger onClick={() => handleDelete(macro)} />
            </div>

            {expanded === macro.name && (
              <div className="flex flex-col gap-1.5 border-t pt-3" style={{ borderColor: "var(--border)" }}>
                {macro.actions.length === 0 && (
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Действий нет.
                  </span>
                )}
                {macro.actions.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                    <span className="shrink-0" style={{ color: "var(--text-muted)" }}>
                      {(a.timestamp / 1000).toFixed(1)}с
                    </span>
                    <span className="shrink-0 font-semibold" style={{ color: "var(--text-primary)" }}>
                      {MACRO_ACTION_TYPES.find((t) => t.value === a.action_type)?.label ?? a.action_type}
                    </span>
                    <span className="truncate">
                      {a.target}
                      {a.action_type === "click" ? ` (${a.x}, ${a.y})` : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function TemplatesSection() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("custom");
  const [description, setDescription] = useState("");
  const [commandsText, setCommandsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setTemplates(await client.listTemplates());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const resetForm = () => {
    setName("");
    setDescription("");
    setCommandsText("");
    setShowForm(false);
  };

  const handleCreate = async () => {
    if (!name.trim() || !category.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const commands = commandsText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      const created = await client.createTemplate({ name: name.trim(), category: category.trim(), description: description.trim(), commands });
      trackVersionSafe("template", created.name, created, "Шаблон создан");
      resetForm();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (tpl: Template) => {
    if (!confirm(`Удалить шаблон «${tpl.name}»?`)) return;
    try {
      await client.deleteTemplate(tpl.name);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  const handleApply = async (tpl: Template) => {
    setApplying(tpl.name);
    setStatus(null);
    setError(null);
    try {
      const applied = await client.applyTemplate(tpl.name);

      let commandsRun = 0;
      for (const cmd of applied.commands ?? []) {
        try {
          await client.runCommand(cmd);
          commandsRun++;
        } catch {
          // одна неудачная команда не должна останавливать остальной шаблон
        }
      }

      let rulesCreated = 0;
      for (const rule of applied.rules ?? []) {
        const cond = rule.conditions[0];
        if (!cond) continue;
        try {
          await client.addIftttRule({
            name: rule.name,
            trigger_type: cond.trigger_type,
            trigger_value: cond.trigger_value,
            action_type: rule.action_type,
            action_value: rule.action_value,
          });
          rulesCreated++;
        } catch {
          // правило с таким именем уже существует — пропускаем
        }
      }

      setStatus(`Шаблон «${tpl.name}» применён: выполнено команд — ${commandsRun}, создано правил — ${rulesCreated}.`);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setApplying(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Готовые сценарии: одна кнопка запускает набор команд и создаёт связанные IFTTT-правила.
        </span>
        <GhostButton text={showForm ? "Отмена" : "Новый шаблон"} icon={showForm ? X : Plus} onClick={() => setShowForm((v) => !v)} />
      </div>

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

      {showForm && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="glass-panel flex flex-col gap-3 rounded-[var(--radius-md)] border p-5"
          style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="Название">
              <StyledInput value={name} onChange={setName} placeholder="Вечерний ритуал" />
            </Field>
            <Field label="Категория">
              <StyledInput value={category} onChange={setCategory} placeholder="custom / morning / work / evening / gaming" />
            </Field>
          </div>
          <Field label="Описание">
            <StyledInput value={description} onChange={setDescription} placeholder="Что делает этот шаблон" />
          </Field>
          <Field label="Команды (по одной на строку, необязательно)">
            <StyledInput value={commandsText} onChange={setCommandsText} multiline placeholder={"Открой Chrome\nОткрой Telegram"} />
          </Field>
          <div className="flex justify-end">
            <AccentButton text="Сохранить" icon={Check} onClick={handleCreate} disabled={saving || !name.trim()} />
          </div>
        </motion.div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {loading && templates.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Загрузка...
          </span>
        )}
        {!loading && templates.length === 0 && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Шаблонов пока нет.
          </span>
        )}
        {templates.map((tpl) => (
          <motion.div
            key={tpl.name}
            layout
            className="glass-panel flex flex-col gap-2.5 rounded-[var(--radius-md)] border p-5"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="flex items-center gap-2">
              <span className="text-xl">{tpl.icon}</span>
              <span className="truncate font-semibold" style={{ color: "var(--text-primary)" }}>
                {tpl.name}
              </span>
              <span
                className="ml-auto shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                style={{ background: "var(--bg-elevated)", color: "var(--text-muted)" }}
              >
                {tpl.category}
              </span>
            </div>
            {tpl.description && (
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {tpl.description}
              </span>
            )}
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              команд: {tpl.commands.length} · правил: {tpl.rules.length} · применений: {tpl.popularity}
            </span>
            <div className="mt-1 flex gap-2">
              <AccentButton
                text={applying === tpl.name ? "Применяю..." : "Применить"}
                icon={Sparkles}
                onClick={() => handleApply(tpl)}
                disabled={applying !== null}
                className="h-10 flex-1"
              />
              <GhostButton icon={Trash2} danger onClick={() => handleDelete(tpl)} />
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

export function AutomationPage() {
  const [tab, setTab] = useState<Tab>("commands");
  const accent = useThemeStore((s) => s.accent);

  return (
    <div className="h-full overflow-y-auto p-10">
      <div className="flex max-w-4xl flex-col gap-6">
        <h1 className="text-[30px] font-bold" style={{ color: "var(--text-primary)" }}>
          Автоматизация
        </h1>

        <div className="flex gap-2">
          {(
            [
              { key: "commands", label: "Кастомные команды", icon: Terminal },
              { key: "ifttt", label: "IFTTT-правила", icon: Zap },
              { key: "macros", label: "Макросы", icon: Circle },
              { key: "templates", label: "Шаблоны", icon: LayoutTemplate },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className="flex items-center gap-2 rounded-[var(--radius-sm)] border px-4 py-2 text-sm font-semibold transition-colors"
              style={{
                borderColor: tab === key ? accent : "var(--border)",
                color: tab === key ? accent : "var(--text-secondary)",
                background: tab === key ? "var(--bg-elevated)" : "transparent",
              }}
            >
              <Icon size={15} strokeWidth={2} />
              {label}
            </button>
          ))}
        </div>

        {tab === "commands" && <CustomCommandsSection />}
        {tab === "ifttt" && <IftttSection />}
        {tab === "macros" && <MacrosSection />}
        {tab === "templates" && <TemplatesSection />}
      </div>
    </div>
  );
}
