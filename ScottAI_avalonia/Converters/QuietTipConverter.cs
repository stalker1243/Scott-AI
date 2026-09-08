using System;
using System.Globalization;
using Avalonia.Data.Converters;

namespace ScottAI.Avalonia.Converters;

/// <summary>
/// Подсказка у кнопки молчания.
///
/// Пишем действие, а не состояние: «Дать голос» понятнее, чем «Тихий режим
/// включён», — человек наводит курсор, чтобы узнать, что случится при нажатии.
/// </summary>
public class QuietTipConverter : IValueConverter
{
    public static readonly QuietTipConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? "Scott молчит — вернуть голос" : "Попросить Scott помолчать";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
