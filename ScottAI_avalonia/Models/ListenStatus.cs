using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Состояние прослушивания микрофона.
///
/// Scott слушает непрерывно, но выполняет только то, что сказано после его
/// имени, — поэтому счётчики разделены: сколько фраз он вообще услышал и
/// сколько из них были обращены к нему.
/// </summary>
public class ListenStatus
{
    [JsonPropertyName("listening")]
    public bool Listening { get; set; }

    /// <summary>Есть ли в системе то, чем записывать звук.</summary>
    [JsonPropertyName("available")]
    public bool Available { get; set; }

    /// <summary>
    /// Уровень фонового шума.
    ///
    /// Первое, на что смотрят, когда Scott не отзывается: при высоком фоне
    /// речь не преодолевает порог.
    /// </summary>
    [JsonPropertyName("noise_floor")]
    public double NoiseFloor { get; set; }

    [JsonPropertyName("phrases_heard")]
    public int PhrasesHeard { get; set; }

    [JsonPropertyName("triggered")]
    public int Triggered { get; set; }

    [JsonPropertyName("ignored")]
    public int Ignored { get; set; }

    [JsonPropertyName("last_text")]
    public string LastText { get; set; } = "";

    [JsonPropertyName("message")]
    public string? Message { get; set; }
}
