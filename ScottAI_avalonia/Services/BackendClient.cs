using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using ScottAI.Avalonia.Models;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Тонкий HTTP-клиент к тому же backend (FastAPI, backend/main.py), которым
/// пользуется и Tauri-версия лаунчера — backend полностью переиспользуется,
/// без единой правки на его стороне.
/// </summary>
public class BackendClient
{
    private readonly HttpClient _http;

    public BackendClient(string baseUrl = "http://127.0.0.1:8000")
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl), Timeout = TimeSpan.FromSeconds(30) };
    }

    public async Task<bool> HealthAsync()
    {
        try
        {
            using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(4));
            var res = await _http.GetAsync("/health", cts.Token);
            return res.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public async Task<MetricsResponse?> MetricsAsync()
    {
        try
        {
            using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(4));
            return await _http.GetFromJsonAsync<MetricsResponse>("/metrics", cts.Token);
        }
        catch
        {
            return null;
        }
    }

    public async Task<string> AskAsync(string question, bool quietMode = true)
    {
        var res = await _http.PostAsJsonAsync("/ask", new { question, quiet_mode = quietMode });
        res.EnsureSuccessStatusCode();
        var body = await res.Content.ReadFromJsonAsync<AskResponse>();
        return body?.Data?.Answer ?? "";
    }

    // ---------- Голос ----------

    /// <summary>
    /// Список голосов Scott. gender="male" оставит только мужские — фильтрует
    /// backend, чтобы лаунчер не знал имён конкретных голосов.
    /// </summary>
    public async Task<(List<VoiceOption> Voices, string Current)> ListVoicesAsync(string gender = "male")
    {
        var body = await _http.GetFromJsonAsync<VoicesResponse>($"/voice/available?gender={gender}");
        return (body?.Voices ?? new List<VoiceOption>(), body?.Current ?? "");
    }

    /// <summary>Переключить голос Scott — действует сразу, без перезапуска backend.</summary>
    public async Task<(bool Success, string Message)> SelectVoiceAsync(string voiceId)
    {
        var res = await _http.PostAsJsonAsync("/voice/select", new { voice = voiceId });
        var body = await res.Content.ReadFromJsonAsync<VoiceSelectResponse>();
        return (body?.Success ?? false, body?.Message ?? "");
    }

    /// <summary>
    /// Озвучить текст голосом Scott — backend проигрывает его сам через локальные
    /// колонки той же машины (edge-tts/pyttsx3 внутри ScottVoice), поэтому здесь не
    /// нужен отдельный аудио-плеер или получение байтов обратно.
    /// </summary>
    public async Task SpeakAsync(string text)
    {
        try
        {
            using var content = new FormUrlEncodedContent(new Dictionary<string, string> { ["text"] = text });
            await _http.PostAsync("/speak", content);
        }
        catch
        {
            // озвучка — не критичная функция, тихо игнорируем сбой (например, backend недоступен)
        }
    }

    // ---------- Система: процессы ----------

    public async Task<List<ProcessInfo>> ListProcessesAsync()
    {
        var body = await _http.GetFromJsonAsync<ListProcessesResponse>("/list-processes");
        return body?.Processes ?? new List<ProcessInfo>();
    }

    /// <summary>
    /// Завершить процесс. /kill-process защищён Bearer-токеном (EXECUTE_TOKEN
    /// из .env) — тем же, что уже проверяет backend/security.py, без
    /// отдельного секрета для этой версии лаунчера.
    /// </summary>
    public async Task<(bool Success, string Message)> KillProcessAsync(int pid)
    {
        var token = EnvConfig.Get("EXECUTE_TOKEN");
        if (string.IsNullOrEmpty(token))
            return (false, "EXECUTE_TOKEN не найден в .env — защищённые действия недоступны");

        using var req = new HttpRequestMessage(HttpMethod.Post, "/kill-process")
        {
            Content = JsonContent.Create(new { pid })
        };
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);

        var res = await _http.SendAsync(req);
        var body = await res.Content.ReadFromJsonAsync<KillProcessResponse>();
        return (body?.Success ?? false, body?.Message ?? $"HTTP {(int)res.StatusCode}");
    }

    // ---------- Автоматизация: кастомные команды ----------

    public async Task<List<CustomCommand>> ListCustomCommandsAsync()
    {
        var body = await _http.GetFromJsonAsync<CustomCommandsListResponse>("/custom-commands/list?enabled_only=false");
        return body?.Commands ?? new List<CustomCommand>();
    }

    public async Task<(bool Success, string Message)> AddCustomCommandAsync(string name, string trigger, string action, string description)
    {
        var res = await _http.PostAsJsonAsync("/custom-commands/add", new { name, trigger, action, description });
        var body = await res.Content.ReadFromJsonAsync<SimpleResponse>();
        return (body?.Success ?? false, body?.Message ?? body?.Error ?? $"HTTP {(int)res.StatusCode}");
    }

    public async Task<(bool Success, string Message)> DeleteCustomCommandAsync(string name)
    {
        var res = await _http.PostAsJsonAsync("/custom-commands/delete", new { name });
        var body = await res.Content.ReadFromJsonAsync<SimpleResponse>();
        return (body?.Success ?? false, body?.Message ?? body?.Error ?? $"HTTP {(int)res.StatusCode}");
    }

    // ---------- v3.3 envelope-хелперы ({success,message,data}) ----------

    private async Task<T?> V33GetAsync<T>(string path)
    {
        var envelope = await _http.GetFromJsonAsync<V33Envelope<T>>(path);
        return envelope is { Success: true } ? envelope.Data : default;
    }

    private async Task<(bool Success, string Message, T? Data)> V33PostAsync<T>(string path, object? body)
    {
        var res = body is null ? await _http.PostAsync(path, null) : await _http.PostAsJsonAsync(path, body);
        var envelope = await res.Content.ReadFromJsonAsync<V33Envelope<T>>();
        return (envelope?.Success ?? false, envelope?.Message ?? $"HTTP {(int)res.StatusCode}", envelope is { Success: true } ? envelope.Data : default);
    }

    // ---------- IFTTT ----------

    public async Task<List<IftttRule>> ListIftttRulesAsync()
    {
        var body = await _http.GetFromJsonAsync<IftttListResponse>("/ifttt/rules?enabled_only=false");
        return body?.Rules ?? new List<IftttRule>();
    }

    public async Task<(bool Success, string Message)> AddIftttRuleAsync(string name, string triggerType, string triggerValue, string actionType, string actionValue, string description)
    {
        var res = await _http.PostAsJsonAsync("/ifttt/add-rule", new { name, trigger_type = triggerType, trigger_value = triggerValue, action_type = actionType, action_value = actionValue, description });
        var body = await res.Content.ReadFromJsonAsync<SimpleResponse>();
        return (body?.Success ?? false, body?.Message ?? body?.Error ?? $"HTTP {(int)res.StatusCode}");
    }

    public async Task<(bool Success, string Message)> DeleteIftttRuleAsync(string name)
    {
        var res = await _http.PostAsJsonAsync("/ifttt/delete-rule", new { name });
        var body = await res.Content.ReadFromJsonAsync<SimpleResponse>();
        return (body?.Success ?? false, body?.Message ?? body?.Error ?? $"HTTP {(int)res.StatusCode}");
    }

    // ---------- Макросы ----------

    public Task<List<Macro>> ListMacrosAsync() => V33GetAsync<List<Macro>>("/macros/list?enabled_only=false")!.ContinueWith(t => t.Result ?? new List<Macro>());

    public Task<MacroRecordingStatus?> MacroStatusAsync() => V33GetAsync<MacroRecordingStatus>("/macros/status");

    public async Task<(bool Success, string Message)> StartMacroRecordingAsync(string name)
    {
        var (success, message, _) = await V33PostAsync<object>("/macros/start-recording", new { name });
        return (success, message);
    }

    public async Task<(bool Success, string Message)> StopMacroRecordingAsync()
    {
        var (success, message, _) = await V33PostAsync<Macro>("/macros/stop-recording", new { });
        return (success, message);
    }

    public async Task<(bool Success, string Message)> RecordMacroActionAsync(string actionType, string target)
    {
        var (success, message, _) = await V33PostAsync<object>("/macros/record-action", new { action_type = actionType, target, x = 0, y = 0 });
        return (success, message);
    }

    public async Task<(bool Success, string Message)> ExecuteMacroAsync(string name, int loopCount)
    {
        var (success, message, _) = await V33PostAsync<object>("/macros/execute", new { name, loop_count = loopCount });
        return (success, message);
    }

    public async Task<(bool Success, string Message)> DeleteMacroAsync(string name)
    {
        var res = await _http.PostAsync($"/macros/delete?name={Uri.EscapeDataString(name)}", null);
        var body = await res.Content.ReadFromJsonAsync<V33Envelope<object>>();
        return (body?.Success ?? false, body?.Message ?? $"HTTP {(int)res.StatusCode}");
    }

    // ---------- Шаблоны ----------

    public Task<List<ScottTemplate>> ListTemplatesAsync() => V33GetAsync<List<ScottTemplate>>("/templates/list")!.ContinueWith(t => t.Result ?? new List<ScottTemplate>());

    public async Task<(bool Success, string Message)> CreateTemplateAsync(string name, string category, string description, List<string> commands)
    {
        var (success, message, _) = await V33PostAsync<ScottTemplate>("/templates/create", new { name, category, description, commands, rules = new List<object>() });
        return (success, message);
    }

    public async Task<(bool Success, string Message)> DeleteTemplateAsync(string name)
    {
        var (success, message, _) = await V33PostAsync<object>("/templates/delete", new { name });
        return (success, message);
    }

    public async Task<(bool Success, string Message, ScottTemplate? Template)> ApplyTemplateAsync(string name)
        => await V33PostAsync<ScottTemplate>("/templates/apply", new { name });

    public async Task RunCommandAsync(string text)
    {
        await _http.PostAsJsonAsync("/command", new { text });
    }

    // ---------- Аналитика ----------

    public Task<Analytics?> GetAnalyticsAsync() => _http.GetFromJsonAsync<Analytics>("/analytics/comprehensive");

    public Task<AnalyticsTrend?> GetAnalyticsTrendAsync() => _http.GetFromJsonAsync<AnalyticsTrend>("/analytics/trends");

    public async Task<List<AnalyticsRecommendation>> GetRecommendationsAsync()
    {
        var body = await _http.GetFromJsonAsync<RecommendationsResponse>("/analytics/recommendations");
        return body?.Recommendations ?? new List<AnalyticsRecommendation>();
    }

    // ---------- Модель ИИ ----------

    public async Task<(List<AiProvider> Providers, string? ActiveProvider, string ActiveModel)> ListAiProvidersAsync()
    {
        var body = await _http.GetFromJsonAsync<AiProvidersResponse>("/ai/providers");
        return (body?.Providers ?? new List<AiProvider>(), body?.ActiveProvider, body?.ActiveModel ?? "");
    }

    public async Task<(bool Success, string Message)> ConfigureAiAsync(string provider, string model, string? apiKey)
    {
        var res = await _http.PostAsJsonAsync("/ai/configure", new { provider, model, api_key = apiKey });
        var body = await res.Content.ReadFromJsonAsync<AiConfigureResponse>();
        return (body?.Success ?? false, body?.Error ?? (body?.Success == true ? $"Активна модель: {body.Provider}/{body.Model}" : $"HTTP {(int)res.StatusCode}"));
    }

    // ---------- Версионирование ----------

    public Task<List<VersionItem>> ListVersionedItemsAsync() => V33GetAsync<List<VersionItem>>("/versions/items")!.ContinueWith(t => t.Result ?? new List<VersionItem>());

    public Task<VersionHistory?> GetVersionHistoryAsync(string itemId) => V33GetAsync<VersionHistory>($"/versions/history?item_id={Uri.EscapeDataString(itemId)}");

    public async Task<(bool Success, string Message)> RollbackVersionAsync(string itemId, int version)
    {
        var (success, message, _) = await V33PostAsync<object>("/versions/rollback", new { item_id = itemId, version });
        return (success, message);
    }

    // ---------- Диагностика ----------

    /// <summary>Последние ошибки из лога backend. Секреты вырезаны на стороне backend.</summary>
    public async Task<List<LogEntry>> RecentErrorsAsync(int limit = 50)
    {
        try
        {
            var body = await _http.GetFromJsonAsync<LogEntriesResponse>($"/diagnostics/errors?limit={limit}");
            return body?.Errors ?? new List<LogEntry>();
        }
        catch
        {
            return new List<LogEntry>();
        }
    }

    public async Task<GpuInfo?> GpuInfoAsync()
    {
        try
        {
            return await _http.GetFromJsonAsync<GpuInfo>("/diagnostics/gpu");
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Собрать архив с логами для отправки разработчику.
    ///
    /// Сборка читает и переписывает несколько файлов, поэтому таймаут здесь
    /// больше общего: на разросшемся логе это занимает заметное время.
    /// </summary>
    public async Task<ReportResult?> BuildReportAsync(string? note)
    {
        try
        {
            using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(60));
            var res = await _http.PostAsJsonAsync("/diagnostics/report", new { note }, cts.Token);
            return await res.Content.ReadFromJsonAsync<ReportResult>(cancellationToken: cts.Token);
        }
        catch
        {
            return null;
        }
    }
}

