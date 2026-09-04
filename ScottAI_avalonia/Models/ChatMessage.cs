using System;

namespace ScottAI.Avalonia.Models;

public class ChatMessage
{
    public required string Text { get; init; }
    public required bool FromUser { get; init; }
    public string Time { get; init; } = DateTime.Now.ToString("HH:mm");
    public string? AttachmentName { get; init; }
}
