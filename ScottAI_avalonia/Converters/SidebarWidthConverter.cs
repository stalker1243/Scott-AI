using System;
using System.Globalization;
using Avalonia.Data.Converters;

namespace ScottAI.Avalonia.Converters;

/// <summary>
/// Ширина списка разделов: полная или только под иконки.
///
/// Числа здесь, а не в разметке, потому что их два и они связаны: 64 — ровно
/// столько, чтобы иконка осталась по центру там же, где была в полном списке,
/// и строка не поехала при сжатии.
/// </summary>
public sealed class SidebarWidthConverter : IValueConverter
{
    public static readonly SidebarWidthConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        return value is true ? 64.0 : 208.0;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        throw new NotSupportedException();
    }
}
