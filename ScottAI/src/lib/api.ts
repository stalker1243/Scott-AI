// Тонкий HTTP-клиент к backend Scott AI (FastAPI, см. backend/main.py).
// Методы соответствуют реально существующим REST-эндпоинтам.

export class ApiError extends Error {}

export interface Metrics {
  cpuPercent: number;
  ramPercent: number;
  processCount: number;
}

export interface CustomCommand {
  name: string;
  trigger: string;
  action: string;
  description: string;
  created_at: string;
  usage_count: number;
  enabled: boolean;
}

export interface IftttCondition {
  trigger_type: string;
  trigger_value: string;
  negate: boolean;
}

export interface IftttRule {
  name: string;
  conditions: IftttCondition[];
  logic: "AND" | "OR";
  action_type: string;
  action_value: string;
  description: string;
  created_at: string;
  enabled: boolean;
  execution_count: number;
  last_execution: string | null;
}

export interface MacroAction {
  action_type: string;
  target: string;
  timestamp: number;
  x: number;
  y: number;
  details: Record<string, unknown>;
}

export interface Macro {
  name: string;
  description: string;
  actions: MacroAction[];
  created_at: string;
  last_executed: string | null;
  execution_count: number;
  enabled: boolean;
  loop_count: number;
  duration_ms: number;
}

export interface RecordingStatus {
  is_recording: boolean;
  current_macro: string | null;
  elapsed_ms?: number;
  actions_recorded?: number;
}

export interface Template {
  name: string;
  category: string;
  description: string;
  commands: string[];
  rules: Array<{
    name: string;
    action_type: string;
    action_value: string;
    conditions: { trigger_type: string; trigger_value: string; negate?: boolean }[];
  }>;
  icon: string;
  created_at: string;
  popularity: number;
}

export interface Analytics {
  daily: { dates: string[]; commands: number[]; total: number };
  hourly: { hours: string[]; commands: number[]; total: number };
  command_types: { types: string[]; counts: number[]; percentages: number[]; total: number };
  top_apps: { apps: string[]; usage_count: number[]; total: number };
  response_time: { average: number; min: number; max: number; count: number; by_type: Record<string, number> };
  total_commands: number;
}

export interface AnalyticsTrend {
  trend: "up" | "down" | "stable" | "insufficient_data";
  trend_percentage: number;
  recent_total?: number;
  previous_total?: number;
}

export interface AnalyticsRecommendation {
  type: string;
  title: string;
  message: string;
}

export interface VersionItem {
  item_id: string;
  item_type: string;
  current_version: number;
  versions_count: number;
}

export interface VersionEntry {
  version_number: number;
  data: Record<string, unknown>;
  author: string;
  change_description: string;
  created_at: string;
}

export interface AiModelOption {
  id: string;
  note: string;
}

export interface AiProvider {
  id: string;
  note: string;
  configured: boolean;
  models: AiModelOption[];
}

export interface AiStatus {
  enabled: boolean;
  model: string;
  provider: string | null;
  temperature: number;
}

export class BackendClient {
  constructor(private baseUrl: string) {}

  withBaseUrl(baseUrl: string): BackendClient {
    return new BackendClient(baseUrl);
  }

  private url(path: string): string {
    return `${this.baseUrl.replace(/\/+$/, "")}${path}`;
  }

  async health(): Promise<boolean> {
    try {
      const res = await fetch(this.url("/health"), { signal: AbortSignal.timeout(4000) });
      return res.ok;
    } catch {
      return false;
    }
  }

  async ask(question: string): Promise<string> {
    const res = await fetch(this.url("/ask"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(30000),
    });

    const body = await res.json().catch(() => null);

    if (!res.ok || !body || body.success === false) {
      const message = body?.error ?? `HTTP ${res.status}`;
      throw new ApiError(message);
    }

    return body?.data?.answer ?? "";
  }

