using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Material.Icons;

namespace ScottAI.Avalonia.Converters;

/// <summary>
/// Значок звука: перечёркнутый динамик в тихом режиме, обычный — в остальное
/// время.
///
/// Состояние должно читаться с одного взгляда, без подписи: переключатель
/// говорит «включено», но включённым может казаться и то, и другое.
/// </summary>
public class QuietIconConverter : IValueConverter
{
    public static readonly QuietIconConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? MaterialIconKind.VolumeOff : MaterialIconKind.VolumeHigh;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
