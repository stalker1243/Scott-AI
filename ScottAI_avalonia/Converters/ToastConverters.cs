using System;
using System.Globalization;
using Avalonia;
using Avalonia.Data.Converters;
using Material.Icons;
using ScottAI.Avalonia.Models;

namespace ScottAI.Avalonia.Converters;

public class ToastKindToIconConverter : IValueConverter
{
    public static readonly ToastKindToIconConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value switch
        {
            ToastKind.Success => MaterialIconKind.CheckCircle,
            ToastKind.Error => MaterialIconKind.AlertCircle,
            _ => MaterialIconKind.InformationOutline,
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

public class ToastKindToBrushConverter : IValueConverter
{
    public static readonly ToastKindToBrushConverter Instance = new();

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value switch
        {
            ToastKind.Success => Application.Current!.Resources["Success"],
            ToastKind.Error => Application.Current!.Resources["Danger"],
            _ => Application.Current!.Resources["Accent"],
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}
