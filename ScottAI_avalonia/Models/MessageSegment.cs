using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Кусок сообщения: либо обычный текст, либо блок кода.
///
/// Ответ Scott — не просто строка: когда он пишет программу, код приходит
/// обрамлённым тройными кавычками markdown. Такой кусок нужно показать
/// моноширинным шрифтом и дать кнопку «Копировать», чтобы человеку не
/// приходилось выделять его мышью.
/// </summary>
public class MessageSegment
{
    public required string Text { get; init; }
    public required bool IsCode { get; init; }

    /// <summary>Язык из рамки блока (```c) — подпись над кодом.</summary>
    public string Language { get; init; } = "";

    public bool IsText => !IsCode;

    /// <summary>Подпись над блоком: язык, если он назван, иначе просто «код».</summary>
    public string Caption => string.IsNullOrWhiteSpace(Language) ? "код" : Language;

    // Рамка markdown: ```язык, перевод строки, тело, ```. Закрывающая рамка
    // может отсутствовать — ответ мог оборваться, и терять хвост в этом
    // случае хуже, чем показать его блоком.
    private static readonly Regex Fence = new(
        @"```([^\r\n]*)\r?\n(.*?)(?:```|$)",
        RegexOptions.Singleline | RegexOptions.Compiled);

    /// <summary>Разобрать текст сообщения на обычные куски и блоки кода.</summary>
    public static IReadOnlyList<MessageSegment> Parse(string? text)
    {
        var segments = new List<MessageSegment>();
        if (string.IsNullOrEmpty(text))
        {
            return segments;
        }

        var position = 0;
        foreach (Match match in Fence.Matches(text))
        {
            if (match.Index > position)
            {
                AddText(segments, text.Substring(position, match.Index - position));
            }

            var body = match.Groups[2].Value.TrimEnd('\r', '\n');
            if (body.Length > 0)
            {
                segments.Add(new MessageSegment
                {
                    Text = body,
                    IsCode = true,
                    Language = match.Groups[1].Value.Trim(),
                });
            }

            position = match.Index + match.Length;
        }

        if (position < text.Length)
        {
            AddText(segments, text.Substring(position));
        }

        // Сообщение без единого блока кода остаётся одним куском — так
        // выглядит подавляющее большинство ответов.
        if (segments.Count == 0)
        {
            segments.Add(new MessageSegment { Text = text, IsCode = false });
        }

        return segments;
    }

    private static void AddText(List<MessageSegment> segments, string chunk)
    {
        var trimmed = chunk.Trim('\r', '\n');
        if (trimmed.Length == 0)
        {
            return;
        }

        segments.Add(new MessageSegment { Text = trimmed, IsCode = false });
    }
}
