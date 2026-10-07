using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Раздел «Модель»: кто отвечает на вопросы и каким ключом.
///
/// Первое, куда человек идёт на новой машине: без ключа Scott выполняет
/// команды, но на вопросы не отвечает вовсе. Раньше это была третья вкладка
/// внутри Настроек — рядом с громкостью и микрофоном.
///
/// Проверяется логика выбора, а не разговор с backend: запрос здесь никуда не
/// уходит вовсе. Так и надо — проверки не должны зависеть от того, поднят ли
/// сейчас backend на этой машине.
/// </summary>
[Collection("avalonia")]
public class AiModelTests
{
    /// <summary>
    /// Backend, которого нет.
    ///
    /// Прежде это изображалось обращением на заведомо глухой порт — и оказалось
    /// не гарантией: на машине с несколькими сетевыми переходниками по такому
    /// адресу иногда кто-то отвечает, и проверка «применение не удалось»
    /// падала через прогон, без связи с тем, что правили. Теперь отказ
    /// гарантирован, потому что запрос вообще никуда не уходит.
    /// </summary>
    private sealed class БезBackend : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken token)
        {
            throw new HttpRequestException("backend не отвечает");
        }
    }

    private static AiModelViewModel Раздел() => new(new BackendClient(new БезBackend()));

    private static AiProvider Провайдер(string id, params string[] модели) => new()
    {
        Id = id,
        Models = модели.Select(m => new AiModelOption { Id = m }).ToList(),
    };

    // ==================== Подключён ли кто-нибудь ====================

    [Fact]
    public void Без_провайдера_считается_ненастроенным()
    {
        // От этого зависит, что человек прочтёт на странице: «Подключено» или
        // «Команды Scott выполняет и так, но на вопросы отвечать некому».
        var раздел = Раздел();

        Assert.False(раздел.Connected);
    }

    [Fact]
    public void С_провайдером_считается_подключённым()
    {
        var раздел = Раздел();

        раздел.ActiveProvider = "Groq";

        Assert.True(раздел.Connected);
    }

    // ==================== Выбор ====================

    [Fact]
    public void Смена_провайдера_стирает_введённый_ключ()
    {
        // Ключ относится к провайдеру: оставленный при переключении, он ушёл бы
        // не туда — и отказ выглядел бы как «ключ неверный», хотя неверен
        // адресат.
        var раздел = Раздел();
        раздел.ApiKeyInput = "секретный-ключ-groq";

        раздел.SetSelectedProviderCommand.Execute(Провайдер("OpenAI", "gpt-4o"));

        Assert.Equal("", раздел.ApiKeyInput);
    }

    [Fact]
    public void Смена_провайдера_подставляет_его_первую_модель()
    {
        // Иначе в списке осталась бы модель прежнего провайдера, которой у
        // нового нет, и «Применить» кончилось бы отказом.
        var раздел = Раздел();

        раздел.SetSelectedProviderCommand.Execute(Провайдер("OpenAI", "gpt-4o", "gpt-4o-mini"));

        Assert.Equal("gpt-4o", раздел.SelectedModel);
    }

    [Fact]
    public void Возврат_к_работающему_провайдеру_показывает_его_модель()
    {
        // Человек ходит по списку туда-сюда, сравнивая. Вернувшись к тому, кто
        // отвечает сейчас, он должен увидеть модель, которая и работает, — а не
        // первую из списка.
        var раздел = Раздел();
        раздел.ActiveProvider = "Groq";
        раздел.ActiveModel = "llama-3.3-70b-versatile";

        раздел.SetSelectedProviderCommand.Execute(Провайдер("Groq", "llama-3.1-8b", "llama-3.3-70b-versatile"));

        Assert.Equal("llama-3.3-70b-versatile", раздел.SelectedModel);
    }

    // ==================== Применение ====================

    [Fact]
    public async Task Без_выбранного_провайдера_говорят_словами()
    {
        // Молчаливый выход — худшее, что можно сделать с человеком, который
        // только что ввёл ключ: кнопка нажата, и ничего не произошло.
        var раздел = Раздел();

        await раздел.ApplyCommand.ExecuteAsync(null);

        Assert.NotNull(раздел.Error);
        Assert.Contains("провайдера", раздел.Error!);
    }

    [Fact]
    public async Task У_провайдера_без_моделей_честный_отказ()
    {
        var раздел = Раздел();
        раздел.SelectedProvider = Провайдер("Пустой");
        раздел.SelectedModel = null;

        await раздел.ApplyCommand.ExecuteAsync(null);

        Assert.NotNull(раздел.Error);
        Assert.Contains("моделей", раздел.Error!);
    }

    [Fact]
    public async Task Введённая_руками_модель_важнее_выбранной_в_списке()
    {
        // Список подсказывает известные, но новые модели выходят чаще, чем
        // обновляется Scott. Указанное вручную — намеренный выбор человека.
        var раздел = Раздел();
        раздел.SelectedProvider = Провайдер("Groq", "llama-3.1-8b");
        раздел.SelectedModel = "llama-3.1-8b";
        раздел.UseCustomModel = true;
        раздел.CustomModel = "  llama-3.3-70b-versatile  ";

        await раздел.ApplyCommand.ExecuteAsync(null);

        // Backend недоступен, применение не удастся — но выбор модели делается
        // до запроса, и именно он здесь проверяется. Заодно видно, что отказ
        // backend не роняет команду, а объясняется словами.
        Assert.Equal("llama-3.3-70b-versatile", раздел.SelectedModel);
        Assert.Contains("Не удалось применить", раздел.Error ?? "");
    }

    [Fact]
    public async Task Пустая_ручная_модель_не_вытесняет_выбранную()
    {
        // Галочку поставили, а поле не заполнили — это не повод остаться вовсе
        // без модели.
        var раздел = Раздел();
        раздел.SelectedProvider = Провайдер("Groq", "llama-3.1-8b");
        раздел.SelectedModel = "llama-3.1-8b";
        раздел.UseCustomModel = true;
        раздел.CustomModel = "   ";

        await раздел.ApplyCommand.ExecuteAsync(null);

        Assert.Equal("llama-3.1-8b", раздел.SelectedModel);
    }
}
