using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Themes.Fluent;
using Avalonia.Markup.Xaml.Styling;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Рука над тем, на что можно нажать.
///
/// Windows оставляет над кнопкой обычную стрелку. В обычной программе это
/// терпимо — кнопка выделена рамкой, — но боковые вкладки лаунчера сделаны
/// кнопками без рамок, и над ними курсор ничем не отличался от курсора над
/// пустым местом рядом. Проверить это можно только наведением, а наведение в
/// проверках не воспроизводится, поэтому спрашиваем у самих контролов.
///
/// Проверяется не наличие строк в разметке, а то, каким курсор окажется у
/// контрола в живом дереве: стиль может существовать и не применяться —
/// например, если тема перебьёт его своим значением.
/// </summary>
[Collection("avalonia")]
public class CursorTests
{
    /// <summary>
    /// Окно с теми же стилями курсора, что и у программы.
    ///
    /// Стили берутся из того же файла, который подключает App: копия здесь
    /// означала бы, что проверка подтверждает сама себя.
    /// </summary>
    private static Window Окно(Control содержимое)
    {
        var окно = new Window
        {
            Styles =
            {
                // Тема нужна не только ради вида: у ToggleSwitch без неё нет
                // шаблона, а ещё тема — единственное, что могло бы перебить
                // наши курсоры своими. Пусть проверка это учитывает.
                new FluentTheme(),

                new StyleInclude(new System.Uri("avares://ScottAI/"))
                {
                    Source = new System.Uri("avares://ScottAI/Styles/Cursors.axaml"),
                },
            },
            Content = содержимое,
        };

        окно.Show();
        return окно;
    }

    [Fact]
    public void Над_кнопкой_рука()
    {
        var кнопка = new Button { Content = "Отправить" };
        Окно(кнопка);

        Assert.Equal(StandardCursorType.Hand, ТипКурсора(кнопка));
    }

    [Fact]
    public void Над_выключенной_кнопкой_обычная_стрелка()
    {
        // Рука обещает нажатие, которого не произойдёт. Пока Scott думает,
        // кнопка «Отправить» выключена — там это сбивало бы с толку сильнее
        // всего.
        var кнопка = new Button { Content = "Отправить", IsEnabled = false };
        Окно(кнопка);

        Assert.Equal(StandardCursorType.Arrow, ТипКурсора(кнопка));
    }

    [Fact]
    public void Над_переключателем_и_флажком_рука()
    {
        var переключатель = new ToggleSwitch();
        var флажок = new CheckBox();
        var список = new ComboBox();

        Окно(new StackPanel { Children = { переключатель, флажок, список } });

        Assert.Equal(StandardCursorType.Hand, ТипКурсора(переключатель));
        Assert.Equal(StandardCursorType.Hand, ТипКурсора(флажок));
        Assert.Equal(StandardCursorType.Hand, ТипКурсора(список));
    }

    [Fact]
    public void Поле_ввода_остаётся_с_текстовым_курсором()
    {
        // Рука в поле ввода означала бы, что по нему нажимают, а не печатают.
        var поле = new TextBox();
        Окно(поле);

        Assert.NotEqual(StandardCursorType.Hand, ТипКурсора(поле));
    }

    private static StandardCursorType ТипКурсора(Control контрол)
    {
        var курсор = контрол.Cursor;
        if (курсор is null) return StandardCursorType.Arrow;

        // У Cursor нет открытого свойства с типом, но ToString возвращает его
        // имя — а сравнивать с заранее созданным курсором нельзя: Avalonia
        // отдаёт для одного типа разные объекты.
        return System.Enum.TryParse<StandardCursorType>(курсор.ToString(), out var тип)
            ? тип
            : StandardCursorType.Arrow;
    }
}
