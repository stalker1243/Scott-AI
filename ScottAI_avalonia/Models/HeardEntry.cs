using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Одна услышанная фраза и то, что из неё вышло.
///
/// Голосом Scott умеет меньше, чем в чате, — и это первое, что замечает
/// человек. Но разбор у голоса и чата ОДИН И ТОТ ЖЕ: дело не в возможностях, а
/// в тексте, который до разбора доходит. Здесь видно, каким он приходит.
/// </summary>
public class HeardEntry
{
    [JsonPropertyName("at")]
    public double At { get; set; }

    /// <summary>Что Scott расслышал — целиком, вместе с именем.</summary>
    [JsonPropertyName("text")]
    public string Text { get; set; } = "";

    /// <summary>«выполнена» | «мимо» | «имя без команды» | «ошибка».</summary>
    [JsonPropertyName("outcome")]
    public string Outcome { get; set; } = "";

    /// <summary>Что осталось после снятия имени. По нему видно, верно ли оно снялось.</summary>
    [JsonPropertyName("command")]
    public string Command { get; set; } = "";

    /// <summary>Сколько длилась запись.</summary>
    [JsonPropertyName("seconds")]
    public double? Seconds { get; set; }

    public string TimeText =>
        DateTimeOffset.FromUnixTimeSeconds((long)At).LocalDateTime.ToString("HH:mm:ss");

    public string SecondsText => Seconds is null ? "" : $"{Seconds:0.0} с";

    /// <summary>
    /// Прошло мимо — Scott не узнал в сказанном своё имя.
    ///
    /// Именно эти строки и есть потерянные команды: человек говорил, Scott
    /// слышал, но промолчал. Их выделяем, остальное приглушаем.
    /// </summary>
    public bool Missed => Outcome == "мимо";

    public bool Done => Outcome == "выполнена";

    public bool HasCommand => Command.Length > 0;
}

/// <summary>Сводка по услышанному: сколько всего и чем кончилось.</summary>
public class HeardSummary
{
    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("outcomes")]
    public Dictionary<string, int> Outcomes { get; set; } = new();
}

public class HeardResponse
{
    [JsonPropertyName("heard")]
    public List<HeardEntry> Heard { get; set; } = new();

    [JsonPropertyName("summary")]
    public HeardSummary Summary { get; set; } = new();
}
