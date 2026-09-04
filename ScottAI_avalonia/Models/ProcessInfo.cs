using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

public class ProcessInfo
{
    [JsonPropertyName("pid")]
    public int Pid { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("memory_mb")]
    public double MemoryMb { get; set; }

    [JsonPropertyName("cpu_percent")]
    public double CpuPercent { get; set; }
}
