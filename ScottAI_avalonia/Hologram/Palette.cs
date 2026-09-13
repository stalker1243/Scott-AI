using System;
using Avalonia.Media;
using ScottAI.Avalonia.Converters;

namespace ScottAI.Avalonia.Hologram;

/// <summary>
/// Цвета фигуры и то, как в них проступает нагрузка.
///
/// Голограмма нужна, чтобы с одного взгляда видеть состояние машины, и цвет —
/// главное, что у неё для этого есть. Когда фигура была в доспехах, цвет
/// нагрузки приходилось приглушать, иначе металл переставал быть металлом:
/// показания читались хуже ради внешности. Без доспеха этот размен исчез.
///
/// Основной тон холодный и почти белый — по нему заметен любой оттенок
/// нагрузки. Тёплое на фигуре означает ровно одно: часть машины загружена.
/// </summary>
public static class Palette
{
    /// <summary>Тело голограммы на спокойной машине.</summary>
    public static readonly Color Body = Color.FromRgb(0x8F, 0xC9, 0xDC);

    /// <summary>Свечение в груди — общая загрузка.</summary>
    public static readonly Color Light = Color.FromRgb(0xE8, 0xF4, 0xFF);

    /// <summary>
    /// Насколько сильно нагрузка перекрашивает тело.
    ///
    /// Заметно сильнее, чем на доспехе: там подкраска боролась с металлом,
    /// здесь ей никто не мешает. Простаивающая часть всё же подкрашена — иначе
    /// фигура выглядела бы одинаково при любой нагрузке.
    /// </summary>
    public const double IdleTint = 0.3;
    public const double BusyTint = 0.88;

    /// <summary>Цвет части: тело, подкрашенное нагрузкой.</summary>
    public static Color PlateFor(Substance substance, double load)
    {
        var baseColor = substance == Substance.Glow ? Light : Body;

        var idle = substance == Substance.Glow ? 0.75 : IdleTint;
        var busy = substance == Substance.Glow ? 0.95 : BusyTint;

        var strength = idle + (busy - idle) * Math.Clamp(load, 0, 100) / 100.0;
        return Blend(baseColor, LoadToBrushConverter.ColorFor(load), strength);
    }

    /// <summary>
    /// Цвет кромки.
    ///
    /// Кромка светится цветом нагрузки сильнее самой поверхности: по ней
    /// состояние и читается с одного взгляда, а заодно она очерчивает силуэт,
    /// который у полупрозрачной фигуры иначе расплывается.
    /// </summary>
    public static Color EdgeFor(Substance substance, double load)
        => Blend(LoadToBrushConverter.ColorFor(load), Colors.White, 0.3);

    /// <summary>
    /// Насколько вещество блестит: сила блика и его резкость.
    ///
    /// Резкость подобрана под восьмигранное сечение: грани стоят через сорок
    /// пять градусов, и блик уже этого зазора не попадёт ни на одну из них.
    /// Первая попытка с резкостью 28 именно так и пропала, вторая с 14 едва
    /// дотягивала. Числа здесь не подобраны на глаз: их держит проверка,
    /// которая строит трубу и требует заметного блика хотя бы на одной грани.
    ///
    /// Светящееся не бликует: у него нет поверхности, которая отражала бы
    /// чужой свет.
    /// </summary>
    public static (double Strength, double Sharpness) Gloss(Substance substance) => substance switch
    {
        Substance.Glow => (0, 1),
        _ => (0.45, 9),
    };

    /// <summary>
    /// Насколько вещество непрозрачно.
    ///
    /// Голограмма должна просвечивать чуть-чуть, а не насквозь: сквозь ближние
    /// части угадываются дальние, но не читаются как отдельные фигуры.
    /// </summary>
    public static double Opacity(Substance substance) => substance switch
    {
        Substance.Glow => 1.0,
        _ => 0.88,
    };

    /// <summary>Смешать два цвета.</summary>
    public static Color Blend(Color from, Color to, double t)
    {
        t = Math.Clamp(t, 0, 1);
        return Color.FromRgb(
            (byte)(from.R + (to.R - from.R) * t),
            (byte)(from.G + (to.G - from.G) * t),
            (byte)(from.B + (to.B - from.B) * t));
    }

    /// <summary>Пригасить или высветлить цвет — этим задаётся объём.</summary>
    public static Color Shade(Color color, double factor)
    {
        factor = Math.Clamp(factor, 0, 2);
        return Color.FromRgb(
            (byte)Math.Clamp(color.R * factor, 0, 255),
            (byte)Math.Clamp(color.G * factor, 0, 255),
            (byte)Math.Clamp(color.B * factor, 0, 255));
    }
}
