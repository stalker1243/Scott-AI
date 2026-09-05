using System;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Вкладка «Логи»: что пошло не так и как сообщить об этом разработчику.
///
/// Без неё о поломке на чужом компьютере узнать нечего — «не работает» не
/// отладишь. Здесь человек видит сами ошибки, состояние своей машины (прежде
/// всего — задействована ли видеокарта) и может одной кнопкой собрать архив
/// для отправки.
/// </summary>
public partial class LogsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<LogEntry> Errors { get; } = new();

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private bool _building;
    [ObservableProperty] private string _note = "";
    [ObservableProperty] private string? _status;
    [ObservableProperty] private string? _reportPath;
    [ObservableProperty] private string _reportFolder = "";

    // ---- Сведения о машине ----
    [ObservableProperty] private string _gpuSummary = "проверяю…";
    [ObservableProperty] private string? _gpuHint;
    [ObservableProperty] private bool _gpuWarning;

    public LogsViewModel(BackendClient client)
    {
        _client = client;
        _ = Refresh();
    }

    [RelayCommand]
    private async Task Refresh()
    {
        Loading = true;
        Status = null;
        try
        {
            var errors = await _client.RecentErrorsAsync(100);
            Errors.Clear();
            foreach (var e in errors) Errors.Add(e);

            await LoadGpu();

            if (errors.Count == 0)
            {
                Status = "Ошибок не найдено — всё в порядке";
            }
        }
        finally
        {
            Loading = false;
        }
    }

    private async Task LoadGpu()
    {
        var gpu = await _client.GpuInfoAsync();
        if (gpu is null)
        {
            GpuSummary = "backend не отвечает";
            GpuWarning = false;
            GpuHint = null;
            return;
        }

        if (gpu.CudaAvailable)
        {
            var memory = gpu.MemoryGb is > 0 ? $", {gpu.MemoryGb:0.#} ГБ" : "";
            GpuSummary = $"{gpu.Device}{memory} — распознавание и синтез идут на видеокарте";
            GpuWarning = false;
            GpuHint = null;
        }
        else
        {
            // Отдельно разделяем два случая: видеокарты нет вовсе (тогда всё в
            // порядке, просто медленнее) и видеокарта есть, но torch собран без
            // CUDA — вот это стоит починить, разница почти двадцатикратная.
            GpuSummary = "работа идёт на процессоре";
            GpuWarning = !gpu.CudaBuild;
            GpuHint = gpu.Hint;
        }
    }

    [RelayCommand]
    private async Task BuildReport()
    {
        Building = true;
        Status = null;
        ReportPath = null;
        try
        {
            var result = await _client.BuildReportAsync(string.IsNullOrWhiteSpace(Note) ? null : Note.Trim());
            if (result is { Success: true })
            {
                ReportPath = result.Path;
                ReportFolder = result.Folder;
                var kb = result.SizeBytes / 1024.0;
                Status = $"Готово: {kb:0.#} КБ. Ключи и токены из отчёта вырезаны.";
                ToastService.Success("Отчёт собран");
            }
            else
            {
                Status = result?.Message ?? "Не удалось собрать отчёт";
                ToastService.Error(Status);
            }
        }
        finally
        {
            Building = false;
        }
    }

    /// <summary>Показывать ли кнопку Telegram: пока адрес не задан, её нет.</summary>
    public bool HasTelegram => SupportLinks.HasTelegram;

    /// <summary>
    /// Открыть чат поддержки в Telegram и папку с отчётом рядом.
    ///
    /// Файл отправляет сам человек: программа не может приложить его к
    /// сообщению за него, а зашивать в неё ключ доступа к боту нельзя — его
    /// вытащит любой, кто откроет файл программы. Зато папка открывается
    /// сразу, и архив остаётся перетащить в чат.
    /// </summary>
    [RelayCommand]
    private void ReportInTelegram()
    {
        if (!SupportLinks.HasTelegram)
        {
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo { FileName = SupportLinks.Telegram, UseShellExecute = true });

            if (!string.IsNullOrWhiteSpace(ReportFolder))
            {
                Process.Start(new ProcessStartInfo { FileName = ReportFolder, UseShellExecute = true });
                ToastService.Info("Перетащите архив из открывшейся папки в чат");
            }
        }
        catch (Exception e)
        {
            ToastService.Error($"Не удалось открыть Telegram: {e.Message}");
        }
    }

    /// <summary>
    /// Открыть страницу создания обращения на GitHub.
    ///
    /// Заголовок и тело подставляются заранее: человек, у которого что-то не
    /// работает, не должен ещё и придумывать, какие сведения приложить. Сам
    /// архив прикрепляется перетаскиванием — через ссылку его не передать.
    /// </summary>
    [RelayCommand]
    private void ReportOnGitHub()
    {
        // Описание уходит в адресную строку, а её длину браузеры ограничивают
        // (обычно около 8 КБ). Длинный рассказ обрезаем: остальное человек
        // допишет прямо на странице, где никаких ограничений нет.
        var note = (Note ?? "").Trim();
        if (note.Length > 1500)
        {
            note = note[..1500].TrimEnd() + "… (продолжите здесь)";
        }

        var body = string.Join(Environment.NewLine, new[]
        {
            "### Что случилось",
            note,
            "",
            "### Что делали до этого",
            "",
            "### Архив с диагностикой",
            ReportPath is null
                ? "(соберите его кнопкой «Собрать отчёт» и перетащите сюда файл)"
                : $"Файл: {System.IO.Path.GetFileName(ReportPath)} — перетащите его в это поле.",
            "",
            "Ключи и токены из архива вырезаны.",
        });

        var url = "https://github.com/stalker1243/Scott-AI/issues/new"
                  + "?title=" + Uri.EscapeDataString(BuildTitle())
                  + "&body=" + Uri.EscapeDataString(body);

        try
        {
            Process.Start(new ProcessStartInfo { FileName = url, UseShellExecute = true });
        }
        catch (Exception e)
        {
            ToastService.Error($"Не удалось открыть браузер: {e.Message}");
        }
    }

    private string BuildTitle()
    {
        var note = (Note ?? "").Trim().Split('\n')[0];
        if (note.Length == 0)
        {
            return "Проблема в работе Scott";
        }

        return note.Length <= 60 ? note : note[..60].TrimEnd() + "…";
    }

    /// <summary>Открыть папку с отчётом в проводнике — дальше пользователь приложит файл сам.</summary>
    [RelayCommand]
    private void OpenReportFolder()
    {
        if (string.IsNullOrWhiteSpace(ReportFolder)) return;
        try
        {
            Process.Start(new ProcessStartInfo { FileName = ReportFolder, UseShellExecute = true });
        }
        catch (Exception e)
        {
            ToastService.Error($"Не удалось открыть папку: {e.Message}");
        }
    }
}
