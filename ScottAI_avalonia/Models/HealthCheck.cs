using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Одна проверка состояния: работает ли эта часть Scott прямо сейчас.
/// </summary>
public class HealthCheck
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    /// <summary>"ok" | "warn" | "fail".</summary>
    [JsonPropertyName("state")]
    public string State { get; set; } = "ok";

    /// <summary>Объяснение словами — оно и есть главное содержимое строки.</summary>
    [JsonPropertyName("detail")]
    public string Detail { get; set; } = "";

    public bool IsOk => State == "ok";
    public bool IsWarn => State == "warn";
    public bool IsFail => State == "fail";
}

/// <summary>Все проверки вместе с итогом.</summary>
public class HealthReport
{
    [JsonPropertyName("state")]
    public string State { get; set; } = "ok";

    /// <summary>Итог одной строкой: «Всё работает», «Не работает: 2».</summary>
    [JsonPropertyName("summary")]
    public string Summary { get; set; } = "";

    [JsonPropertyName("checks")]
    public List<HealthCheck> Checks { get; set; } = new();
}
