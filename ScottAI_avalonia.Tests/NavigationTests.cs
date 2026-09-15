using System;
using System.Collections.Generic;
using System.Linq;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Список разделов слева.
///
/// Раньше каждый из шестнадцати был расписан в разметке отдельно, по шесть
/// строк XAML. Теперь они заданы данными — и главный риск такого переноса в
/// том, что раздел мог тихо пропасть: страница осталась в программе, а попасть
/// на неё стало неоткуда. Разметку тесты не читают, поэтому потерю заметил бы
/// только человек, который однажды не нашёл нужный раздел.
///
/// Отсюда и проверки: все страницы на месте, у каждой рабочий путь, открытый
/// раздел отмечен и виден даже в свёрнутой группе.
/// </summary>
// Та же коллекция, что у проверок оформления: они тоже правят общие настройки
// лаунчера, а xUnit по умолчанию гоняет разные классы параллельно. Из-за этого
// одна проверка сжимала список, пока другая сворачивала группу, — и падала то
// одна, то другая, через прогон.
[Collection("avalonia")]
public class NavigationTests : IDisposable
{
    private readonly bool _былоСжато;
    private readonly string[] _былиСвёрнуты;

    /// <summary>
    /// Состояние списка хранится в настройках лаунчера — тех же, что у живого
    /// человека. Проверки его меняют, поэтому запоминаем и возвращаем.
    ///
    /// Без этого тесты портят состояние друг другу: один сжимает список, и у
    /// следующего сворачивание групп молча перестаёт работать — в сжатом виде
    /// оно и не должно. Именно так два теста здесь и упали в первый раз.
    /// Заодно это перестаёт портить настройки того, кто запускает проверки на
    /// своей машине.
    /// </summary>
    public NavigationTests()
    {
        _былоСжато = SettingsStore.Current.SidebarCollapsed;
        _былиСвёрнуты = SettingsStore.Current.CollapsedGroups ?? Array.Empty<string>();

        SettingsStore.Current.SidebarCollapsed = false;
        SettingsStore.Current.CollapsedGroups = Array.Empty<string>();
    }

    public void Dispose()
    {
        SettingsStore.Current.SidebarCollapsed = _былоСжато;
        SettingsStore.Current.CollapsedGroups = _былиСвёрнуты;
        SettingsStore.SaveCurrent();
    }

    /// <summary>Все страницы, до которых человек должен добираться из списка.</summary>
    private static readonly string[] ВсеСтраницы =
    {
        "home", "chat", "memory", "profile", "projects", "protocols", "actions",
        "system", "aimodel", "remote", "appearance", "settings",
        "diagnostics", "logs", "analytics", "about",
    };

    private static IEnumerable<NavItem> Разделы(MainWindowViewModel окно) =>
        окно.Sections.SelectMany(г => г.Items);

    [Fact]
    public void Ни_один_раздел_не_потерялся()
    {
        var окно = new MainWindowViewModel();

        var страницы = Разделы(окно).Select(р => р.Page).ToArray();

        Assert.Equal(ВсеСтраницы.Length, страницы.Length);
        foreach (var страница in ВсеСтраницы)
        {
            Assert.Contains(страница, страницы);
        }
    }

    [Fact]
    public void У_каждого_раздела_есть_подпись_и_значок()
    {
        var окно = new MainWindowViewModel();

        foreach (var раздел in Разделы(окно))
        {
            Assert.False(string.IsNullOrWhiteSpace(раздел.Label), раздел.Page);
            Assert.NotEqual(default, раздел.Icon);
        }
    }

    [Fact]
    public void Разделы_не_повторяются()
    {
        // Раздел, попавший в две группы, отмечался бы открытым в обеих — и
        // человек не понял бы, где он находится.
        var окно = new MainWindowViewModel();

        var страницы = Разделы(окно).Select(р => р.Page).ToArray();

        Assert.Equal(страницы.Length, страницы.Distinct().Count());
    }

