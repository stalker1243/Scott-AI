using System;
using System.Collections.Generic;

namespace ScottAI.Avalonia.Models;

public class ChatMessage
{
    public required string Text { get; init; }
    public required bool FromUser { get; init; }
    public string Time { get; init; } = DateTime.Now.ToString("HH:mm");
    public string? AttachmentName { get; init; }

    // Разбор ленивый и запоминается: шаблон обращается к Segments при каждой
    // перерисовке списка, а разбирать одно и то же регулярным выражением
    // заново незачем.
    private IReadOnlyList<MessageSegment>? _segments;

    /// <summary>
    /// Сообщение, разобранное на обычный текст и блоки кода: код показывается
    /// отдельно, с кнопкой «Копировать».
    /// </summary>
    public IReadOnlyList<MessageSegment> Segments => _segments ??= MessageSegment.Parse(Text);
}
