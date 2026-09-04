using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

public class Analytics
{
    [JsonPropertyName("daily")]
    public DailyStats? Daily { get; set; }

    [JsonPropertyName("hourly")]
    public HourlyStats? Hourly { get; set; }

    [JsonPropertyName("command_types")]
    public CommandTypeStats? CommandTypes { get; set; }

    [JsonPropertyName("top_apps")]
    public TopAppsStats? TopApps { get; set; }

    [JsonPropertyName("response_time")]
    public ResponseTimeStats? ResponseTime { get; set; }

    [JsonPropertyName("total_commands")]
    public int TotalCommands { get; set; }
}

public class DailyStats
{
    [JsonPropertyName("dates")] public List<string> Dates { get; set; } = new();
    [JsonPropertyName("commands")] public List<int> Commands { get; set; } = new();
}

public class HourlyStats
{
    [JsonPropertyName("hours")] public List<string> Hours { get; set; } = new();
    [JsonPropertyName("commands")] public List<int> Commands { get; set; } = new();
}

public class CommandTypeStats
{
    [JsonPropertyName("types")] public List<string> Types { get; set; } = new();
    [JsonPropertyName("counts")] public List<int> Counts { get; set; } = new();
    [JsonPropertyName("percentages")] public List<double> Percentages { get; set; } = new();
}

public class TopAppsStats
{
    [JsonPropertyName("apps")] public List<string> Apps { get; set; } = new();
    [JsonPropertyName("usage_count")] public List<int> UsageCount { get; set; } = new();
}

public class ResponseTimeStats
{
    [JsonPropertyName("average")] public double Average { get; set; }
    [JsonPropertyName("min")] public double Min { get; set; }
    [JsonPropertyName("max")] public double Max { get; set; }
}

public class AnalyticsTrend
{
    [JsonPropertyName("trend")]
    public string Trend { get; set; } = "stable";

    [JsonPropertyName("trend_percentage")]
    public double TrendPercentage { get; set; }
}

public class AnalyticsRecommendation
{
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("message")] public string Message { get; set; } = "";
}
