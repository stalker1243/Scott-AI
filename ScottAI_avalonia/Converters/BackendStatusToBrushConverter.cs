using System;
using System.Globalization;
using Avalonia;
using Avalonia.Data.Converters;

namespace ScottAI.Avalonia.Converters;

/// <summary>BackendStatus ("starting"/"online"/"offline") -> цвет индикатора. Раньше точка статуса
/// была жёстко зелёной независимо от реального состояния — теперь честно отражает офлайн/старт.</summary>
public class BackendStatusToBrushConverter : IValueConverter
{
    public static readonly BackendStatusToBrushConverter Instance = new();

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => (value as string) switch
        {
            "online" => Application.Current!.Resources["Success"],
            "offline" => Application.Current!.Resources["Danger"],
            _ => Application.Current!.Resources["TextMuted"],
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
