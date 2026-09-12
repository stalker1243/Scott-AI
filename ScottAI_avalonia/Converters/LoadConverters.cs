using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Avalonia.Media;

namespace ScottAI.Avalonia.Converters;

/// <summary>
/// Нагрузка в цвет: от спокойного бирюзового через янтарный к тревожному
/// красному.
///
/// Цвет здесь несёт смысл, а не украшает. На голограмме четыре части, и человек
/// должен одним взглядом понять, какая из них загружена, не читая цифр. Поэтому
/// переход плавный: резкие ступени превращали бы шкалу в три состояния вместо
/// непрерывной величины, и разница между 51% и 74% пропадала бы.
/// </summary>
public class LoadToBrushConverter : IValueConverter
{
    public static readonly LoadToBrushConverter Instance = new();

    /// <summary>Спокойно: работа идёт, запас есть.</summary>
    public static readonly Color Calm = Color.FromRgb(0x22, 0xD3, 0xEE);

    /// <summary>Заметная нагрузка: пора обратить внимание.</summary>
    public static readonly Color Busy = Color.FromRgb(0xF5, 0x9E, 0x0B);

    /// <summary>На пределе.</summary>
    public static readonly Color Hot = Color.FromRgb(0xEF, 0x44, 0x44);

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => new SolidColorBrush(ColorFor(AsPercent(value)));

    /// <summary>Цвет для нагрузки в процентах.</summary>
    public static Color ColorFor(double percent)
    {
        percent = Math.Clamp(percent, 0, 100);

        // Половина шкалы уходит на спокойную часть: до пятидесяти процентов
        // машина работает вольготно, и пугать там нечем.
        if (percent <= 50)
        {
            return Blend(Calm, Busy, percent / 50.0 * 0.35);
        }

        if (percent <= 80)
        {
            return Blend(Calm, Busy, 0.35 + (percent - 50) / 30.0 * 0.65);
        }

        return Blend(Busy, Hot, (percent - 80) / 20.0);
    }

    private static Color Blend(Color from, Color to, double t)
    {
        t = Math.Clamp(t, 0, 1);
        return Color.FromRgb(
            (byte)(from.R + (to.R - from.R) * t),
            (byte)(from.G + (to.G - from.G) * t),
            (byte)(from.B + (to.B - from.B) * t));
    }

    internal static double AsPercent(object? value)
        => value switch
        {
            double d => d,
            int i => i,
            float f => f,
            _ => 0,
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Нагрузка в высоту заполнения: часть тела наливается снизу вверх.
///
/// Параметр задаёт полную высоту части. Пустая часть всё равно оставляет
/// тонкую полоску: совсем исчезнув, она не отличалась бы от «данных нет».
/// </summary>
public class LoadToHeightConverter : IValueConverter
{
    public static readonly LoadToHeightConverter Instance = new();

    /// <summary>Минимальная видимая полоска в пикселях.</summary>
    public const double MinVisible = 3;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var percent = Math.Clamp(LoadToBrushConverter.AsPercent(value), 0, 100);
        var full = parameter is string s
            && double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : 100;

        return Math.Max(MinVisible, full * percent / 100.0);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Нагрузка в яркость свечения.
///
/// Простаивающая часть светится вполсилы, загруженная — в полную. Так
/// голограмма «дышит» вместе с машиной: по ней видно, что происходит, даже
/// боковым зрением.
/// </summary>
public class LoadToGlowConverter : IValueConverter
{
    public static readonly LoadToGlowConverter Instance = new();

    /// <summary>Яркость простаивающей части. Ноль означал бы «части нет».</summary>
    public const double Idle = 0.35;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var percent = Math.Clamp(LoadToBrushConverter.AsPercent(value), 0, 100);
        return Idle + (1.0 - Idle) * (percent / 100.0);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Нагрузка в положение границы заливки внутри градиента.
///
/// Заливать часть тела оказалось надёжнее всего градиентом по самому силуэту, а
/// не отдельным прямоугольником с обрезкой. Прямоугольник нужно было к чему-то
/// прижимать, обрезка ездила вместе с его высотой, и на живой проверке части
/// наливались сверху вниз вместо низа вверх — дважды, разными способами.
///
/// У градиента ноль наверху, единица внизу, поэтому граница считается наоборот:
/// чем больше нагрузка, тем выше она поднимается.
/// </summary>
public class LoadToFillEdgeConverter : IValueConverter
{
    public static readonly LoadToFillEdgeConverter Instance = new();

    /// <summary>
    /// Сдвиг границы для верхнего края свечения. Без него граница выглядит
    /// обрезанной ножницами, а не поверхностью налитой жидкости.
    /// </summary>
    public const double Feather = 0.05;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var percent = Math.Clamp(LoadToBrushConverter.AsPercent(value), 0, 100);
        var edge = 1.0 - percent / 100.0;

        // Параметр «feather» сдвигает вторую точку градиента вверх, создавая
        // мягкую кромку.
        if (parameter is string s && s.Equals("feather", StringComparison.OrdinalIgnoreCase))
        {
            edge -= Feather;
        }

        return Math.Clamp(edge, 0, 1);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Нагрузка в цвет — тот же переход, что у кисти, но цветом.
///
/// Точке градиента нужен именно Color: кисть внутрь кисти не вложить.
/// </summary>
public class LoadToColorConverter : IValueConverter
{
    public static readonly LoadToColorConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => LoadToBrushConverter.ColorFor(LoadToBrushConverter.AsPercent(value));

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
