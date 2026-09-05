using System;
using System.Collections.Generic;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media.Imaging;
using Avalonia.Platform;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Выбор иконки приложения: тёмная или светлая.
///
/// Двух вариантов хватает потому, что различаются они фоном самой иконки:
/// тёмная со свечением хороша на тёмном интерфейсе и в тёмной панели задач,
/// светлая — на белом. Тема лаунчера и системная тема панели задач у человека
/// могут не совпадать, поэтому выбор оставлен ему, а не привязан к теме
/// автоматически.
///
/// Иконка .exe в этот выбор не входит: она вшивается в файл при сборке и
/// поменять её на лету нельзя.
/// </summary>
public static class AppIconService
{
    public const string Dark = "dark";
    public const string Light = "light";

    private static readonly Dictionary<string, (string Icon, string Logo)> Variants = new()
    {
        [Dark] = ("avares://ScottAI.Avalonia/Assets/scott.ico",
                  "avares://ScottAI.Avalonia/Assets/scott-logo.png"),
        [Light] = ("avares://ScottAI.Avalonia/Assets/scott-light.ico",
                   "avares://ScottAI.Avalonia/Assets/scott-logo-light.png"),
    };

    public static string Current { get; private set; } = Dark;

    /// <summary>Сработает после смены — сайдбар слушает, чтобы перерисовать логотип.</summary>
    public static event Action<string>? IconChanged;

    public static bool IsKnown(string? variant) => variant is not null && Variants.ContainsKey(variant);

    /// <summary>Логотип для интерфейса. Загружается заново на каждый вызов: картинка
    /// маленькая, а держать её в поле — значит рисковать обращением к освобождённой.</summary>
    public static Bitmap LoadLogo(string? variant = null)
    {
        var key = IsKnown(variant) ? variant! : Current;
        return new Bitmap(AssetLoader.Open(new Uri(Variants[key].Logo)));
    }

    public static WindowIcon LoadWindowIcon(string? variant = null)
    {
        var key = IsKnown(variant) ? variant! : Current;
        return new WindowIcon(AssetLoader.Open(new Uri(Variants[key].Icon)));
    }

    /// <summary>
    /// Применить вариант к окну, трею и логотипу в сайдбаре.
    ///
    /// Ошибки здесь намеренно проглатываются: иконка — вещь приятная, но
    /// падать из-за неё лаунчер не должен, а трей на некоторых системах может
    /// быть недоступен вовсе.
    /// </summary>
    public static void Apply(string? variant)
    {
        Current = IsKnown(variant) ? variant! : Dark;

        try
        {
            var icon = LoadWindowIcon(Current);

            if (Application.Current?.ApplicationLifetime
                is global::Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop
                && desktop.MainWindow is not null)
            {
                desktop.MainWindow.Icon = icon;
            }

            if (Application.Current is not null)
            {
                foreach (var tray in TrayIcon.GetIcons(Application.Current) ?? new TrayIcons())
                {
                    tray.Icon = icon;
                }
            }
        }
        catch (Exception)
        {
            // Не нашлось ресурса или система не даёт трей — оставляем как есть.
        }

        IconChanged?.Invoke(Current);
    }
}
