using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

public class AiModelOption
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("note")] public string Note { get; set; } = "";
}

public class AiProvider
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("note")] public string Note { get; set; } = "";
    [JsonPropertyName("configured")] public bool Configured { get; set; }
    [JsonPropertyName("models")] public List<AiModelOption> Models { get; set; } = new();
}

public class VersionItem
{
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = "";
    [JsonPropertyName("item_type")] public string ItemType { get; set; } = "";
    [JsonPropertyName("current_version")] public int CurrentVersion { get; set; }
    [JsonPropertyName("versions_count")] public int VersionsCount { get; set; }
}

public class VersionEntry
{
    [JsonPropertyName("version_number")] public int VersionNumber { get; set; }
    [JsonPropertyName("author")] public string Author { get; set; } = "";
    [JsonPropertyName("change_description")] public string ChangeDescription { get; set; } = "";
    [JsonPropertyName("created_at")] public string CreatedAt { get; set; } = "";
}

public class VersionHistory
{
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = "";
    [JsonPropertyName("versions")] public List<VersionEntry> Versions { get; set; } = new();
    [JsonPropertyName("current_version")] public int CurrentVersion { get; set; }
}
