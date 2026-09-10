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
    public AvaloniaFixture()
    {
        AppBuilder.Configure<Application>()
            .UseHeadless(new AvaloniaHeadlessPlatformOptions())
            .SetupWithoutStarting();
    }
}

[CollectionDefinition("avalonia")]
public sealed class AvaloniaCollection : ICollectionFixture<AvaloniaFixture>
{
    // Avalonia поднимается один раз на весь прогон: второй вызов Setup падает.
}
