using System.Collections.Generic;
using System.Text.Json.Serialization;
using CommunityToolkit.Mvvm.ComponentModel;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Характер звучания: обработка, которой пропускается синтезированная речь.
///
/// Голосов у локальной модели пять, и все обычные человеческие — сделать
/// звучание узнаваемым сменой голоса нельзя. Зато можно обработать готовый
/// звук, и разница слышна сразу.
/// </summary>
public partial class VoiceCharacter : ObservableObject
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    /// <summary>Название вместе с пояснением: «Чёткий — ровный и разборчивый».</summary>
    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    /// <summary>Само название, до тире, — для заголовка строки.</summary>
    public string Name => Title.Split('—')[0].Trim();

    /// <summary>
    /// Выбран ли сейчас.
    ///
    /// Хранится в самом характере, а не сравнивается в разметке: сравнение
    /// требует передать значение в преобразователь, а его параметр не
    /// привязывается к данным — в шаблоне так не выйдет.
    /// </summary>
    [ObservableProperty] private bool _selected;

    /// <summary>Пояснение после тире — мелким шрифтом под названием.</summary>
    public string Hint
    {
        get
        {
            var части = Title.Split('—');
            return части.Length > 1 ? части[1].Trim() : "";
        }
    }
}

public class VoiceCharactersResponse
{
    [JsonPropertyName("characters")]
    public List<VoiceCharacter> Characters { get; set; } = new();

    [JsonPropertyName("current")]
    public string Current { get; set; } = "natural";
}
