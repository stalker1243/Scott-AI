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

/// <summary>
/// QuietMode -> подпись кнопки.
///
/// Речь именно об ответах в переписке, а не о Scott вообще: общее молчание —
/// отдельная настройка, и раньше обе назывались «тихим режимом», хотя значат
/// разное.
/// </summary>
public class ChatVoiceLabelConverter : IValueConverter
{
    public static readonly ChatVoiceLabelConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? "Ответы молча" : "Ответы вслух";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
