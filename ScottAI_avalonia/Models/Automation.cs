using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

public class IftttCondition
{
    [JsonPropertyName("trigger_type")]
    public string TriggerType { get; set; } = "";

    [JsonPropertyName("trigger_value")]
    public string TriggerValue { get; set; } = "";

    [JsonPropertyName("negate")]
    public bool Negate { get; set; }
}

public class IftttRule
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("conditions")]
    public List<IftttCondition> Conditions { get; set; } = new();

    [JsonPropertyName("logic")]
    public string Logic { get; set; } = "AND";

    [JsonPropertyName("action_type")]
    public string ActionType { get; set; } = "";

    [JsonPropertyName("action_value")]
    public string ActionValue { get; set; } = "";

    [JsonPropertyName("description")]
    public string Description { get; set; } = "";

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; } = true;

    [JsonPropertyName("execution_count")]
    public int ExecutionCount { get; set; }

    public string Summary =>
        (Conditions.Count > 0
            ? $"«{Conditions[0].TriggerValue}» → "
            : "") + $"{ActionType}: {ActionValue}";
}

public class MacroAction
{
    [JsonPropertyName("action_type")]
    public string ActionType { get; set; } = "";

    [JsonPropertyName("target")]
    public string Target { get; set; } = "";

    [JsonPropertyName("timestamp")]
    public long Timestamp { get; set; }

    [JsonPropertyName("x")]
    public int X { get; set; }

    [JsonPropertyName("y")]
    public int Y { get; set; }
}

public class Macro
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("description")]
    public string Description { get; set; } = "";

    [JsonPropertyName("actions")]
    public List<MacroAction> Actions { get; set; } = new();

    [JsonPropertyName("execution_count")]
    public int ExecutionCount { get; set; }

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; } = true;

    [JsonPropertyName("loop_count")]
    public int LoopCount { get; set; } = 1;

    [JsonPropertyName("duration_ms")]
    public long DurationMs { get; set; }

    public string Summary => $"{Actions.Count} действ. · {DurationMs / 1000.0:0.0}с · запусков: {ExecutionCount}";
}

public class MacroRecordingStatus
{
    [JsonPropertyName("is_recording")]
    public bool IsRecording { get; set; }

    [JsonPropertyName("current_macro")]
    public string? CurrentMacro { get; set; }

    [JsonPropertyName("actions_recorded")]
    public int ActionsRecorded { get; set; }
}

public class TemplateRule
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("action_type")]
    public string ActionType { get; set; } = "";

    [JsonPropertyName("action_value")]
    public string ActionValue { get; set; } = "";

    [JsonPropertyName("conditions")]
    public List<IftttCondition> Conditions { get; set; } = new();
}

public class ScottTemplate
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("category")]
    public string Category { get; set; } = "";

    [JsonPropertyName("description")]
    public string Description { get; set; } = "";

    [JsonPropertyName("commands")]
    public List<string> Commands { get; set; } = new();

    [JsonPropertyName("rules")]
    public List<TemplateRule> Rules { get; set; } = new();

    [JsonPropertyName("icon")]
    public string Icon { get; set; } = "🎯";

    [JsonPropertyName("popularity")]
    public int Popularity { get; set; }

    public string Summary => $"команд: {Commands.Count} · правил: {Rules.Count} · применений: {Popularity}";
}
