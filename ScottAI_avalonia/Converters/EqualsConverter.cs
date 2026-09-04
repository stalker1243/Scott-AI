using System;
using System.Globalization;
using Avalonia.Data.Converters;

namespace ScottAI.Avalonia.Converters;

/// <summary>Сравнивает значение с ConverterParameter (строкой) — используется для подсветки активного пункта навигации.</summary>
public class EqualsConverter : IValueConverter
{
    public static readonly EqualsConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value?.ToString() == parameter?.ToString();

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
