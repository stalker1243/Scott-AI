using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>Одно звуковое устройство: микрофон или динамики.</summary>
public class AudioDevice
{
    [JsonPropertyName("index")]
    public int Index { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    /// <summary>Системное по умолчанию — его помечаем в списке.</summary>
    [JsonPropertyName("default")]
    public bool IsDefault { get; set; }

    /// <summary>
    /// Что показать в списке.
    ///
    /// Пустое имя означает «как в системе»: этим же элементом человек
    /// возвращается к автоматике, не разыскивая своё устройство в списке.
    /// </summary>
    public string Display => string.IsNullOrEmpty(Name)
        ? "Как в системе"
        : (IsDefault ? $"{Name} — по умолчанию" : Name);
}

public class AudioDeviceLists
{
    [JsonPropertyName("input")]
    public List<AudioDevice> Input { get; set; } = new();

    [JsonPropertyName("output")]
    public List<AudioDevice> Output { get; set; } = new();
}

/// <summary>Что Scott помнит про звук между запусками.</summary>
public class AudioSettings
{
    /// <summary>Имя микрофона; пусто — системный.</summary>
    [JsonPropertyName("input_device")]
    public string InputDevice { get; set; } = "";

    /// <summary>Имя динамиков; пусто — системные.</summary>
    [JsonPropertyName("output_device")]
    public string OutputDevice { get; set; } = "";

    /// <summary>Громкость речи в процентах.</summary>
    [JsonPropertyName("volume")]
    public int Volume { get; set; } = 100;

    /// <summary>Тихий режим: Scott слышит и выполняет, но молчит.</summary>
    [JsonPropertyName("quiet")]
    public bool Quiet { get; set; }
}

public class AudioSettingsResponse
{
    [JsonPropertyName("success")]
    public bool Success { get; set; } = true;

    /// <summary>Есть ли на машине звуковая подсистема вообще.</summary>
    [JsonPropertyName("available")]
    public bool Available { get; set; }

    [JsonPropertyName("settings")]
    public AudioSettings Settings { get; set; } = new();

    [JsonPropertyName("devices")]
    public AudioDeviceLists Devices { get; set; } = new();

    [JsonPropertyName("message")]
    public string? Message { get; set; }
}
