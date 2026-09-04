using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>Одна строка об ошибке из лога backend — то, что видно на вкладке «Логи».</summary>
public class LogEntry
{
    [JsonPropertyName("time")]
    public string Time { get; set; } = "";

    [JsonPropertyName("text")]
    public string Text { get; set; } = "";
}

public class LogEntriesResponse
{
    [JsonPropertyName("errors")]
    public List<LogEntry> Errors { get; set; } = new();
}

/// <summary>
/// Что известно про видеокарту и какое устройство используется для распознавания
/// и синтеза речи.
///
/// Показывается пользователю не из любопытства: обычная команда `pip install torch`
/// ставит сборку для процессора и молча игнорирует видеокарту. Разница
/// принципиальная — на процессоре Whisper распознаёт короткую фразу около
/// 6.6 секунды, на видеокарте это доли секунды. Без такой подсказки человек
/// просто считает, что «Scott тормозит».
/// </summary>
public class GpuInfo
{
    [JsonPropertyName("cuda_доступна")]
    public bool CudaAvailable { get; set; }

    [JsonPropertyName("torch")]
    public string Torch { get; set; } = "";

    [JsonPropertyName("сборка_с_cuda")]
    public bool CudaBuild { get; set; }

    [JsonPropertyName("устройство")]
    public string? Device { get; set; }

    [JsonPropertyName("память_гб")]
    public double? MemoryGb { get; set; }

    [JsonPropertyName("подсказка")]
    public string? Hint { get; set; }
}

/// <summary>Результат сборки архива с логами.</summary>
public class ReportResult
{
    [JsonPropertyName("success")]
    public bool Success { get; set; }

    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    [JsonPropertyName("folder")]
    public string Folder { get; set; } = "";

    [JsonPropertyName("size_bytes")]
    public long SizeBytes { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; } = "";
}
