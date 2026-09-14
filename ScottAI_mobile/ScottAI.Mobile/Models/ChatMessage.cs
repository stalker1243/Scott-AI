using System;

namespace ScottAI.Mobile.Models;

/// <summary>
/// Одна реплика в чате.
///
/// Отказ выделен отдельно от ошибки, и это не мелочь: «не буду выключать
/// компьютер издалека» — это Scott, работающий как задумано, а «компьютер не
/// отвечает» — сломанная связь. Человеку важно различать их с первого взгляда,
/// иначе он будет чинить то, что не сломано.
/// </summary>
public class ChatMessage
{
    public string Text { get; init; } = "";

    /// <summary>Сказано человеком, а не Scott.</summary>
    public bool Mine { get; init; }

    /// <summary>Scott отказался — не смог, а именно не стал.</summary>
    public bool Refused { get; init; }

    /// <summary>Связь не удалась. Команда, скорее всего, не выполнена.</summary>
    public bool Failed { get; init; }

    public DateTime At { get; init; } = DateTime.Now;

    public string TimeText => At.ToString("HH:mm");

    public bool Theirs => !Mine;
}
