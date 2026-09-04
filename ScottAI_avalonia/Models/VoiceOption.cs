using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Голос Scott из /voice/available. Голоса приходят из двух движков: локального
/// Silero (работает офлайн, синтезирует фразу за ~150мс) и облачного Edge TTS
/// (~1.9с и нужен интернет), поэтому в списке видно, какой именно используется.
/// </summary>
public class VoiceOption
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("label")]
    public string Label { get; set; } = "";

    [JsonPropertyName("gender")]
    public string Gender { get; set; } = "";

    [JsonPropertyName("engine")]
    public string Engine { get; set; } = "";

    [JsonPropertyName("local")]
    public bool Local { get; set; }

    /// <summary>Подпись для выпадающего списка: имя голоса плюс пометка о движке.</summary>
    public string Display => Local ? $"{Label} · офлайн" : $"{Label} · облако";
}
