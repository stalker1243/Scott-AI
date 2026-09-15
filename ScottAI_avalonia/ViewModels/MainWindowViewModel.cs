using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Material.Icons;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class MainWindowViewModel : ViewModelBase
{
    private readonly BackendClient _client = new();
    private readonly BackendLauncher _backendLauncher = new();

    /// <summary>Мастер первого запуска — виден, только пока машина не готова.</summary>
    public FirstRunViewModel FirstRun { get; } = new();

    /// <summary>Полоска «вышла новая версия» — показывается один раз при запуске.</summary>
    /// <summary>
    /// Адрес backend — один на всех, кто к нему обращается.
    ///
    /// Записанный в двух местах, он однажды разойдётся, и тогда одна половина
    /// программы будет разговаривать с backend, а другая молча нет.
    /// </summary>
    public const string BackendBase = "http://127.0.0.1:8000";

    public UpdateViewModel Update { get; } = new(BackendBase);

    public AboutViewModel About { get; } = new(BackendBase);
    private readonly DispatcherTimer _healthTimer;
    private bool _everOnline;

    /// <summary>Что происходит с backend, пока он поднимается.</summary>
    [ObservableProperty] private string _backendHint = "";

    [ObservableProperty]
    private ViewModelBase _currentPage;

    [ObservableProperty]
    private string _pageTitle = "Главная";

    /// <summary>
    /// Пояснение под названием раздела.
    ///
    /// Не украшение: по названиям «Память», «Действия», «Диагностика» не
    /// угадать, что внутри, а заходить в каждый раздел, чтобы выяснить, —
    /// плохой способ знакомиться с программой. Одна строка снимает вопрос
    /// раньше, чем он возникнет.
    /// </summary>
    [ObservableProperty]
    private string _pageSubtitle = "Scott готов к работе";

    [ObservableProperty]
    private string _activePage = "home";

    // ==================== Список разделов ====================
    //
    // Разделов шестнадцать. Шестнадцать строк подряд человек не читает — он их
    // просматривает и не находит нужную, потому что глазу не за что зацепиться.
    // Поэтому они собраны в пять групп, каждую можно свернуть, а весь список —
    // сжать до иконок, когда нужно место для самой страницы.
    //
    // Заданы данными, а не разметкой: прежде каждый раздел был расписан в XAML
    // отдельно, по шесть строк, и добавить к ним сворачивание значило бы
    // править шестнадцать мест и в одном непременно ошибиться.

    public IReadOnlyList<NavSection> Sections { get; }

    /// <summary>
    /// Сжат ли список до иконок.
    ///
    /// Запоминается между запусками: человек, которому нужно место, хочет его
    /// всегда, а не до следующего перезапуска.
    /// </summary>
    [ObservableProperty]
    private bool _sidebarCollapsed = SettingsStore.Current.SidebarCollapsed;

    [ObservableProperty]
    private string _backendStatus = "starting"; // starting | online | offline

    [ObservableProperty]
    private bool _isClassicStyle = ThemeService.CurrentStyle == AppStyle.Classic;

    /// <summary>Логотип в сайдбаре — та же иконка, что у окна и в трее.</summary>
    [ObservableProperty]
    private global::Avalonia.Media.Imaging.Bitmap? _logo = AppIconService.LoadLogo();

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

    /// <summary>
    /// Молчит ли Scott. Переключатель стоит в шапке, а не только в настройках:
    /// просьба замолчать возникает внезапно — начался звонок, проснулся
    /// человек рядом, — и искать её в разделах некогда.
    /// </summary>
    [ObservableProperty]
    private bool _quietMode;

    /// <summary>
    /// Пока состояние читается с backend, обратно его слать не нужно: иначе
    /// чтение выглядело бы как нажатие переключателя.
    /// </summary>
    private bool _quietLoading;

    public ObservableCollection<ToastMessage> Toasts { get; } = new();

    public HomeViewModel Home { get; }
    public ChatViewModel Chat { get; }
    public SystemViewModel SystemPage { get; }
    public ProtocolsViewModel ProtocolsPage { get; }
    public AnalyticsViewModel AnalyticsPage { get; }
    public SettingsViewModel SettingsPage { get; }
    public ProfileViewModel ProfilePage { get; }

    /// <summary>
    /// Выбор акцентного цвета, доступный с любой страницы.
    ///
    /// Живёт в модели окна, а не страницы: панель висит поверх содержимого и
    /// не должна пропадать при переходе между разделами.
    /// </summary>
    public AccentPickerViewModel Accent { get; } = new();

    public AppearanceViewModel Appearance { get; } = new();

    public AiModelViewModel AiModel { get; }

    public DiagnosticsViewModel Diagnostics { get; }

    public MemoryViewModel Memory { get; }

    public ProjectsViewModel ProjectsPage { get; }

    public ActionsViewModel Actions { get; }

    public RemoteViewModel Remote { get; }
    public LogsViewModel LogsPage { get; }

    public MainWindowViewModel()
    {
        Sections = СобратьРазделы();
        ОтметитьАктивный();

        AiModel = new AiModelViewModel(_client);
        Diagnostics = new DiagnosticsViewModel(_client);
        Memory = new MemoryViewModel(_client);
        ProjectsPage = new ProjectsViewModel(_client);

        // Примеры из «Действий» уходят в чат: человек должен увидеть, что
        // Scott ответил, а не гадать, сработало ли.
        Actions = new ActionsViewModel(_client, OpenChatWith);
        Remote = new RemoteViewModel(_client);
        ProfilePage = new ProfileViewModel(_client);
        Home = new HomeViewModel(_client, OpenChatWith);
        Chat = new ChatViewModel(_client);
        SystemPage = new SystemViewModel(_client);
        LogsPage = new LogsViewModel(_client);
        ProtocolsPage = new ProtocolsViewModel(_client);
        AnalyticsPage = new AnalyticsViewModel(_client);
        // Сброс настроек делается в Настройках, а оформление живёт в своём
        // разделе: без этой связи его переключатели после сброса показывали бы
        // прежнее до перезапуска лаунчера.
        SettingsPage = new SettingsViewModel(_client, Appearance.ReloadFromSettings);

        // Тихий режим переключается из двух мест — кнопкой в шапке и на
        // странице настроек. Связь нужна в обе стороны, иначе переключатель и
        // кнопка показывают разное, и человек не понимает, чему верить.
        SettingsPage.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName != nameof(SettingsViewModel.QuietMode)) return;
            if (QuietMode == SettingsPage.QuietMode) return;

            // Настройки уже сообщили backend сами — здесь только приводим в
            // соответствие кнопку, не отправляя то же самое второй раз.
            _quietLoading = true;
            QuietMode = SettingsPage.QuietMode;
            Chat.GloballyMuted = SettingsPage.QuietMode;
            _quietLoading = false;
        };
        _currentPage = Home;

        ThemeService.StyleApplied += style => IsClassicStyle = style == AppStyle.Classic;

        // Смена иконки в Настройках должна быть видна сразу, без перезапуска.
        AppIconService.IconChanged += variant => Logo = AppIconService.LoadLogo(variant);

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
        _ = StartBackendAsync();
    }

    /// <summary>
    /// Поднять backend, если он ещё не работает.
    ///
    /// Раньше лаунчер только проверял состояние и при отсутствии backend вечно
    /// показывал «offline» — человек, открывший программу впервые, решал, что
    /// она сломана, и никакой подсказки не получал. Теперь backend запускается
    /// сам, а если запустить не удалось, причина видна словами.
    /// </summary>
    private async Task StartBackendAsync()
    {
        // Сначала — готова ли машина вообще. Поднимать backend, когда не
        // установлены torch и модели речи, бессмысленно: он упадёт на импорте,
        // а человек увидит «offline» без объяснения. На готовой машине
        // проверка занимает секунду и мастер не показывается.
        BackendHint = "проверяю, всё ли установлено…";
        if (!await FirstRun.EnsureReadyAsync())
        {
            BackendHint = "подготовка не завершена";
            return;
        }

        BackendHint = "проверяю Scott…";
        var (success, message) = await _backendLauncher.EnsureRunningAsync(_client);
        BackendHint = success ? "" : message;

        if (!success)
        {
            ToastService.Error(message);
        }

        await CheckHealthAsync();

        // Страницы, созданные до того как backend ответил, ждут этого сигнала:
        // без него человек видел пустые списки, пока не нажимал «Обновить».
        if (success)
        {
            BackendReady.Signal();
            _ = LoadQuietModeAsync();
        }

        // Обновления проверяются последними и молча: если backend не поднялся
        // или GitHub недоступен, человек об этом не узнает — беспокоить его
        // ради несостоявшейся проверки незачем.
        if (success)
        {
            await Update.CheckAsync();
        }
    }

    /// <summary>
    /// Остановить backend при закрытии окна — но только если запускали его мы.
    ///
    /// Процесс, поднятый человеком в терминале, остаётся жить: он мог оставить
    /// его нарочно, чтобы читать логи.
    /// </summary>
    public void ShutdownBackend() => _backendLauncher.StopIfOurs();

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

    /// <summary>Замолчать или заговорить снова — одним нажатием из шапки.</summary>
    [RelayCommand]
    private void ToggleQuiet() => QuietMode = !QuietMode;

    partial void OnQuietModeChanged(bool value)
    {
        if (_quietLoading) return;

        _ = _client.SetQuietAsync(value);

        // Настройки открыты на той же странице, что и переключатель в шапке, —
        // и они не должны показывать противоположное.
        SettingsPage.QuietMode = value;

        // У чата свой выбор — зачитывать ли ответы в переписке. Пока Scott
        // молчит совсем, этот выбор ничего не решает, и кнопка должна об этом
        // сказать, а не обещать озвучку, которой не будет.
        Chat.GloballyMuted = value;
    }

    /// <summary>
    /// Узнать у backend, включён ли тихий режим.
    ///
    /// Настройка переживает перезапуск, поэтому окно обязано открыться в том
    /// же состоянии, в каком его закрыли: иначе человек, выключивший звук
    /// вечером, утром получит говорящего Scott.
    /// </summary>
    private async Task LoadQuietModeAsync()
    {
        try
        {
            var state = await _client.GetAudioAsync();
            if (state is null) return;

            _quietLoading = true;
            QuietMode = state.Settings.Quiet;
            SettingsPage.QuietMode = state.Settings.Quiet;
            Chat.GloballyMuted = state.Settings.Quiet;
        }
        catch
        {
            // Не отвечает backend — оставляем переключатель как есть.
        }
        finally
        {
            _quietLoading = false;
        }
    }

    /// <summary>
    /// Разделы по группам — в том порядке, в каком ими пользуются.
    ///
    /// Группировка не декоративная: «Память» и «Персонализация» — про то, что
    /// Scott знает о человеке, «Система» и «Удалённо» — про машину, а
    /// «Диагностика» и «Логи» открываются, только когда что-то сломалось.
    /// Свалить их в один список значит заставить искать нужное перебором.
    /// </summary>
    private IReadOnlyList<NavSection> СобратьРазделы()
    {
        var свёрнутые = SettingsStore.Current.CollapsedGroups ?? Array.Empty<string>();

        var группы = new List<NavSection>
        {
            new()
            {
                Title = "Начало",
                Items = new List<NavItem>
                {
                    new() { Page = "home", Label = "Главная", Icon = MaterialIconKind.Home },
                    new() { Page = "chat", Label = "Чат", Icon = MaterialIconKind.ChatOutline },
                },
            },
            new()
            {
                Title = "Scott",
                Items = new List<NavItem>
                {
                    new() { Page = "memory", Label = "Память", Icon = MaterialIconKind.HeadCogOutline },
                    new() { Page = "profile", Label = "Персонализация", Icon = MaterialIconKind.AccountHeartOutline },
                    new() { Page = "projects", Label = "Проекты", Icon = MaterialIconKind.FolderMultipleOutline },
                    new() { Page = "protocols", Label = "Протоколы", Icon = MaterialIconKind.FormatListNumbered },
                    new() { Page = "actions", Label = "Действия", Icon = MaterialIconKind.LightningBoltOutline },
                },
            },
            new()
            {
                Title = "Компьютер",
                Items = new List<NavItem>
                {
                    new() { Page = "system", Label = "Система", Icon = MaterialIconKind.Cpu64Bit },
                    new() { Page = "aimodel", Label = "Модель", Icon = MaterialIconKind.RobotOutline },
                    new() { Page = "remote", Label = "Удалённо", Icon = MaterialIconKind.CellphoneLink },
                },
            },
            new()
            {
                Title = "Оформление",
                Items = new List<NavItem>
                {
                    new() { Page = "appearance", Label = "Внешний вид", Icon = MaterialIconKind.PaletteOutline },
                    new() { Page = "settings", Label = "Настройки", Icon = MaterialIconKind.CogOutline },
                },
            },
            new()
            {
                Title = "Служебное",
                Items = new List<NavItem>
                {
                    new() { Page = "diagnostics", Label = "Диагностика", Icon = MaterialIconKind.Stethoscope },
                    new() { Page = "logs", Label = "Логи", Icon = MaterialIconKind.TextBoxSearchOutline },
                    new() { Page = "analytics", Label = "Аналитика", Icon = MaterialIconKind.ChartBar },
                    new() { Page = "about", Label = "О ScottAI", Icon = MaterialIconKind.InformationOutline },
                },
            },
        };

        foreach (var группа in группы)
        {
            группа.Expanded = !Array.Exists(свёрнутые, имя => имя == группа.Title);
            группа.ItemsVisible = SidebarCollapsed || группа.Expanded;
        }

        return группы;
    }

    /// <summary>
    /// Открыть раздел по имени.
    ///
    /// Одна команда на все шестнадцать: в шаблоне строки нельзя привязаться к
    /// своей команде у каждого раздела, да и заводить шестнадцать одинаковых
    /// обёрток незачем — прежние Navigate* остаются для тех, кто зовёт их по
    /// имени (главная страница, трей, мастер первого запуска).
    /// </summary>
    [RelayCommand]
    private void Go(string? page)
    {
        switch (page)
        {
            case "home": NavigateHome(); break;
            case "chat": NavigateChat(); break;
            case "system": NavigateSystem(); break;
            case "actions": NavigateActions(); break;
            case "protocols": NavigateProtocols(); break;
            case "analytics": NavigateAnalytics(); break;
            case "aimodel": NavigateAiModel(); break;
            case "appearance": NavigateAppearance(); break;
            case "settings": NavigateSettings(); break;
            case "projects": NavigateProjects(); break;
            case "memory": NavigateMemory(); break;
            case "profile": NavigateProfile(); break;
            case "about": NavigateAbout(); break;
            case "remote": NavigateRemote(); break;
            case "diagnostics": NavigateDiagnostics(); break;
            case "logs": NavigateLogs(); break;
        }
    }

    /// <summary>
    /// Сжать список до иконок или вернуть подписи.
    ///
    /// В сжатом виде группы не сворачиваются: подписей нет, заголовок группы
    /// скрыт, и часть иконок исчезала бы без видимой причины.
    /// </summary>
    [RelayCommand]
    private void ToggleSidebar()
    {
        SidebarCollapsed = !SidebarCollapsed;

        SettingsStore.Current.SidebarCollapsed = SidebarCollapsed;
        SettingsStore.SaveCurrent();
    }

    [RelayCommand]
    private void ToggleSection(NavSection? группа)
    {
        if (группа is null || SidebarCollapsed)
        {
            return;
        }

        группа.Expanded = !группа.Expanded;
        группа.ItemsVisible = группа.Expanded;

        ЗапомнитьСвёрнутые();
    }

    private void ЗапомнитьСвёрнутые()
    {
        var свёрнутые = new List<string>();

        foreach (var группа in Sections)
        {
            if (!группа.Expanded)
            {
                свёрнутые.Add(группа.Title);
            }
        }

        SettingsStore.Current.CollapsedGroups = свёрнутые.ToArray();
        SettingsStore.SaveCurrent();
    }

    partial void OnSidebarCollapsedChanged(bool value)
    {
        foreach (var группа in Sections)
        {
            группа.ItemsVisible = value || группа.Expanded;
        }
    }

    /// <summary>
    /// Отметить открытый раздел и показать его, даже если группа свёрнута.
    ///
    /// Иначе человек оказывается на странице, которой нет в списке, — и не
    /// понимает, где находится.
    /// </summary>
    partial void OnActivePageChanged(string value) => ОтметитьАктивный();

    private void ОтметитьАктивный()
    {
        foreach (var группа in Sections)
        {
            foreach (var раздел in группа.Items)
            {
                раздел.Active = раздел.Page == ActivePage;

                if (раздел.Active && !группа.Expanded)
                {
                    группа.Expanded = true;
                    группа.ItemsVisible = true;
                    ЗапомнитьСвёрнутые();
                }
            }
        }
    }

    [RelayCommand]
    private void NavigateHome()
    {
        CurrentPage = Home;
        PageTitle = "Главная";
        PageSubtitle = "Scott готов к работе";
        ActivePage = "home";
    }

    /// <summary>
    /// Открыть чат, а если задан вопрос — сразу его и задать.
    ///
    /// Нужно главной странице: там есть поле ввода и примеры команд, по
    /// которым можно нажать. Без этого вопрос пришлось бы набирать заново уже
    /// в чате — то есть первый экран показывал бы, что Scott умеет, но сделать
    /// с этим ничего не давал.
    /// </summary>
    private void OpenChatWith(string вопрос)
    {
        NavigateChat();

        if (string.IsNullOrWhiteSpace(вопрос))
        {
            return;
        }

        Chat.Draft = вопрос;
        Chat.SendCommand.Execute(null);
    }

    [RelayCommand]
    private void NavigateChat()
    {
        CurrentPage = Chat;
        PageTitle = "Чат";
        PageSubtitle = "Разговор со Scott";
        ActivePage = "chat";
    }

    [RelayCommand]
    private void NavigateSystem()
    {
        CurrentPage = SystemPage;
        PageTitle = "Система";
        PageSubtitle = "Мониторинг и управление";
        ActivePage = "system";
    }

    [RelayCommand]
    private void NavigateProtocols()
    {
        CurrentPage = ProtocolsPage;
        PageTitle = "Протоколы";
        PageSubtitle = "Последовательности команд по одному слову";
        ActivePage = "protocols";

        // Список перечитывается при каждом заходе: протокол можно завести и
        // голосом, и из другого места — иначе он не появился бы в списке до
        // перезапуска лаунчера.
        ProtocolsPage.RefreshCommand.Execute(null);
    }

    [RelayCommand]
    private void NavigateAnalytics()
    {
        CurrentPage = AnalyticsPage;
        PageTitle = "Аналитика";
        PageSubtitle = "Чем Scott занимался";
        ActivePage = "analytics";
    }

    [RelayCommand]
    private void NavigateSettings()
    {
        CurrentPage = SettingsPage;
        PageTitle = "Настройки";
        PageSubtitle = "Основные параметры приложения";
        ActivePage = "settings";
    }

    [RelayCommand]
    private void NavigateProfile()
    {
        CurrentPage = ProfilePage;
        PageTitle = "Персонализация";
        PageSubtitle = "Как Scott будет с вами говорить";
        ActivePage = "profile";
    }

    [RelayCommand]
    private void NavigateAiModel()
    {
        CurrentPage = AiModel;
        PageTitle = "Модель";
        PageSubtitle = "Кто отвечает на вопросы и каким ключом";
        ActivePage = "aimodel";
    }

    [RelayCommand]
    private void NavigateAppearance()
    {
        CurrentPage = Appearance;
        PageTitle = "Внешний вид";
        PageSubtitle = "Стиль окна, тема, цвет и значок";
        ActivePage = "appearance";

        // Цвет мог смениться из панели в углу окна, пока раздел был закрыт:
        // отметка на странице врала бы о том, какой из них сейчас в деле.
        Appearance.SyncAccentSelection();
    }

    [RelayCommand]
    private void NavigateRemote()
    {
        CurrentPage = Remote;
        PageTitle = "Удалённо";
        PageSubtitle = "Кто может командовать Scott издалека";
        ActivePage = "remote";

        // Перечитываем при заходе: привязка происходит на телефоне, и список
        // устройств меняется без участия этого окна.
        _ = Remote.Refresh();
    }

    [RelayCommand]
    private void NavigateActions()
    {
        CurrentPage = Actions;
        PageTitle = "Действия";
        PageSubtitle = "Что Scott умеет и как его об этом просить";
        ActivePage = "actions";

        // Перечитываем при заходе: доступность умений меняется — микрофон
        // отключают, ключ вводят, — и список, собранный при запуске, соврал бы.
        _ = Actions.Refresh();
    }

    [RelayCommand]
    private void NavigateProjects()
    {
        CurrentPage = ProjectsPage;
        PageTitle = "Проекты";
        PageSubtitle = "Над чем вы работаете";
        ActivePage = "projects";

        // Перечитываем при заходе: текущий проект мог смениться от фразы
        // «открой проект такой-то», сказанной в разговоре.
        _ = ProjectsPage.Refresh();
    }

    [RelayCommand]
    private void NavigateMemory()
    {
        CurrentPage = Memory;
        PageTitle = "Память";
        PageSubtitle = "Что Scott о вас помнит";
        ActivePage = "memory";

        // Перечитываем при заходе: запомнить можно и голосом, посреди
        // разговора, — и список, собранный при запуске, этого не покажет.
        _ = Memory.Refresh();
    }

    [RelayCommand]
    private void NavigateDiagnostics()
    {
        CurrentPage = Diagnostics;
        PageTitle = "Диагностика";
        PageSubtitle = "Что работает, а что нет";
        ActivePage = "diagnostics";

        // Перепроверяем при каждом заходе: микрофон отключают, ключ вводят,
        // интернет пропадает — снимок получасовой давности здесь бесполезен.
        _ = Diagnostics.Refresh();
    }

    [RelayCommand]
    private void NavigateAbout()
    {
        CurrentPage = About;
        PageTitle = "О ScottAI";
        PageSubtitle = "Версия, обновления и сведения о программе";
        ActivePage = "about";
    }

    [RelayCommand]
    private void NavigateLogs()
    {
        CurrentPage = LogsPage;
        PageTitle = "Логи";
        PageSubtitle = "Что происходило под капотом";
        ActivePage = "logs";
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
