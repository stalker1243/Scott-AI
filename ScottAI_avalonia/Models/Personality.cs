using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Характер, которым Scott разговаривает.
///
/// Список приходит с backend, а не записан здесь: добавленный там характер
/// должен появиться в интерфейсе сам, без пересборки программы.
/// </summary>
public class PersonalityStyle
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    /// <summary>Одна строка о том, чем этот характер отличается от других.</summary>
    [JsonPropertyName("hint")]
    public string Hint { get; set; } = "";
}

/// <summary>
/// Персонализация: как Scott говорит и что знает о своём человеке.
///
/// Всё это уходит в каждый запрос к модели. Раньше поле «О себе» существовало
/// только в лаунчере и до Scott не доходило вовсе — человек писал о себе, а
/// ответы получал ровно те же, что и все.
/// </summary>
public class PersonalitySettings
{
    [JsonPropertyName("style")]
    public string Style { get; set; } = "friendly";

    [JsonPropertyName("about")]
    public string About { get; set; } = "";

    [JsonPropertyName("interests")]
    public List<string> Interests { get; set; } = new();

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("styles")]
    public List<PersonalityStyle> Styles { get; set; } = new();
}
