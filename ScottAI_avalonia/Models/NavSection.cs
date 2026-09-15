using System.Collections.Generic;
using CommunityToolkit.Mvvm.ComponentModel;
using Material.Icons;

namespace ScottAI.Avalonia.Models;

/// <summary>
/// Один раздел в списке слева.
///
/// До этого каждый был расписан в разметке отдельно — шесть строк XAML,
/// шестнадцать раз. Добавить к ним сворачивание значило бы править все
/// шестнадцать мест и в одном непременно ошибиться.
/// </summary>
public partial class NavItem : ObservableObject
{
    public string Page { get; init; } = "";
    public string Label { get; init; } = "";
    public MaterialIconKind Icon { get; init; }

    /// <summary>
    /// Открыт ли он сейчас.
    ///
    /// Хранится в самом разделе, а не сравнивается в разметке: сравнение
    /// требует передать имя страницы в преобразователь, а параметр
    /// преобразователя не привязывается к данным — в шаблоне так не выйдет.
    /// </summary>
    [ObservableProperty] private bool _active;
}

/// <summary>
/// Группа разделов — «Scott», «Компьютер», «Служебное».
///
/// Шестнадцать строк подряд человек не читает, он их просматривает и не
/// находит нужную. Пять групп по три-четыре строки ищутся глазами, а не
/// перебором.
/// </summary>
public partial class NavSection : ObservableObject
{
    public string Title { get; init; } = "";
    public IReadOnlyList<NavItem> Items { get; init; } = new List<NavItem>();

    /// <summary>Раскрыта ли группа — это выбор человека, он запоминается.</summary>
    [ObservableProperty] private bool _expanded = true;

    /// <summary>
    /// Видны ли строки группы прямо сейчас.
    ///
    /// Не то же самое, что <see cref="Expanded"/>: в узком списке подписей
    /// нет, и заголовок группы скрыт — сворачивать там нечего и незачем.
    /// Если бы видимость решалась одним <see cref="Expanded"/>, часть иконок
    /// исчезала бы без всякой видимой причины.
    /// </summary>
    [ObservableProperty] private bool _itemsVisible = true;
}