    [Theory]
    [InlineData("chat")]
    [InlineData("memory")]
    [InlineData("remote")]
    [InlineData("logs")]
    [InlineData("about")]
    public void Раздел_открывается_по_имени(string страница)
    {
        var окно = new MainWindowViewModel();

        окно.GoCommand.Execute(страница);

        Assert.Equal(страница, окно.ActivePage);
    }

    [Fact]
    public void Каждая_страница_из_списка_действительно_открывается()
    {
        // Опечатка в имени страницы не ломает сборку: команда просто ничего не
        // сделает, и раздел окажется нерабочим. Единственный способ это
        // заметить — пройти по всем.
        var окно = new MainWindowViewModel();

        foreach (var раздел in Разделы(окно))
        {
            окно.GoCommand.Execute(раздел.Page);

            Assert.Equal(раздел.Page, окно.ActivePage);
        }
    }

    [Fact]
    public void Открытый_раздел_отмечен_сразу_после_запуска()
    {
        // ActivePage задаётся инициализатором поля, а не через свойство, и
        // событие смены в этот момент не срабатывает: «Главная» открывалась,
        // не будучи отмеченной в списке.
        var окно = new MainWindowViewModel();

        var отмеченные = Разделы(окно).Where(р => р.Active).ToArray();

        Assert.Single(отмеченные);
        Assert.Equal("home", отмеченные[0].Page);
    }

    [Fact]
    public void Отмечен_всегда_ровно_один_раздел()
    {
        var окно = new MainWindowViewModel();

        окно.GoCommand.Execute("remote");

        var отмеченные = Разделы(окно).Where(р => р.Active).ToArray();

        Assert.Single(отмеченные);
        Assert.Equal("remote", отмеченные[0].Page);
    }

    [Fact]
    public void Свёрнутая_группа_скрывает_свои_строки()
    {
        var окно = new MainWindowViewModel();
        var группа = окно.Sections.First(г => г.Title == "Служебное");

        окно.ToggleSectionCommand.Execute(группа);

        Assert.False(группа.Expanded);
        Assert.False(группа.ItemsVisible);
    }

    [Fact]
    public void Переход_в_свёрнутую_группу_её_раскрывает()
    {
        // Иначе человек оказывается на странице, которой нет в списке, и не
        // понимает, где находится.
        var окно = new MainWindowViewModel();
        var группа = окно.Sections.First(г => г.Title == "Служебное");
        окно.ToggleSectionCommand.Execute(группа);

        окно.GoCommand.Execute("logs");

        Assert.True(группа.Expanded);
        Assert.True(группа.ItemsVisible);
    }

    [Fact]
    public void В_сжатом_списке_видны_все_значки()
    {
        // Подписей там нет и заголовок группы скрыт — сворачивать нечего.
        // Если бы видимость решалась одной свёрнутостью, часть значков
        // исчезала бы без всякой видимой причины.
        var окно = new MainWindowViewModel();
        var группа = окно.Sections.First(г => г.Title == "Служебное");
        окно.ToggleSectionCommand.Execute(группа);

        окно.ToggleSidebarCommand.Execute(null);

        Assert.True(окно.SidebarCollapsed);
        Assert.All(окно.Sections, г => Assert.True(г.ItemsVisible));
    }

    [Fact]
    public void Разворот_списка_возвращает_свёрнутость_групп()
    {
        // Сжатие списка не должно стирать выбор человека: свёрнутая группа
        // остаётся свёрнутой, когда подписи вернулись.
        var окно = new MainWindowViewModel();
        var группа = окно.Sections.First(г => г.Title == "Служебное");
        окно.ToggleSectionCommand.Execute(группа);

        окно.ToggleSidebarCommand.Execute(null);
        окно.ToggleSidebarCommand.Execute(null);

        Assert.False(окно.SidebarCollapsed);
        Assert.False(группа.ItemsVisible);
    }

    [Fact]
    public void В_сжатом_списке_группы_не_сворачиваются()
    {
        var окно = new MainWindowViewModel();
        окно.ToggleSidebarCommand.Execute(null);
        var группа = окно.Sections.First(г => г.Title == "Служебное");

        окно.ToggleSectionCommand.Execute(группа);

        Assert.True(группа.Expanded);
        Assert.True(группа.ItemsVisible);
    }
}