public class MetricsResponse
{
    [JsonPropertyName("metrics")]
    public MetricsInner? Metrics { get; set; }
}

public class MetricsInner
{
    [JsonPropertyName("cpu")]
    public double Cpu { get; set; }

    [JsonPropertyName("ram")]
    public double Ram { get; set; }

    [JsonPropertyName("processes")]
    public int Processes { get; set; }
}

public class AskResponse
{
    [JsonPropertyName("success")]
    public bool Success { get; set; }

    [JsonPropertyName("data")]
    public AskData? Data { get; set; }
}

public class AskData
{
    [JsonPropertyName("answer")]
    public string? Answer { get; set; }
}

public class ListProcessesResponse
{
    [JsonPropertyName("processes")]
    public List<ProcessInfo>? Processes { get; set; }
}

public class KillProcessResponse
{
    [JsonPropertyName("success")]
    public bool Success { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }
}

public class CustomCommandsListResponse
{
    [JsonPropertyName("commands")]
    public List<CustomCommand>? Commands { get; set; }
}

public class SimpleResponse
{
    [JsonPropertyName("success")]
    public bool Success { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }
}

public class V33Envelope<T>
{
    [JsonPropertyName("success")] public bool Success { get; set; }
    [JsonPropertyName("message")] public string? Message { get; set; }
    [JsonPropertyName("data")] public T? Data { get; set; }
}

