using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Avalonia.Layout;
using Avalonia.Media;

namespace ScottAI.Avalonia.Converters;

/// <summary>FromUser (bool) -> цвет фона пузыря сообщения (акцент для пользователя, поверхность для Scott).</summary>
public class FromUserToBrushConverter : IValueConverter
{
    public static readonly FromUserToBrushConverter Instance = new();

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var key = value is true ? "Accent" : "BgSurface";
        var resources = global::Avalonia.Application.Current?.Resources;
        return resources is not null && resources.TryGetResource(key, null, out var brush) ? brush : null;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>FromUser (bool) -> выравнивание пузыря по правому/левому краю чата.</summary>
public class FromUserToAlignmentConverter : IValueConverter
{
    public static readonly FromUserToAlignmentConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? HorizontalAlignment.Right : HorizontalAlignment.Left;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
