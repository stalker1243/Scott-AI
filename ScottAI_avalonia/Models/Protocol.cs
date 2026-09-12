using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Один шаг протокола.
///
/// Шаг записан теми же словами, какими человек сказал бы его голосом, — «открой
/// браузер», а не названием действия с параметрами. Так протоколу достаётся
/// весь разбор, уже отлаженный на сотнях фраз, и человеку, который составляет
/// протокол, не нужно знать ни одного названия действия.
/// </summary>
public class ProtocolStep
{
    [JsonPropertyName("text")]
    public string Text { get; set; } = "";

    /// <summary>
    /// Сколько подождать после шага, секунд.
    ///
    /// Нужна чаще, чем кажется: программа, которую только что попросили
    /// открыться, не готова принять следующую команду сразу.
    /// </summary>
    [JsonPropertyName("pause")]
    public double Pause { get; set; }
}

/// <summary>Именованная последовательность шагов.</summary>
public class Protocol
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("steps")]
    public List<ProtocolStep> Steps { get; set; } = new();

    /// <summary>Чем протокол зовётся, кроме «протокол &lt;имя&gt;».</summary>
    [JsonPropertyName("phrases")]
    public List<string> Phrases { get; set; } = new();

    [JsonPropertyName("description")]
    public string Description { get; set; } = "";

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; } = true;

    [JsonPropertyName("runs")]
    public int Runs { get; set; }

    [JsonPropertyName("last_run")]
    public string? LastRun { get; set; }

    /// <summary>Шаги одной строкой — то, что видно в списке.</summary>
    public string StepsLine => string.Join(" → ", Steps.Select(s => s.Text));

    public string Counter => Runs == 0 ? "ни разу не запускался" : $"запусков: {Runs}";

    /// <summary>Как позвать протокол голосом.</summary>
    public string CallHint => Phrases.Count > 0
        ? $"«протокол {Name}» или «{string.Join("», «", Phrases)}»"
        : $"«протокол {Name}»";
}
