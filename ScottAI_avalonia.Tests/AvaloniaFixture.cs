using Avalonia;
using Avalonia.Headless;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Avalonia, поднятая без окна.
///
/// Нужна ради загрузчика ресурсов: он регистрируется только запущенным
/// приложением, и без него не проверить даже то, что иконки лежат по своим
/// адресам. А на этом однажды не запустился весь выпуск — версия 1.0.5 падала
/// до появления окна, молча.
///
/// Поднимается голое Application, а не App лаунчера: тому нужны значок в трее и
/// прочее окружение рабочего стола, которого на сервере проверок нет.
/// </summary>
public sealed class AvaloniaFixture
{
    // Поднимается ровно один раз на процесс.
    //
    // xUnit обещает создать фикстуру коллекции однажды, и обычно так и есть.
    // Но повторный вызов Setup роняет Avalonia, а вместе с ней — все проверки,
    // которым нужен загрузчик ресурсов: двадцать пять разом, без внятного
    // объяснения. Такое уже случалось дважды — один раз здесь, один на
    // macOS-раннере, — и оба раза со следующего прогона проходило само, то
    // есть выглядело случайностью, каковой не было.
    //
    // Дешевле сделать подъём идемпотентным, чем каждый раз разбираться, отчего
    // именно в этот прогон он случился дважды.
    private static readonly object Замок = new();
    private static bool Поднята;

    public AvaloniaFixture()
    {
        lock (Замок)
        {
            if (Поднята)
            {
                return;
            }

            AppBuilder.Configure<Application>()
                .UseHeadless(new AvaloniaHeadlessPlatformOptions())
                .SetupWithoutStarting();

            Поднята = true;
        }
    }
}

[CollectionDefinition("avalonia")]
public sealed class AvaloniaCollection : ICollectionFixture<AvaloniaFixture>
{
    // Avalonia поднимается один раз на весь прогон: второй вызов Setup падает.
}
