using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Avalonia.Media;

namespace ScottAI.Avalonia.Converters;

/// <summary>Строка "#RRGGBB" -> SolidColorBrush. Binding напрямую в Color/Brush через
/// компилированные биндинги молча не срабатывает (нет неявной конвертации строка->Color),
/// поэтому нужен явный конвертер.</summary>
public class HexToBrushConverter : IValueConverter
{
    public static readonly HexToBrushConverter Instance = new();

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is string hex && Color.TryParse(hex, out var color))
            return new SolidColorBrush(color);
        return Brushes.Transparent;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
