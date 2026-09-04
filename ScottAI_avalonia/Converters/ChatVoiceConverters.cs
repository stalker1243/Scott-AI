using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Material.Icons;

namespace ScottAI.Avalonia.Converters;

/// <summary>QuietMode -> иконка колонки (перечёркнутая, когда тихий режим включён).</summary>
public class ChatVoiceIconConverter : IValueConverter
{
    public static readonly ChatVoiceIconConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? MaterialIconKind.VolumeOff : MaterialIconKind.VolumeHigh;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>QuietMode -> подпись кнопки.</summary>
public class ChatVoiceLabelConverter : IValueConverter
{
    public static readonly ChatVoiceLabelConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? "Тихий режим" : "Озвучка: вкл";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