  async metrics(): Promise<Metrics> {
    const res = await fetch(this.url("/metrics"), { signal: AbortSignal.timeout(4000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    const body = await res.json();
    return {
      cpuPercent: body?.metrics?.cpu ?? 0,
      ramPercent: body?.metrics?.ram ?? 0,
      processCount: body?.metrics?.processes ?? 0,
    };
  }

  /** Распознать речь из записанного аудио (webm/opus из MediaRecorder). */
  async speechToText(audio: Blob): Promise<string> {
    const form = new FormData();
    form.append("file", audio, "voice.webm");

    const res = await fetch(this.url("/speech_to_text"), {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(30000),
    });

    const body = await res.json().catch(() => null);
    if (!res.ok || !body?.success) {
      throw new ApiError(body?.message ?? `HTTP ${res.status}`);
    }
    return body.text ?? "";
  }

  /** Озвучить текст голосом Scott — возвращает аудио (mp3) как Blob. Голос — опционально (см. listVoices()). */
  async textToSpeech(text: string, voice?: string | null): Promise<Blob> {
    const res = await fetch(this.url("/text_to_speech"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: voice ?? undefined }),
      signal: AbortSignal.timeout(45000),
    });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    return res.blob();
  }

  /** Список доступных голосов Edge TTS (для выбора в Настройках). */
  async listVoices(): Promise<{ voices: { id: string; label: string }[]; default: string }> {
    const res = await fetch(this.url("/voice/available"), { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    return res.json();
  }

  private async postJson(path: string, body: unknown): Promise<any> {
    const res = await fetch(this.url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data || data.success === false || data.error) {
      throw new ApiError(data?.error ?? `HTTP ${res.status}`);
    }
    return data;
  }

  private async getJson(path: string): Promise<any> {
    const res = await fetch(this.url(path), { signal: AbortSignal.timeout(10000) });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data || data.error) {
      throw new ApiError(data?.error ?? `HTTP ${res.status}`);
    }
    return data;
  }

  // ---------- Кастомные команды ----------

  async listCustomCommands(): Promise<CustomCommand[]> {
    const body = await this.getJson("/custom-commands/list?enabled_only=false");
    return body.commands ?? [];
  }

  async addCustomCommand(cmd: { name: string; trigger: string; action: string; description?: string }): Promise<CustomCommand> {
    const body = await this.postJson("/custom-commands/add", cmd);
    return body.command;
  }

  async updateCustomCommand(name: string, updates: Partial<Omit<CustomCommand, "name" | "created_at" | "usage_count">>): Promise<CustomCommand> {
    const body = await this.postJson("/custom-commands/update", { name, ...updates });
    return body.command;
  }

  async deleteCustomCommand(name: string): Promise<void> {
    await this.postJson("/custom-commands/delete", { name });
  }

  // ---------- IFTTT-правила ----------

  async listIftttRules(): Promise<IftttRule[]> {
    const body = await this.getJson("/ifttt/rules?enabled_only=false");
    return body.rules ?? [];
  }

  async addIftttRule(rule: {
    name: string;
    trigger_type: string;
    trigger_value: string;
    action_type: string;
    action_value: string;
    logic?: "AND" | "OR";
    description?: string;
  }): Promise<IftttRule> {
    const body = await this.postJson("/ifttt/add-rule", rule);
    return body.rule;
  }

  async updateIftttRule(name: string, updates: Partial<Pick<IftttRule, "action_value" | "description" | "enabled" | "logic" | "conditions">>): Promise<IftttRule> {
    const body = await this.postJson("/ifttt/update-rule", { name, ...updates });
    return body.rule;
  }

  async deleteIftttRule(name: string): Promise<void> {
    await this.postJson("/ifttt/delete-rule", { name });
  }

  // ---------- v3.3 envelope ({success,message,data} или {detail} при ошибке) ----------

  private async v33Post(path: string, body: unknown): Promise<any> {
    const res = await fetch(this.url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(data?.detail ?? `HTTP ${res.status}`);
    if (data?.success === false) throw new ApiError(data?.message ?? "Неизвестная ошибка");
    return data?.data;
  }

  private async v33Get(path: string): Promise<any> {
    const res = await fetch(this.url(path), { signal: AbortSignal.timeout(15000) });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(data?.detail ?? `HTTP ${res.status}`);
    if (data?.success === false) throw new ApiError(data?.message ?? "Неизвестная ошибка");
    return data?.data;
  }

  // ---------- Выполнение произвольной команды Scott (используется при применении шаблонов) ----------

  async runCommand(text: string): Promise<void> {
    await fetch(this.url("/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: AbortSignal.timeout(20000),
    });
  }

  // ---------- Макросы ----------

  async listMacros(): Promise<Macro[]> {
    return (await this.v33Get("/macros/list?enabled_only=false")) ?? [];
  }

  async macroRecordingStatus(): Promise<RecordingStatus> {
    return await this.v33Get("/macros/status");
  }

  async startMacroRecording(name: string): Promise<void> {
    await this.v33Post("/macros/start-recording", { name });
  }

  async stopMacroRecording(): Promise<Macro> {
    return await this.v33Post("/macros/stop-recording", {});
  }

  async recordMacroAction(action: { action_type: string; target: string; x?: number; y?: number; details?: Record<string, unknown> }): Promise<void> {
    await this.v33Post("/macros/record-action", { x: 0, y: 0, ...action });
  }

  async executeMacro(name: string, loopCount = 1): Promise<void> {
    await this.v33Post("/macros/execute", { name, loop_count: loopCount });
  }

  async deleteMacro(name: string): Promise<void> {
    await this.v33Post(`/macros/delete?name=${encodeURIComponent(name)}`, null);
  }

  // ---------- Шаблоны ----------

  async listTemplates(): Promise<Template[]> {
    return (await this.v33Get("/templates/list")) ?? [];
  }

  async listTemplateCategories(): Promise<string[]> {
    return (await this.v33Get("/templates/categories")) ?? [];
  }

  async createTemplate(tpl: { name: string; category: string; description?: string; icon?: string; commands?: string[] }): Promise<Template> {
    return await this.v33Post("/templates/create", { rules: [], ...tpl, commands: tpl.commands ?? [] });
  }

  async deleteTemplate(name: string): Promise<void> {
    await this.v33Post("/templates/delete", { name });
  }

  /**
   * Применить шаблон. Backend лишь увеличивает счётчик популярности и возвращает
   * сам шаблон — реально выполнить его команды/правила должен клиент (используя
   * template.commands/template.rules), т.к. backend это не делает.
   */
  async applyTemplate(name: string): Promise<Template> {
    return await this.v33Post("/templates/apply", { name });
  }

  // ---------- Аналитика (v3.2, плоские эндпоинты без envelope) ----------

  async getAnalytics(): Promise<Analytics> {
    const res = await fetch(this.url("/analytics/comprehensive"), { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    return res.json();
  }

  async getAnalyticsTrend(): Promise<AnalyticsTrend> {
    const res = await fetch(this.url("/analytics/trends"), { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    return res.json();
  }

  async getAnalyticsRecommendations(): Promise<AnalyticsRecommendation[]> {
    const res = await fetch(this.url("/analytics/recommendations"), { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    const body = await res.json();
    return body?.recommendations ?? [];
  }

  // ---------- Версионирование ----------

  async listVersionedItems(): Promise<VersionItem[]> {
    return (await this.v33Get("/versions/items")) ?? [];
  }

  async getVersionHistory(itemId: string): Promise<{ item_id: string; item_type: string; versions: VersionEntry[]; current_version: number } | null> {
    const data = await this.v33Get(`/versions/history?item_id=${encodeURIComponent(itemId)}`);
    return data && Object.keys(data).length > 0 ? data : null;
  }

  async trackVersion(itemId: string, itemType: string, data: object, description = ""): Promise<void> {
    await this.v33Post("/versions/track", { item_id: itemId, item_type: itemType, data, description });
  }

  async rollbackVersion(itemId: string, version: number): Promise<Record<string, unknown>> {
    return await this.v33Post("/versions/rollback", { item_id: itemId, version });
  }

  // ---------- Модель ИИ (провайдер/модель/свой API-ключ) ----------

  async getAiStatus(): Promise<AiStatus> {
    const res = await fetch(this.url("/ai/status"), { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    return res.json();
  }

  async listAiProviders(): Promise<{ providers: AiProvider[]; active_provider: string | null; active_model: string }> {
    const res = await fetch(this.url("/ai/providers"), { signal: AbortSignal.timeout(15000) });
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`);
    return res.json();
  }

  async configureAi(provider: string, model: string, apiKey?: string): Promise<{ success: boolean; provider?: string; model?: string; error?: string }> {
    const res = await fetch(this.url("/ai/configure"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model, api_key: apiKey || undefined }),
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(data?.error ?? `HTTP ${res.status}`);
    return data;
  }
}
