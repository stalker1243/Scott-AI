using System;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Проект, над которым человек работает.
///
/// Не просто запись в списке: по названию Scott открывает папку, а текущий
/// проект держит в уме, отвечая на вопросы о работе.
/// </summary>
public class Project
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    /// <summary>На чём написан — «C# и Avalonia», «Python».</summary>
    [JsonPropertyName("stack")]
    public string Stack { get; set; } = "";

    [JsonPropertyName("note")]
    public string Note { get; set; } = "";

    [JsonPropertyName("created")]
    public double Created { get; set; }

    /// <summary>Над этим проектом человек работает сейчас.</summary>
    [JsonPropertyName("current")]
    public bool Current { get; set; }

    /// <summary>
    /// Папка на месте.
    ///
    /// Её могли удалить или перенести уже после того, как проект завели, — и
    /// честнее показать это сразу, чем молча не открыть по просьбе.
    /// </summary>
    [JsonPropertyName("exists")]
    public bool Exists { get; set; }

    public bool PathMissing => Path.Length > 0 && !Exists;

    public string CreatedText => Created <= 0
        ? ""
        : DateTimeOffset.FromUnixTimeSeconds((long)Created).LocalDateTime.ToString("dd.MM.yyyy");

    /// <summary>
    /// Первая буква названия — для квадратика в списке.
    ///
    /// Значка у проекта нет и взяться ему неоткуда, а ряд одинаковых строк
    /// читается хуже, чем ряд с опознавательными знаками.
    /// </summary>
    public string Initial => Name.Length > 0 ? Name.Substring(0, 1).ToUpperInvariant() : "?";
}

/// <summary>Ответ backend со списком проектов.</summary>
public class ProjectsResponse
{
    [JsonPropertyName("projects")]
    public System.Collections.Generic.List<Project> Projects { get; set; } = new();
}
