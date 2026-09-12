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
/// Потом у доспеха появился собственный цвет, но один на всё: и кираса, и
/// плащ, и обод ядра были из одного вещества разной яркости. Теперь цвет
/// берётся из материала — стали, золота, сукна, подкладки, кожи, — а нагрузка
/// проступает сквозь него только там, где ей положено.
///
/// Правило про цвет простое и его стоит держать: тёплое на фигуре редко и
/// потому заметно. Золочёная отделка и багровая подкладка плаща — единственные
/// тёплые пятна, и именно они не дают фигуре слиться в одно голубое пятно.
/// Если раскрасить теплом ещё и доспех, пропадут оба.
/// </summary>
public static class Palette
{
    /// <summary>Вороненая сталь: основной металл доспеха.</summary>
    public static readonly Color Steel = Color.FromRgb(0x7E, 0x90, 0xA0);

    /// <summary>Тёмный металл: наручи, поножи, изнанка пластин.</summary>
    public static readonly Color DarkSteel = Color.FromRgb(0x4E, 0x5C, 0x68);

    /// <summary>Сама маска — светлее корпуса, чтобы лицо читалось первым.</summary>
    public static readonly Color Mask = Color.FromRgb(0xC3, 0xD0, 0xDA);

    /// <summary>Золочёная отделка: пояс, обод ядра, кромки наплечников.</summary>
    public static readonly Color Gold = Color.FromRgb(0xD8, 0xA9, 0x3C);

    /// <summary>Сукно плаща: глубокая зелень.</summary>
    public static readonly Color Cloth = Color.FromRgb(0x24, 0x50, 0x3C);

    /// <summary>Подкладка плаща — тёплая, видна только со спины и в повороте.</summary>
    public static readonly Color Lining = Color.FromRgb(0x7A, 0x22, 0x30);

    /// <summary>
    /// Кожа ремней и сочленений.
    ///
    /// Заметно светлее, чем кажется на память: первый выбор был почти чёрным,
    /// и кисти с набедренниками превратились в пятна без формы.
    /// </summary>
    public static readonly Color Leather = Color.FromRgb(0x6B, 0x55, 0x42);

    /// <summary>Свечение ядра и прорези для глаз.</summary>
    public static readonly Color Light = Color.FromRgb(0xE8, 0xF4, 0xFF);

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

    /// <summary>Цвет пластины: материал, подкрашенный нагрузкой.</summary>
    public static Color PlateFor(Substance substance, double load)
    {
        var baseColor = BaseFor(substance);

        if (!ShowsLoad(substance))
        {
            return baseColor;
        }

        // Ядро подкрашивается почти целиком: это единственная деталь, по
        // которой состояние процессора видно цветом, а не свечением кромок.
        var idle = substance == Substance.Glow ? 0.75 : IdleTint;
        var busy = substance == Substance.Glow ? 0.95 : BusyTint;

        var strength = idle + (busy - idle) * Math.Clamp(load, 0, 100) / 100.0;
        return Blend(baseColor, LoadToBrushConverter.ColorFor(load), strength);
    }

    /// <summary>
    /// Цвет кромки пластины.
    ///
    /// У металла кромка светится цветом нагрузки заметно сильнее, чем сама
    /// пластина: именно по ней состояние и читается с одного взгляда, а металл
    /// остаётся металлом. У материалов, которые ничего не показывают, кромка
    /// просто светлее их самих — это фаска, а не индикатор.
    /// </summary>
    public static Color EdgeFor(Substance substance, double load)
    {
        if (!ShowsLoad(substance))
        {
            return Blend(BaseFor(substance), Colors.White, substance switch
            {
                Substance.Gold => 0.42,
                Substance.Cloth => 0.26,
                Substance.Lining => 0.3,
                _ => 0.2,
            });
        }

        return Blend(LoadToBrushConverter.ColorFor(load), Colors.White, 0.25);
    }

    /// <summary>
    /// Показывает ли материал нагрузку.
    ///
    /// Отделка, ткань и кожа не показывают ничего: у них своя задача, и спорить
    /// с показаниями приборов за внимание им незачем. Заодно это и есть те
    /// самые постоянные пятна цвета, по которым фигура узнаётся при любой
    /// нагрузке.
    /// </summary>
    public static bool ShowsLoad(Substance substance) => substance
        is Substance.Plate or Substance.Mask or Substance.Glow;

    /// <summary>
    /// Насколько материал блестит.
    ///
    /// Возвращается пара: сила блика и его резкость. У полированной стали блик
    /// узкий и яркий, у золота шире и мягче, у сукна нет никакого. Эта разница
    /// и отличает металл от ткани — одной яркости для этого мало, что и было
    /// видно, пока материала не существовало.
    ///
    /// Резкость подобрана под восьмигранное сечение: грани стоят через сорок
    /// пять градусов, и блик уже этого зазора не попадёт ни на одну из них.
    /// Первая попытка с резкостью 28 именно так и пропала, вторая с 14 едва
    /// дотягивала — блик на трубе выходил силой в семь сотых, на пределе
    /// различимости. Числа здесь не подобраны на глаз: их держит проверка,
    /// которая строит трубу и требует заметного блика хотя бы на одной грани.
    /// </summary>
    public static (double Strength, double Sharpness) Gloss(Substance substance) => substance switch
    {
        Substance.Plate => (0.55, 9),
        Substance.Mask => (0.6, 12),
        Substance.Gold => (0.75, 6),
        Substance.Leather => (0.18, 4),
        Substance.Cloth => (0, 1),
        Substance.Lining => (0, 1),

        // Светящееся не бликует: у него нет поверхности, которая отражала бы
        // чужой свет.
        Substance.Glow => (0, 1),
        _ => (0.3, 20),
    };

    /// <summary>
    /// Насколько материал непрозрачен.
    ///
    /// Голограмма должна просвечивать чуть-чуть, а не насквозь: сквозь ткань
    /// угадывается фигура, сквозь доспех — почти ничего.
    /// </summary>
    public static double Opacity(Substance substance) => substance switch
    {
        // Сукно почти непрозрачно. Полупрозрачным оно выглядело марлей: со
        // спины сквозь плащ просвечивала вся фигура вместе с ногами, и
        // разобрать, где ткань, а где человек, было нельзя.
        Substance.Cloth => 0.9,
        Substance.Lining => 0.9,
        Substance.Glow => 1.0,
        _ => 0.95,
    };

    private static Color BaseFor(Substance substance) => substance switch
    {
        Substance.Mask => Mask,
        Substance.Gold => Gold,
        Substance.Cloth => Cloth,
        Substance.Lining => Lining,
        Substance.Leather => Leather,
        Substance.Glow => Light,
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
