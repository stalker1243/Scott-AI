using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Одно умение Scott: что он делает и как его об этом просить.
/// </summary>
public class Ability
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    [JsonPropertyName("detail")]
    public string Detail { get; set; } = "";

    /// <summary>
    /// Примеры фраз — не украшение.
    ///
    /// Это единственный способ показать, КАК просить: Scott понимает «сделай
    /// громче», но не «увеличь звук на 20 процентов», и узнать об этом иначе
    /// неоткуда.
    /// </summary>
    [JsonPropertyName("examples")]
    public List<string> Examples { get; set; } = new();

    /// <summary>"ready" | "off".</summary>
    [JsonPropertyName("state")]
    public string State { get; set; } = "ready";

    /// <summary>Почему недоступно — если недоступно.</summary>
    [JsonPropertyName("reason")]
    public string Reason { get; set; } = "";

    public bool Ready => State == "ready";
    public bool Unavailable => State != "ready";
}

/// <summary>Умения, сгруппированные по тому, к чему они относятся.</summary>
public class AbilityGroup
{
    [JsonPropertyName("group")]
    public string Group { get; set; } = "";

    [JsonPropertyName("items")]
    public List<Ability> Items { get; set; } = new();
}

public class AbilitiesResponse
{
    [JsonPropertyName("groups")]
    public List<AbilityGroup> Groups { get; set; } = new();

    [JsonPropertyName("ready")]
    public int Ready { get; set; }

    [JsonPropertyName("total")]
    public int Total { get; set; }
}