public class IftttListResponse
{
    [JsonPropertyName("rules")] public List<IftttRule>? Rules { get; set; }
}

public class RecommendationsResponse
{
    [JsonPropertyName("recommendations")] public List<AnalyticsRecommendation>? Recommendations { get; set; }
}

public class AiProvidersResponse
{
    [JsonPropertyName("providers")] public List<AiProvider>? Providers { get; set; }
    [JsonPropertyName("active_provider")] public string? ActiveProvider { get; set; }
    [JsonPropertyName("active_model")] public string? ActiveModel { get; set; }
}

public class AiConfigureResponse
{
    [JsonPropertyName("success")] public bool Success { get; set; }
    [JsonPropertyName("provider")] public string? Provider { get; set; }
    [JsonPropertyName("model")] public string? Model { get; set; }
    [JsonPropertyName("error")] public string? Error { get; set; }
}

public class VoicesResponse
{
    [JsonPropertyName("voices")] public List<VoiceOption>? Voices { get; set; }
    [JsonPropertyName("current")] public string? Current { get; set; }
}

public class VoiceSelectResponse
{
    [JsonPropertyName("success")] public bool Success { get; set; }
    [JsonPropertyName("voice")] public string? Voice { get; set; }
    [JsonPropertyName("message")] public string? Message { get; set; }
}
