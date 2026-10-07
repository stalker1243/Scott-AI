using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Раздел «О программе».
///
/// Главное здесь — кнопка проверки обновлений, и главное в ней — что она
/// отвечает ВСЕГДА. Карточка обновления наверху окна молчит намеренно:
/// беспокоить человека сообщением «обновлений нет» посреди работы незачем. Но
/// кнопку, на которую нажали руками, молчание превращает в сломанную — нажал и
/// не понял, случилось ли что-нибудь.
///
/// Поэтому проверяются все три исхода: обновление есть, обновления нет, и
/// спросить не удалось.
/// </summary>
[Collection("avalonia")]
public class AboutTests
{
    private const string Адрес = "http://127.0.0.1:8000";

    /// <summary>Backend, отвечающий заранее заданным телом.</summary>
    private sealed class Ответчик : HttpMessageHandler
    {
        private readonly HttpStatusCode _код;
        private readonly string _тело;

        public Ответчик(string тело, HttpStatusCode код = HttpStatusCode.OK)
        {
            _тело = тело;
            _код = код;
        }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            return Task.FromResult(new HttpResponseMessage(_код)
            {
                Content = new StringContent(_тело),
            });
        }
    }

    private static AboutViewModel Раздел(string тело, HttpStatusCode код = HttpStatusCode.OK)
    {
        var служба = new UpdateService(new HttpClient(new Ответчик(тело, код)));
        return new AboutViewModel(Адрес, служба);
    }

    private static string Ответ(bool доступно, string текущая = "1.2.0",
                                string последняя = "1.2.0", string ошибка = "")
    {
        // Обычная строка, а не «сырая»: закрывающие фигурные скобки JSON
        // ссорятся с разметкой подстановок, и сообщение компилятора об этом
        // разбирать дольше, чем написать так.
        return "{\"data\": {"
             + "\"update_available\": " + (доступно ? "true" : "false") + ","
             + "\"current_version\": \"" + текущая + "\","
             + "\"latest_version\": \"" + последняя + "\","
             + "\"release_notes\": \"\","
             + "\"download_url\": \"\","
             + "\"asset_name\": \"\","
             + "\"asset_size\": 0,"
             + "\"release_url\": \"https://example.com/release\","
             + "\"published_at\": \"\","
             + "\"error\": \"" + ошибка + "\""
             + "}}";
    }

    // ==================== Ответ на нажатие ====================

    [Fact]
    public async Task Когда_обновлений_нет_об_этом_говорят()
    {
        var раздел = Раздел(Ответ(доступно: false));

        await раздел.CheckUpdatesCommand.ExecuteAsync(null);

        Assert.Equal("У вас последняя версия", раздел.CheckStatus);
        Assert.False(раздел.UpdateFound);
    }

    [Fact]
    public async Task Вышедшая_версия_называется_номером()
    {
        var раздел = Раздел(Ответ(доступно: true, последняя: "1.3.0"));

        await раздел.CheckUpdatesCommand.ExecuteAsync(null);

        Assert.Contains("1.3.0", раздел.CheckStatus);
        Assert.True(раздел.UpdateFound, "кнопка «Что нового» не появилась");
    }

    [Fact]
    public async Task Молчащий_backend_тоже_получает_ответ()
    {
        // Самый частый случай на свежей машине: backend ещё поднимается.
        // Пустая строка вместо ответа выглядела бы как сломанная кнопка.
        var раздел = Раздел("", HttpStatusCode.ServiceUnavailable);

        await раздел.CheckUpdatesCommand.ExecuteAsync(null);

        Assert.Contains("Не удалось проверить", раздел.CheckStatus);
    }

    [Fact]
    public async Task Ошибка_проверки_передаётся_словами()
    {
        // GitHub недоступен, исчерпан предел запросов, нет сети — человеку
        // важно отличить это от «обновлений нет».
        var раздел = Раздел(Ответ(доступно: false, ошибка: "нет подключения"));

        await раздел.CheckUpdatesCommand.ExecuteAsync(null);

        Assert.Contains("нет подключения", раздел.CheckStatus);
        Assert.DoesNotContain("последняя версия", раздел.CheckStatus);
    }

    [Fact]
    public async Task Версия_берётся_у_backend()
    {
        // Он читает VERSION.json — ту самую версию, которая стоит у человека.
        var раздел = Раздел(Ответ(доступно: false, текущая: "9.9.9"));

        await раздел.CheckUpdatesCommand.ExecuteAsync(null);

        Assert.Equal("9.9.9", раздел.Version);
    }

    // ==================== Сведения ====================

    [Fact]
    public void Версия_известна_ещё_до_ответа_backend()
    {
        // Пока backend поднимается, прочерк вместо версии висел бы всё время
        // запуска — а спрашивают её как раз тогда, когда что-то не работает.
        var раздел = Раздел(Ответ(доступно: false));

        Assert.NotEqual("—", раздел.Version);
    }

    [Fact]
    public void Платформа_спрашивается_у_системы()
    {
        // Записанное строкой «Windows x64» врало бы на Mac и Linux: сборки
        // делаются из одних и тех же исходников под все три.
        var платформа = Раздел(Ответ(доступно: false)).Platform;

        Assert.NotEmpty(платформа);
        Assert.DoesNotContain("X64", платформа);  // строчными, не как в системе

        if (OperatingSystem.IsWindows())
        {
            Assert.StartsWith("Windows", платформа);
        }
    }

    [Fact]
    public void Адрес_backend_виден()
    {
        // Первое, что спрашивают при «лаунчер пишет offline»: куда он вообще
        // стучится.
        Assert.Equal(Адрес, Раздел(Ответ(доступно: false)).BackendAddress);
    }
}
