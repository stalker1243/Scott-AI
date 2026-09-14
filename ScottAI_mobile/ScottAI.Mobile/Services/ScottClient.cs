using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using ScottAI.Mobile.Models;

namespace ScottAI.Mobile.Services;

/// <summary>Чем закончилась команда — и чем именно.</summary>
public record CommandResult(string Text, bool Refused, bool Failed);

/// <summary>
/// Разговор с компьютером.
///
/// ПОЧЕМУ НАПРЯМУЮ, А НЕ ЧЕРЕЗ ПОСРЕДНИКА. Дома телефон и компьютер в одной
/// сети и видят друг друга без чьей-либо помощи. Любой посредник здесь — это
/// чужая машина, через которую пойдут команды к вашему компьютеру, и заводить
/// её ради того, что и так работает, не стоит.
///
/// Вне дома этот путь не работает, и честно сказать об этом важнее, чем
/// делать вид, что работает: там остаётся Telegram — тот же Scott, те же
/// правила, но через бота, из обычного клиента Telegram.
///
/// КЛЮЧ. Уходит в заголовке каждого запроса. Без него компьютер отвечает 404
/// на всё: снаружи его API просто не существует.
/// </summary>
public class ScottClient
{
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(70) };

    private static string База(string host)
    {
        var адрес = (host ?? "").Trim();

        if (адрес.Length == 0)
        {
            return "";
        }

        // Человек вводит «192.168.1.5» — без схемы и часто без порта. Дописать
        // их за него надёжнее, чем объяснять, почему «не подключается».
        if (!адрес.StartsWith("http://") && !адрес.StartsWith("https://"))
        {
            адрес = "http://" + адрес;
        }

        if (!адрес[7..].Contains(':'))
        {
            адрес += ":8000";
        }

        return адрес.TrimEnd('/');
    }

    /// <summary>
    /// Отзывается ли компьютер по этому адресу.
    ///
    /// Спрашивается до привязки: перепутанный адрес и неверный код выглядят
    /// для человека одинаково — «не вышло», — а чинятся по-разному.
    /// </summary>
    public async Task<bool> ReachableAsync(string host)
    {
        var адрес = База(host);
        if (адрес.Length == 0)
        {
            return false;
        }

        try
        {
            using var источник = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var ответ = await _http.GetAsync($"{адрес}/health", источник.Token);
            return ответ.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Привязаться по коду с экрана компьютера.
    ///
    /// Код живёт минуту и годится один раз: столько нужно, чтобы прочитать его
    /// и набрать здесь. Возвращает ключ — единственный раз, когда его видно.
    /// </summary>
    public async Task<(bool Успех, string Ключ, string Ошибка)> PairAsync(
        string host, string code, string name)
    {
        var адрес = База(host);
        if (адрес.Length == 0)
        {
            return (false, "", "Не указан адрес компьютера");
        }

        try
        {
            var ответ = await _http.PostAsJsonAsync($"{адрес}/remote/pair",
                new { code, name });

            var данные = await ответ.Content.ReadFromJsonAsync<JsonElement>();

            if (данные.TryGetProperty("success", out var успех) && успех.GetBoolean())
            {
                return (true, данные.GetProperty("token").GetString() ?? "", "");
            }

            var причина = данные.TryGetProperty("error", out var о)
                ? о.GetString() ?? "Код не принят"
                : "Код не принят";

            return (false, "", причина);
        }
        catch (Exception e)
        {
            return (false, "", $"Компьютер не отвечает: {e.Message}");
        }
    }

    /// <summary>
    /// Отдать команду.
    ///
    /// Отказ возвращается как обычный ответ, а не как ошибка, и это намеренно:
    /// «не буду выключать компьютер издалека» — тоже ответ Scott, и человек
    /// должен его прочитать, а не увидеть «сбой связи».
    /// </summary>
    public async Task<CommandResult> SendAsync(string text)
    {
        var настройки = SettingsStore.Current;
        var адрес = База(настройки.Host);

        if (адрес.Length == 0 || настройки.Token.Length == 0)
        {
            return new CommandResult(
                "Телефон ещё не привязан к компьютеру — сделайте это в «Связи».",
                Refused: false, Failed: true);
        }

        try
        {
            using var запрос = new HttpRequestMessage(HttpMethod.Post, $"{адрес}/remote/command")
            {
                Content = JsonContent.Create(new { text }),
            };
            запрос.Headers.Add("X-Scott-Device", настройки.Token);

            var ответ = await _http.SendAsync(запрос);

            if (ответ.StatusCode == System.Net.HttpStatusCode.Forbidden)
            {
                return new CommandResult(
                    "Компьютер больше не признаёт этот телефон — видимо, его отвязали. "
                    + "Привяжитесь заново в «Связи».",
                    Refused: false, Failed: true);
            }

            var данные = await ответ.Content.ReadFromJsonAsync<JsonElement>();

            var слова = данные.TryGetProperty("response", out var р)
                ? р.GetString() ?? ""
                : "";

            var отказ = данные.TryGetProperty("refused", out var о) && о.GetBoolean();

            return new CommandResult(
                слова.Length > 0 ? слова : "Сделано",
                Refused: отказ,
                Failed: false);
        }
        catch (TaskCanceledException)
        {
            return new CommandResult(
                "Компьютер не ответил вовремя. Он мог уснуть или выйти из сети.",
                Refused: false, Failed: true);
        }
        catch (Exception e)
        {
            return new CommandResult($"Связи с компьютером нет: {e.Message}",
                Refused: false, Failed: true);
        }
    }
}
