using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Что это за программа и какой она версии.
///
/// Версия была разбросана: в карточке обновления она появлялась, только когда
/// вышла новая, а в остальное время узнать её было негде — при жалобе «у меня
/// не работает» первым делом спрашивают именно её.
///
/// Проверка обновлений здесь отвечает ВСЕГДА. В карточке наверху она тиха
/// намеренно: беспокоить человека сообщением «обновлений нет» посреди работы
/// незачем. Но кнопку, на которую нажали руками, молчание превращает в
/// сломанную: нажал — и не понял, случилось ли что-нибудь.
/// </summary>
public partial class AboutViewModel : ViewModelBase
{
    private readonly UpdateService _updates;
    private readonly string _backendBase;

    /// <summary>Открыть страницу выпуска, если он есть.</summary>
    private string? _releaseUrl;

    [ObservableProperty] private string _version = "—";
    [ObservableProperty] private string _checkStatus = "";
    [ObservableProperty] private bool _checking;
    [ObservableProperty] private bool _updateFound;

    public string Developer => "Phantom";

    /// <summary>
    /// На чём программа работает прямо сейчас.
    ///
    /// Спрашивается у системы, а не пишется строкой: сборки одни и те же
    /// исходники дают под Windows, Linux и Mac, и записанное вручную «Windows
    /// x64» врало бы на двух из трёх.
    /// </summary>
    public string Platform
    {
        get
        {
            var система = OperatingSystem.IsWindows() ? "Windows"
                : OperatingSystem.IsMacOS() ? "macOS"
                : OperatingSystem.IsLinux() ? "Linux"
                : "неизвестная система";

            // Строчными: «Windows X64» с заглавной X выглядит опечаткой, а
            // именно так это значение и приходит из системы.
            return $"{система} {RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant()}";
        }
    }

    public string BackendAddress => _backendBase;

    public AboutViewModel(string backendBase, UpdateService? updates = null)
    {
        _backendBase = backendBase;
        _updates = updates ?? new UpdateService();

        // Версия сборки — пока не ответил backend. Он читает VERSION.json и
        // знает настоящую; но показывать прочерк, пока он поднимается, значит
        // показывать прочерк на всё время запуска.
        Version = Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "—";

        _ = LoadVersionAsync();
        BackendReady.WhenReady(() => _ = LoadVersionAsync());
    }

    private async Task LoadVersionAsync()
    {
        var info = await _updates.CheckAsync(_backendBase);
        if (info is not null && !string.IsNullOrWhiteSpace(info.CurrentVersion))
        {
            Version = info.CurrentVersion;
        }
    }

    [RelayCommand]
    private async Task CheckUpdates()
    {
        Checking = true;
        UpdateFound = false;
        CheckStatus = "Проверяю…";

        try
        {
            // force: без него ответ придёт из кэша, и нажатие «проверить» не
            // проверило бы ничего — а человек нажимает её как раз тогда, когда
            // ждёт свежий ответ.
            var info = await _updates.CheckAsync(_backendBase, force: true);

            if (info is null)
            {
                CheckStatus = "Не удалось проверить: backend не отвечает";
                return;
            }

            if (!string.IsNullOrWhiteSpace(info.CurrentVersion))
            {
                Version = info.CurrentVersion;
            }

            if (!string.IsNullOrWhiteSpace(info.Error))
            {
                CheckStatus = $"Не удалось проверить: {info.Error}";
                return;
            }

            if (info.Available)
            {
                _releaseUrl = info.ReleaseUrl;
                UpdateFound = true;
                CheckStatus = $"Вышла версия {info.LatestVersion}";
                return;
            }

            CheckStatus = "У вас последняя версия";
        }
        finally
        {
            Checking = false;
        }
    }

    [RelayCommand]
    private void OpenRelease()
    {
        if (string.IsNullOrWhiteSpace(_releaseUrl))
        {
            return;
        }

        try
        {
            System.Diagnostics.Process.Start(
                new System.Diagnostics.ProcessStartInfo(_releaseUrl) { UseShellExecute = true });
        }
        catch (Exception)
        {
            // Не открылся браузер — не повод показывать ошибку: человек и так
            // видит номер вышедшей версии.
        }
    }
}
