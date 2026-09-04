using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

public class CustomCommand
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("trigger")]
    public string Trigger { get; set; } = "";

    [JsonPropertyName("action")]
    public string Action { get; set; } = "";

    [JsonPropertyName("description")]
    public string Description { get; set; } = "";

    [JsonPropertyName("usage_count")]
    public int UsageCount { get; set; }

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; } = true;
}
