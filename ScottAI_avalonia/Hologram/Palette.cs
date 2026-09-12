using System;
using Avalonia.Media;
using ScottAI.Avalonia.Converters;

namespace ScottAI.Avalonia.Hologram;

/// <summary>
/// Цвета костюма и то, как в них проступает нагрузка.
///
/// Сначала вся фигура красилась цветом метрики: голова — цветом видеокарты,
/// кираса — цветом памяти, и так далее. Читалось это как схема, а не как
/// костюм — сплошные бирюзовые и янтарные пятна, между которыми нет ничего
/// общего.
///
/// Теперь у доспеха свой цвет: вороненая сталь и тёмная ткань. Нагрузка
/// проступает сквозь него — чем выше, тем сильнее металл отливает тревожным
/// оттенком и ярче светятся кромки пластин. Так фигура остаётся фигурой, но
/// по ней по-прежнему видно состояние машины: спокойная — холодная сталь,
/// загруженная — раскалённый металл.
/// </summary>
public static class Palette
{
    /// <summary>Вороненая сталь: основной металл доспеха.</summary>
    public static readonly Color Steel = Color.FromRgb(0x8A, 0x9B, 0xA8);

    /// <summary>Тёмный металл: наручи, пояс, набедренники.</summary>
    public static readonly Color DarkSteel = Color.FromRgb(0x5E, 0x6E, 0x7A);

    /// <summary>Сама маска — светлее корпуса, чтобы лицо читалось первым.</summary>
    public static readonly Color Mask = Color.FromRgb(0xB4, 0xC2, 0xCC);

    /// <summary>Ткань плаща и капюшона: глубокая зелень.</summary>
    public static readonly Color Cloth = Color.FromRgb(0x2C, 0x5A, 0x43);

    /// <summary>
    /// Насколько сильно нагрузка перекрашивает металл.
    ///
    /// Даже на полной загрузке металл остаётся металлом: полный переход в
    /// красный вернул бы ту самую схему, от которой уходили. Простаивающая
    /// часть подкрашена совсем чуть-чуть — иначе фигура выглядела бы
    /// одинаково при любой нагрузке.
    /// </summary>
    public const double IdleTint = 0.12;
    public const double BusyTint = 0.62;

    /// <summary>Цвет пластины: металл, подкрашенный нагрузкой.</summary>
    public static Color PlateFor(BodyPart part, double load)
    {
        var baseColor = BaseFor(part);

        // Плащ и отделка нагрузку не показывают: у них своя задача, и спорить
        // с показаниями приборов за внимание им незачем.
        if (part is BodyPart.Cape or BodyPart.Trim)
        {
            return baseColor;
        }

        // Ядро подкрашивается почти целиком: это единственная деталь, по
        // которой состояние процессора видно цветом, а не свечением кромок.
        var idle = part == BodyPart.Core ? 0.75 : IdleTint;
        var busy = part == BodyPart.Core ? 0.95 : BusyTint;

        var strength = idle + (busy - idle) * Math.Clamp(load, 0, 100) / 100.0;
        return Blend(baseColor, LoadToBrushConverter.ColorFor(load), strength);
    }

    /// <summary>
    /// Цвет кромки пластины.
    ///
    /// Кромки светятся цветом нагрузки заметно сильнее, чем сама пластина:
    /// именно по ним состояние и читается с одного взгляда, а металл остаётся
    /// металлом.
    /// </summary>
    public static Color EdgeFor(BodyPart part, double load)
    {
        if (part is BodyPart.Cape)
        {
            return Blend(Cloth, Color.FromRgb(0x9A, 0xE6, 0xC4), 0.35);
        }

        if (part is BodyPart.Trim)
        {
            return Blend(DarkSteel, Color.FromRgb(0xE2, 0xE8, 0xF0), 0.4);
        }

        return Blend(LoadToBrushConverter.ColorFor(load), Colors.White, 0.25);
    }

    private static Color BaseFor(BodyPart part) => part switch
    {
        BodyPart.Head => Mask,
        // Ядро светится цветом своей подсистемы — ниже его подкрасят
        // нагрузкой ещё раз, и оно выйдет ярче остальных пластин. Здесь стоял
        // цвет полной загрузки: ядро горело тревожным красным на спокойной
        // машине, и по нему нельзя было ничего понять.
        BodyPart.Core => Color.FromRgb(0xE8, 0xF4, 0xFF),
        BodyPart.Cape => Cloth,
        BodyPart.Trim => DarkSteel,
        BodyPart.Arms => DarkSteel,
        _ => Steel,
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
