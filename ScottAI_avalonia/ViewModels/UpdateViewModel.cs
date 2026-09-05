using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Полоска «вышла новая версия» и всё, что за ней стоит.
///
/// Обновление не ставится само и не выпрашивается навязчиво: полоска
/// показывается один раз при запуске, её можно закрыть, и до следующего
/// запуска она не вернётся. Установщик скачивается и запускается только по
/// нажатию — это программа на компьютере человека, и решать ему.
/// </summary>
public partial class UpdateViewModel : ViewModelBase
{
    private readonly UpdateService _service = new();
    private readonly string _backendBase;
    private UpdateInfo? _info;
    private CancellationTokenSource? _cancellation;

    public UpdateViewModel(string backendBase)
    {
        _backendBase = backendBase;
    }

    /// <summary>Видна ли полоска с предложением обновиться.</summary>
    [ObservableProperty] private bool _visible;

    [ObservableProperty] private string _headline = "";

    [ObservableProperty] private string _notes = "";

    /// <summary>Идёт ли загрузка — на время неё кнопки заменяются полосой.</summary>
    [ObservableProperty] private bool _downloading;

    [ObservableProperty] private double _progress;

    [ObservableProperty] private string _status = "";

    [ObservableProperty] private string? _error;

    /// <summary>«61 МБ» — сколько весит установщик. Человек вправе знать заранее.</summary>
    [ObservableProperty] private string _sizeText = "";

    /// <summary>Дата выпуска словами: «10 сентября 2026».</summary>
    [ObservableProperty] private string _dateText = "";

    /// <summary>
    /// Спросить backend, вышло ли что-то новое.
    ///
    /// Тихо ничего не делает, если backend не ответил или обновлений нет:
    /// проверка обновлений — не то, ради чего стоит беспокоить человека
    /// сообщениями об ошибках.
    /// </summary>
    public async Task CheckAsync()
    {
        var info = await _service.CheckAsync(_backendBase);
        if (info is null || !info.Available)
        {
            return;
        }

        _info = info;
        Headline = $"Вышла версия {info.LatestVersion}";
        SizeText = FormatSize(info.AssetSize);
        DateText = FormatDate(info.ReleaseDate);

        // Заметки к выпуску бывают длинными; в карточку идёт начало, остальное
        // человек прочтёт на странице выпуска.
        Notes = Shorten(CleanMarkup(info.Notes), 200);
        Visible = true;
    }

    [RelayCommand]
    private void Dismiss()
    {
        Visible = false;
        _cancellation?.Cancel();
    }

    /// <summary>Открыть страницу выпуска в браузере — «что нового» целиком.</summary>
    [RelayCommand]
    private void OpenRelease()
    {
        var url = _info?.ReleaseUrl;
        if (string.IsNullOrWhiteSpace(url))
        {
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception)
        {
            // Браузер не открылся — не повод падать.
        }
    }

    [RelayCommand]
    private async Task Install()
    {
        if (_info is null || Downloading)
        {
            return;
        }

        Downloading = true;
        Error = null;
        Progress = 0;
        Status = "Скачиваю обновление…";

        _cancellation = new CancellationTokenSource();
        var total = _info.AssetSize;
        var progress = new Progress<double>(share =>
        {
            Progress = share * 100;

            // Проценты сами по себе мало что говорят: «12 из 61 МБ» сразу
            // отвечает на вопрос, сколько ещё ждать.
            Status = total > 0
                ? $"Скачано {FormatSize((long)(total * share))} из {FormatSize(total)}"
                : $"Скачано {share * 100:0}%";
        });

        var (path, error) = await _service.DownloadAsync(_info, progress, _cancellation.Token);

        Downloading = false;

        if (string.IsNullOrEmpty(path))
        {
            Error = error;
            Status = "";
            return;
        }

        Status = "Запускаю установщик…";

        try
        {
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch (Exception e)
        {
            Error = $"не удалось запустить установщик: {e.Message}";
            return;
        }

        // Установщик не сможет заменить файлы, пока программа открыта, поэтому
        // лаунчер закрывается сам — иначе человек упёрся бы в ошибку доступа.
        RequestShutdown?.Invoke();
    }

    /// <summary>Просьба закрыть лаунчер: установщику нужны незанятые файлы.</summary>
    public event Action? RequestShutdown;

    private static string FormatSize(long bytes)
    {
        if (bytes <= 0)
        {
            return "";
        }

        var megabytes = bytes / 1024.0 / 1024.0;
        return megabytes >= 1024
            ? $"{megabytes / 1024:0.#} ГБ"
            : $"{megabytes:0} МБ";
    }

    private static string FormatDate(string iso)
    {
        // GitHub отдаёт дату в ISO 8601. Показывать её человеку в таком виде
        // незачем, а падать из-за неразобранной строки — тем более.
        if (DateTimeOffset.TryParse(iso, out var moment))
        {
            return moment.ToLocalTime().ToString("d MMMM yyyy",
                new System.Globalization.CultureInfo("ru-RU"));
        }

        return "";
    }

    /// <summary>
    /// Убрать разметку из заметок к выпуску.
    ///
    /// На GitHub их пишут в markdown, и в карточке это выглядит мусором:
    /// «[!IMPORTANT]», «**жирный**», «## Заголовок», голые ссылки. Человеку
    /// нужна суть, а полный текст открывается кнопкой «Что нового».
    /// </summary>
    private static string CleanMarkup(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return "";
        }

        var lines = text.Split(new[] { (char)10, (char)13 },
                               StringSplitOptions.RemoveEmptyEntries);
        var kept = new System.Collections.Generic.List<string>();

        foreach (var raw in lines)
        {
            var line = raw.Trim().TrimStart('>', '#', '*', '-', ' ').Trim();
            line = line.Replace("**", "").Replace("`", "");

            // Служебные пометки и строки-ссылки в двух строках карточки
            // бесполезны — пропускаем их и берём следующую осмысленную.
            if (line.Length == 0 || line.StartsWith("[!") || line.StartsWith("http"))
            {
                continue;
            }

            kept.Add(line);
            if (kept.Count >= 3)
            {
                break;
            }
        }

        return string.Join(" · ", kept);
    }

    private static string Shorten(string text, int limit)
    {
        text = (text ?? "").Trim();
        if (text.Length <= limit)
        {
            return text;
        }

        return text[..limit].TrimEnd() + "…";
    }
}
