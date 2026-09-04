using System;
using System.Globalization;
using Avalonia.Data.Converters;

namespace ScottAI.Avalonia.Converters;

/// <summary>Доля 0..1 -> пиксели, ConverterParameter задаёт максимальную высоту/ширину столбика.</summary>
public class FractionToPixelsConverter : IValueConverter
{
    public static readonly FractionToPixelsConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var fraction = value is double d ? d : 0;
        var max = parameter is string s && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out var m) ? m : 100;
        return System.Math.Max(2, fraction * max);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
