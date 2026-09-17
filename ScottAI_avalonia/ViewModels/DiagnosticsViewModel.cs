using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Что у Scott работает прямо сейчас.
///
/// Раздел для одного случая: «у меня не работает». Раньше на этот вопрос
/// отвечали логи — то есть человеку предлагалось прочесть чужой технический
/// текст и самому догадаться, что в нём не так. Здесь он видит список: микрофон,
/// динамики, речь, модель, сеть — и рядом с каждым, работает оно или нет.
///
/// Кнопка «Скопировать» кладёт то же самое текстом в буфер обмена. Это главный
/// способ рассказать о поломке: вместо «у меня не работает» — восемь строк, по
/// которым видно, что именно.
/// </summary>
public partial class DiagnosticsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<HealthCheck> Checks { get; } = new();

    /// <summary>
    /// Что Scott услышал за последнее время.
    ///
    /// Сюда смотрят, когда «Scott меня не слышит» или «голосом он умеет
    /// меньше, чем в чате». Разбор у голоса и чата общий, поэтому дело
    /// почти всегда в тексте: Scott расслышал не то или не узнал в сказанном
    /// своё имя. Пока этого не видно, чинить приходится вслепую.
    /// </summary>
    public ObservableCollection<HeardEntry> Heard { get; } = new();

    [ObservableProperty] private string _heardSummary = "";
    [ObservableProperty] private bool _hasHeard;

    [ObservableProperty] private string _summary = "";
    [ObservableProperty] private string _state = "ok";
    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;

    /// <summary>Сообщение о том, что отчёт скопирован. Гаснет само.</summary>
    [ObservableProperty] private string _copied = "";

    public bool AllGood => State == "ok";
    public bool HasFailures => State == "fail";

    partial void OnStateChanged(string value)
    {
        OnPropertyChanged(nameof(AllGood));
        OnPropertyChanged(nameof(HasFailures));
    }

    public DiagnosticsViewModel(BackendClient client)
    {
        _client = client;
    }

    /// <summary>
    /// Перепроверить всё.
    ///
    /// Зовётся при каждом заходе на страницу, а не один раз при создании:
    /// состояние меняется — микрофон отключают, ключ вводят, интернет
    /// пропадает, — и показывать снимок получасовой давности бессмысленно.
    /// </summary>
    [RelayCommand]
    public async Task Refresh()
    {
        Loading = true;
        Error = null;

        try
        {
            var отчёт = await _client.HealthChecksAsync();

            if (отчёт is null)
            {
                // Сам backend и есть первая проверка: если он не ответил,
                // остальные и не выполнялись.
                Error = "Backend не отвечает — проверить остальное некому";
                State = "fail";
                Summary = "Backend не отвечает";
                Checks.Clear();
                return;
            }

            State = отчёт.State;
            Summary = отчёт.Summary;

            Checks.Clear();
            foreach (var проверка in отчёт.Checks)
            {
                Checks.Add(проверка);
            }

            await ОбновитьУслышанное();
        }
        finally
        {
            Loading = false;
        }
    }

    private async Task ОбновитьУслышанное()
    {
        var ответ = await _client.HeardAsync();

        Heard.Clear();
        HeardSummary = "";

        if (ответ is null)
        {
            HasHeard = false;
            return;
        }

        foreach (var запись in ответ.Heard)
        {
            Heard.Add(запись);
        }

        HasHeard = Heard.Count > 0;

        if (!HasHeard)
        {
            return;
        }

        // Главное число здесь — доля прошедших мимо. Если Scott слышит
        // сказанное, но узнаёт своё имя в трети случаев, лечить надо имя, а не
        // разбор команд.
        var мимо = ответ.Summary.Outcomes.TryGetValue("мимо", out var м) ? м : 0;
        var выполнено = ответ.Summary.Outcomes.TryGetValue("выполнена", out var в) ? в : 0;

        HeardSummary = $"Услышано {ответ.Summary.Total}: выполнено {выполнено}, "
                       + $"прошло мимо {мимо}";
    }

    /// <summary>Забыть услышанное. Это речь человека, и он вправе её стереть.</summary>
    [RelayCommand]
    private async Task ClearHeard()
    {
        var согласен = await DialogService.ConfirmAsync(
            "Забыть услышанное?",
            "Scott сотрёт список фраз, которые он расслышал. На его работу это не "
            + "влияет — список нужен, чтобы разбираться, почему он вас не понял.",
            "Забыть");

        if (!согласен)
        {
            return;
        }

        if (await _client.ClearHeardAsync())
        {
            await ОбновитьУслышанное();
        }
    }

    /// <summary>
    /// Отчёт словами — для буфера обмена.
    ///
    /// Текст берётся у backend, а не собирается здесь из показанного: в нём
    /// вырезаны ключи, и повторять эту работу в лаунчере значило бы однажды
    /// забыть её повторить.
    ///
    /// Кладёт его в буфер сама страница: буфер обмена в Avalonia живёт у окна,
    /// и добираться до него из модели пришлось бы окольным путём.
    /// </summary>
    public Task<string?> BuildReportAsync() => _client.HealthChecksTextAsync();

    /// <summary>Сказать человеку, что отчёт скопирован, и погасить сообщение.</summary>
    public async Task ReportCopied()
    {
        Copied = "Отчёт скопирован — его можно вставить в сообщение";
        ToastService.Success("Отчёт скопирован");

        await Task.Delay(4000);
        Copied = "";
    }
}
