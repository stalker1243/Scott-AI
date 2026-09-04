using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>Состояние одного движка: что выбрано и что используется на самом деле.</summary>
public class EngineDevice
{
    /// <summary>Выбор пользователя: auto, cuda или cpu.</summary>
    [JsonPropertyName("choice")]
    public string Choice { get; set; } = "auto";

    /// <summary>
    /// Устройство, на котором движок работает сейчас.
    ///
    /// От выбора отличается: при «авто» на машине без видеокарты выбор
    /// останется auto, а устройством будет cpu.
    /// </summary>
    [JsonPropertyName("device")]
    public string Device { get; set; } = "cpu";

    /// <summary>Задано переменной в .env — тогда кнопки в интерфейсе бессильны.</summary>
    [JsonPropertyName("locked_by_env")]
    public bool LockedByEnv { get; set; }

    [JsonPropertyName("env_var")]
    public string EnvVar { get; set; } = "";
}

public class DeviceSettingsResponse
{
    [JsonPropertyName("cuda_available")]
    public bool CudaAvailable { get; set; }

    [JsonPropertyName("engines")]
    public Dictionary<string, EngineDevice> Engines { get; set; } = new();

    [JsonPropertyName("message")]
    public string? Message { get; set; }

    [JsonPropertyName("success")]
    public bool Success { get; set; } = true;
}
