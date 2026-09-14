using System.Linq;
using System.Threading.Tasks;
using ScottAI.Mobile.Services;
using ScottAI.Mobile.ViewModels;

namespace ScottAI.Mobile.Tests;

/// <summary>Отвечает заранее известным — настоящий компьютер тестам недоступен.</summary>
public class ПодставнойКомпьютер : ScottClient
{
    private readonly CommandResult _ответ;

    public string? Получено { get; private set; }

    public ПодставнойКомпьютер(CommandResult ответ) => _ответ = ответ;

    public override Task<CommandResult> SendAsync(string text)
    {
        Получено = text;
        return Task.FromResult(_ответ);
    }
}

/// <summary>
/// Чат с телефона.
///
/// Здесь проверяется то, чего не бывает в обычных чатах: написанное выполняется
/// на домашнем компьютере, в пустой комнате. Поэтому отказ и обрыв связи — не
/// одно и то же, и перепутать их нельзя.
/// </summary>
public class ChatTests
{
    private static ChatViewModel Чат(CommandResult ответ) => new(new ПодставнойКомпьютер(ответ));

    private static CommandResult Обычный => new("Открыл браузер", Refused: false, Failed: false);

    [Fact]
    public async Task Сказанное_уходит_и_ответ_приходит()
    {
        var чат = Чат(Обычный);
        чат.Input = "открой браузер";

        await чат.SendCommand.ExecuteAsync(null);

        Assert.Equal(2, чат.Messages.Count);
        Assert.True(чат.Messages[0].Mine);
        Assert.Equal("Открыл браузер", чат.Messages[1].Text);
    }

    [Fact]
    public async Task Поле_очищается_сразу()
    {
        // Оставленный текст подталкивает отправить то же самое второй раз — а
        // вторая «открой браузер» откроет второе окно.
        var чат = Чат(Обычный);
        чат.Input = "открой браузер";

        await чат.SendCommand.ExecuteAsync(null);

        Assert.Equal("", чат.Input);
    }

    [Fact]
    public async Task Пустое_не_отправляется()
    {
        var чат = Чат(Обычный);
        чат.Input = "   ";

        await чат.SendCommand.ExecuteAsync(null);

        Assert.Empty(чат.Messages);
    }

    [Fact]
    public async Task Отказ_помечен_отказом()
    {
        // «Не буду выключать компьютер издалека» — Scott, работающий как
        // задумано. Показать это как сбой значит отправить человека чинить
        // исправное.
        var чат = Чат(new CommandResult("выключение издалека я не делаю",
            Refused: true, Failed: false));
        чат.Input = "выключи компьютер";

        await чат.SendCommand.ExecuteAsync(null);

        var ответ = чат.Messages.Last();
        Assert.True(ответ.Refused);
        Assert.False(ответ.Failed);
    }

    [Fact]
    public async Task Обрыв_связи_помечен_неудачей()
    {
        // Здесь наоборот: команда могла не дойти, и человек должен об этом
        // знать — иначе он решит, что дома уже всё сделано.
        var чат = Чат(new CommandResult("Связи с компьютером нет",
            Refused: false, Failed: true));
        чат.Input = "открой браузер";

        await чат.SendCommand.ExecuteAsync(null);

        Assert.True(чат.Messages.Last().Failed);
    }

    [Fact]
    public async Task Подсказка_отправляется_как_обычная_команда()
    {
        // Подсказки в пустом чате не украшение: Scott понимает не всё подряд,
        // и нажатие должно приводить ровно к тому же, что набранный текст.
        var компьютер = new ПодставнойКомпьютер(Обычный);
        var чат = new ChatViewModel(компьютер);

        await чат.UseHintCommand.ExecuteAsync("открой браузер");

        Assert.Equal("открой браузер", компьютер.Получено);
        Assert.Equal(2, чат.Messages.Count);
    }

    [Fact]
    public async Task Переписка_забывается_целиком()
    {
        // История живёт только в памяти: команды к домашнему компьютеру — не
        // та переписка, которую стоит хранить в телефоне, который теряют.
        var чат = Чат(Обычный);
        чат.Input = "открой браузер";
        await чат.SendCommand.ExecuteAsync(null);

        чат.ClearCommand.Execute(null);

        Assert.Empty(чат.Messages);
        Assert.True(чат.Empty);
    }
}
