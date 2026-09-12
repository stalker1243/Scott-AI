using System;
using System.ComponentModel;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Меню значка в трее.
///
/// Фоновый режим — обычное состояние Scott: окно закрыто, а он продолжает
/// слушать комнату и отвечать голосом. До сих пор в этом состоянии с ним
/// нельзя было сделать ничего, кроме «открыть» и «выйти»: чтобы велеть ему
/// замолчать, приходилось разворачивать окно, нажимать кнопку и закрывать окно
/// обратно. Между тем именно замолчать чаще всего и нужно — когда начался
/// разговор или созвон.
///
/// Поэтому в меню есть два переключателя: тихий режим и микрофон. Оба
/// показывают текущее состояние галочкой, а не только меняют его: из трея не
/// видно ничего, и меню — единственное место, где можно узнать, слушает Scott
/// или нет.
///
/// Пункты строятся в коде, а не в разметке. Меню должно показывать состояние,
/// которое живёт в моделях представления, а до них разметка приложения не
/// дотягивается: значок в трее создаётся раньше главного окна и ничего о нём
/// не знает.
/// </summary>
public static class TrayMenuService
{
    private static NativeMenuItem? _quiet;
    private static NativeMenuItem? _listen;
    private static TrayIcon? _icon;
    private static MainWindowViewModel? _model;

    /// <summary>Подпись значка — по ней состояние видно, не открывая меню.</summary>
    public static string Tooltip(bool quiet, bool listening) => (quiet, listening) switch
    {
        (true, true) => "Scott AI — слушает, отвечает без голоса",
        (true, false) => "Scott AI — тихий режим",
        (false, true) => "Scott AI — слушает",
        _ => "Scott AI",
    };

    /// <summary>
    /// Достроить меню значка и связать его с моделью главного окна.
    ///
    /// Связь двусторонняя: галочки следуют за состоянием, которое могли
    /// поменять и из окна, а нажатие в меню зовёт ту же команду, что и кнопка
    /// в шапке. Иначе меню и окно показывали бы разное, и человек не понимал
    /// бы, чему верить, — на этом уже обжигались с тихим режимом, когда он
    /// переключался из двух мест.
    /// </summary>
    public static void Attach(TrayIcon? icon, MainWindowViewModel model)
    {
        if (icon?.Menu is null) return;

        _icon = icon;
        _model = model;

        _quiet = new NativeMenuItem("Тихий режим") { ToggleType = MenuItemToggleType.CheckBox };
        _quiet.Click += (_, _) => model.ToggleQuietCommand.Execute(null);

        _listen = new NativeMenuItem("Слушать микрофон") { ToggleType = MenuItemToggleType.CheckBox };
        _listen.Click += (_, _) => model.Home.ToggleListeningCommand.Execute(null);

        // Переключатели идут первыми: ради них меню и открывают. «Открыть» и
        // «Выход» остаются там, где были, — их ищут глазами внизу.
        icon.Menu.Items.Insert(0, _quiet);
        icon.Menu.Items.Insert(1, _listen);
        icon.Menu.Items.Insert(2, new NativeMenuItemSeparator());

        model.PropertyChanged += OnModelChanged;
        model.Home.PropertyChanged += OnHomeChanged;

        Sync();
    }

    private static void OnModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MainWindowViewModel.QuietMode)) Sync();
    }

    private static void OnHomeChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(HomeViewModel.IsListening)) Sync();
    }

    private static void Sync()
    {
        if (_model is null) return;

        if (_quiet is not null) _quiet.IsChecked = _model.QuietMode;
        if (_listen is not null) _listen.IsChecked = _model.Home.IsListening;

        if (_icon is not null)
        {
            _icon.ToolTipText = Tooltip(_model.QuietMode, _model.Home.IsListening);
        }
    }

    /// <summary>Значок приложения, если система его вообще дала.</summary>
    public static TrayIcon? IconOf(Application app)
        => TrayIcon.GetIcons(app)?.FirstOrDefault();
}
