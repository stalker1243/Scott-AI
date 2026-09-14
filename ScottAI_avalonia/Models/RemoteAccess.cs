using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Models;

/// <summary>Состояние моста в Telegram.</summary>
public class RemoteBridge
{
    [JsonPropertyName("configured")]
    public bool Configured { get; set; }

    [JsonPropertyName("running")]
    public bool Running { get; set; }

    /// <summary>Имя бота — по нему человек найдёт его в Telegram.</summary>
    [JsonPropertyName("username")]
    public string Username { get; set; } = "";

    [JsonPropertyName("error")]
    public string Error { get; set; } = "";
}

/// <summary>
/// Привязанное устройство — то, что может командовать Scott издалека.
///
/// Ключа здесь нет намеренно: его показывают один раз, тому, кто
/// привязывается. В списке он был бы лишней копией секрета.
/// </summary>
public class RemoteDevice
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    /// <summary>"telegram" | "app".</summary>
    [JsonPropertyName("channel")]
    public string Channel { get; set; } = "";

    [JsonPropertyName("paired")]
    public double Paired { get; set; }

    [JsonPropertyName("last_seen")]
    public double LastSeen { get; set; }

    public string PairedText => Paired <= 0
        ? ""
        : DateTimeOffset.FromUnixTimeSeconds((long)Paired).LocalDateTime.ToString("dd.MM.yyyy");

    public string LastSeenText => LastSeen <= 0
        ? "ещё не командовало"
        : DateTimeOffset.FromUnixTimeSeconds((long)LastSeen).LocalDateTime.ToString("dd.MM HH:mm");

    public string ChannelText => Channel switch
    {
        "telegram" => "Telegram",
        "app" => "Приложение",
        _ => Channel,
    };
}

/// <summary>Одна запись журнала: что выполнено издалека.</summary>
public class RemoteLogEntry
{
    [JsonPropertyName("at")]
    public double At { get; set; }

    [JsonPropertyName("device")]
    public string Device { get; set; } = "";

    [JsonPropertyName("text")]
    public string Text { get; set; } = "";

    [JsonPropertyName("outcome")]
    public string Outcome { get; set; } = "";

    public string AtText => At <= 0
        ? ""
        : DateTimeOffset.FromUnixTimeSeconds((long)At).LocalDateTime.ToString("dd.MM HH:mm");

    /// <summary>Отказ виден отдельно: именно о нём стоит узнать.</summary>
    public bool Refused => Outcome.StartsWith("отказано", StringComparison.OrdinalIgnoreCase);
}

public class RemoteStatus
{
    [JsonPropertyName("bridge")]
    public RemoteBridge Bridge { get; set; } = new();

    [JsonPropertyName("devices")]
    public List<RemoteDevice> Devices { get; set; } = new();

    [JsonPropertyName("pairing")]
    public bool Pairing { get; set; }

    /// <summary>Что вообще позволено издалека — показывается человеку списком.</summary>
    [JsonPropertyName("allowed")]
    public Dictionary<string, string> Allowed { get; set; } = new();
}
