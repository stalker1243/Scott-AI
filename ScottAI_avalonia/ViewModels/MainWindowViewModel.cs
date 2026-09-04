using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class MainWindowViewModel : ViewModelBase
{
    private readonly BackendClient _client = new();
    private readonly DispatcherTimer _healthTimer;
    private bool _everOnline;

    [ObservableProperty]
    private ViewModelBase _currentPage;

    [ObservableProperty]
    private string _pageTitle = "Главная";

    [ObservableProperty]
    private string _activePage = "home";

    [ObservableProperty]
    private string _backendStatus = "starting"; // starting | online | offline

    [ObservableProperty]
    private bool _isClassicStyle = ThemeService.CurrentStyle == AppStyle.Classic;

    [ObservableProperty]
    private bool _dialogVisible;

    [ObservableProperty]
    private string _dialogTitle = "";

    [ObservableProperty]
    private string _dialogMessage = "";

    [ObservableProperty]
    private string _dialogConfirmLabel = "Удалить";

    [ObservableProperty]
    private bool _dialogDanger = true;

    public ObservableCollection<ToastMessage> Toasts { get; } = new();

    public HomeViewModel Home { get; }
    public ChatViewModel Chat { get; }
    public SystemViewModel SystemPage { get; }
    public AutomationViewModel AutomationPage { get; }
    public AnalyticsViewModel AnalyticsPage { get; }
    public SettingsViewModel SettingsPage { get; }
    public ProfileViewModel ProfilePage { get; } = new();

    public MainWindowViewModel()
    {
        Home = new HomeViewModel(_client, NavigateChat);
        Chat = new ChatViewModel(_client);
        SystemPage = new SystemViewModel(_client);
        AutomationPage = new AutomationViewModel(_client);
        AnalyticsPage = new AnalyticsViewModel(_client);
        SettingsPage = new SettingsViewModel(_client);
        _currentPage = Home;

        ThemeService.StyleApplied += style => IsClassicStyle = style == AppStyle.Classic;

        DialogService.ConfirmRequested += (title, message, confirmLabel, danger) =>
        {
            DialogTitle = title;
            DialogMessage = message;
            DialogConfirmLabel = confirmLabel;
            DialogDanger = danger;
            DialogVisible = true;
        };

        ToastService.ToastRequested += toast => _ = ShowToast(toast);

        _healthTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
        _healthTimer.Tick += async (_, _) => await CheckHealthAsync();
        _healthTimer.Start();
        _ = CheckHealthAsync();
    }

    private async Task CheckHealthAsync()
    {
        var online = await _client.HealthAsync();
        if (online) _everOnline = true;
        BackendStatus = online ? "online" : (_everOnline ? "offline" : "starting");
    }

    private async Task ShowToast(ToastMessage toast)
    {
        // Не больше 4 уведомлений одновременно, чтобы не завалить угол экрана при цепочке действий.
        while (Toasts.Count >= 4) Toasts.RemoveAt(0);

        Toasts.Add(toast);
        await Task.Delay(TimeSpan.FromSeconds(4));
        Toasts.Remove(toast);
    }

    [RelayCommand]
    private void DismissToast(ToastMessage toast) => Toasts.Remove(toast);

    [RelayCommand]
    private void NavigateHome()
    {
        CurrentPage = Home;
        PageTitle = "Главная";
        ActivePage = "home";
    }

    [RelayCommand]
    private void NavigateChat()
    {
        CurrentPage = Chat;
        PageTitle = "Чат";
        ActivePage = "chat";
    }

    [RelayCommand]
    private void NavigateSystem()
    {
        CurrentPage = SystemPage;
        PageTitle = "Система";
        ActivePage = "system";
    }

    [RelayCommand]
    private void NavigateAutomation()
    {
        CurrentPage = AutomationPage;
        PageTitle = "Автоматизация";
        ActivePage = "automation";
    }

    [RelayCommand]
    private void NavigateAnalytics()
    {
        CurrentPage = AnalyticsPage;
        PageTitle = "Аналитика";
        ActivePage = "analytics";
    }

    [RelayCommand]
    private void NavigateSettings()
    {
        CurrentPage = SettingsPage;
        PageTitle = "Настройки";
        ActivePage = "settings";
    }

    [RelayCommand]
    private void NavigateProfile()
    {
        CurrentPage = ProfilePage;
        PageTitle = "Профиль";
        ActivePage = "profile";
    }

    [RelayCommand]
    private void ConfirmDialog()
    {
        DialogVisible = false;
        DialogService.Resolve(true);
    }

    [RelayCommand]
    private void CancelDialog()
    {
        DialogVisible = false;
        DialogService.Resolve(false);
    }
}
