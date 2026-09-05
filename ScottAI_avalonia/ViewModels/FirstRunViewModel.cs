using System;
using System.Threading;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Мастер первого запуска.
///
/// Показывается, пока машина не готова: без torch и моделей речи Scott не
/// работает вовсе, а весят они около четырёх гигабайт и в дистрибутив не
/// входят. Всю работу делает backend/bootstrap.py — здесь только то, что
/// человек видит: что происходит, сколько осталось и что делать, если
/// сорвалось.
/// </summary>
public partial class FirstRunViewModel : ViewModelBase
{
    private readonly SetupService _setup = new();
    private CancellationTokenSource? _cancellation;

    /// <summary>Вызывается, когда всё готово — окно переходит к обычной работе.</summary>
    public event Action? Finished;

    [ObservableProperty] private bool _visible;

    /// <summary>Идёт ли установка прямо сейчас — от неё зависят кнопки.</summary>
    [ObservableProperty] private bool _running;

    [ObservableProperty] private string _title = "Подготовка Scott";

    [ObservableProperty] private string _explanation =
        "Проверяю, что уже установлено…";

    [ObservableProperty] private string _status = "";

    [ObservableProperty] private double _progress;

    [ObservableProperty] private string? _error;

    /// <summary>Кнопка появляется только после сбоя: повторять успешную установку незачем.</summary>
    public bool CanRetry => Error is not null && !Running;

    partial void OnErrorChanged(string? value) => OnPropertyChanged(nameof(CanRetry));

    partial void OnRunningChanged(bool value) => OnPropertyChanged(nameof(CanRetry));

    /// <summary>
    /// Проверить готовность и, если нужно, показать мастер.
    ///
    /// Возвращает true, если можно сразу запускать backend: на готовой машине
    /// мастер не показывается вовсе, и человек его никогда не увидит.
    /// </summary>
    public async Task<bool> EnsureReadyAsync()
    {
        var readiness = await _setup.CheckAsync();

        if (readiness.Ready)
        {
            return true;
        }

        Visible = true;
        Explanation = BuildExplanation(readiness.Gpu);

        // Установка начинается сама: выбора всё равно нет — без библиотек
        // программа не работает, а лишнее подтверждение только задержало бы
        // человека перед неизбежным.
        await InstallAsync();
        return !Visible;
    }

    [RelayCommand]
    private async Task Retry()
    {
        Error = null;
        await InstallAsync();
    }

    private async Task InstallAsync()
    {
        Running = true;
        Error = null;
        Progress = 0;
        Status = "Начинаю…";

        _cancellation = new CancellationTokenSource();

        var progress = new Progress<SetupProgress>(step =>
        {
            Status = step.Message;
            Progress = Math.Clamp(step.Fraction * 100, 0, 100);
        });

        var (success, error) = await _setup.RunAsync(progress, _cancellation.Token);

        Running = false;

        if (!success)
        {
            Error = error;
            Status = "Не получилось";
            return;
        }

        Progress = 100;
        Status = "Готово";
        Visible = false;
        Finished?.Invoke();
    }

    private static string BuildExplanation(string? gpu)
    {
        // Про размер и время говорится честно и сразу: скачивание идёт
        // минутами, и человек, не понимающий почему, решит, что программа
        // зависла.
        if (gpu is not null)
        {
            return $"Нашлась {gpu}. Скачаю библиотеки под неё и модели речи — " +
                   "около 4 ГБ, обычно 5–15 минут. На видеокарте Scott распознаёт фразу за секунду.";
        }

        return "Видеокарта NVIDIA не найдена — поставлю сборку для процессора и модели речи, " +
               "около 1 ГБ. Scott будет работать, но распознавание займёт около шести секунд на фразу.";
    }
}
