using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Одна запись памяти: то, что человек велел Scott запомнить.
/// </summary>
public class MemoryItem
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("text")]
    public string Text { get; set; } = "";

    /// <summary>"fact" | "preference" | "task" | "note".</summary>
    [JsonPropertyName("kind")]
    public string Kind { get; set; } = "fact";

    /// <summary>Когда запомнено — секунды, как их отдаёт backend.</summary>
    [JsonPropertyName("created")]
    public double Created { get; set; }

    /// <summary>
    /// Дата словами.
    ///
    /// Показывается рядом с записью: память накапливается, и через полгода
    /// «мой проект на C#» может относиться к другому проекту.
    /// </summary>
    public string CreatedText => Created <= 0
        ? ""
        : DateTimeOffset.FromUnixTimeSeconds((long)Created).LocalDateTime.ToString("dd.MM.yyyy");
}

/// <summary>Название категории — приходит с backend, чтобы не дублировать список.</summary>
public class MemoryKind : CommunityToolkit.Mvvm.ComponentModel.ObservableObject
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    private bool _isActive;

    /// <summary>
    /// Показана ли сейчас эта категория.
    ///
    /// Признак живёт здесь, а не вычисляется в разметке: сравнить с выбранной
    /// категорией прямо в привязке нечем — у элемента списка нет доступа к
    /// состоянию страницы.
    /// </summary>
    [JsonIgnore]
    public bool IsActive
    {
        get => _isActive;
        set => SetProperty(ref _isActive, value);
    }
}

public class MemoryList
{
    [JsonPropertyName("memories")]
    public List<MemoryItem> Memories { get; set; } = new();

    [JsonPropertyName("kinds")]
    public List<MemoryKind> Kinds { get; set; } = new();
}
