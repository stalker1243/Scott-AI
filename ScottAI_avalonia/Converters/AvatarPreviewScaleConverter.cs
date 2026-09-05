using System;
using System.Globalization;
using Avalonia.Data.Converters;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia.Converters;

/// <summary>
/// Пересчитать сдвиг кадра из большой области подбора в маленький аватар.
///
/// Кадр человек подбирает на превью в 220 пикселей, а показывается аватар
/// кружком в 88. Смещение хранится в пикселях большой рамки, поэтому для
/// маленькой его нужно уменьшить в том же отношении — иначе фото в аватаре
/// уезжало бы куда сильнее, чем видно при настройке, и выбранное лицо
/// оказывалось бы за краем.
/// </summary>
public class AvatarPreviewScaleConverter : IValueConverter
{
    public static readonly AvatarPreviewScaleConverter Instance = new();

    /// <summary>Диаметр аватара в интерфейсе. Совпадает с размером Border в ProfileView.</summary>
    private const double AvatarSize = 88;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var offset = value as double? ?? 0;
        return offset * (AvatarSize / ProfileViewModel.FrameSize);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
