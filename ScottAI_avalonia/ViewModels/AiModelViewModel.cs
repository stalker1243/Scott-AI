using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Какая модель отвечает на вопросы и каким ключом.
///
/// Была вкладкой внутри Настроек, третьей по счёту. Между тем это первое, куда
/// человек идёт на новой машине: без ключа Scott выполняет команды, но на
/// вопросы не отвечает вовсе, — и найти это место надо сразу, а не перебирая
/// вкладки в разделе с громкостью и микрофоном.
/// </summary>
public partial class AiModelViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<AiProvider> Providers { get; } = new();

    [ObservableProperty] private AiProvider? _selectedProvider;
    [ObservableProperty] private string? _selectedModel;
    [ObservableProperty] private string _apiKeyInput = "";

    /// <summary>Вводить название модели руками вместо выбора из списка.</summary>
    [ObservableProperty] private bool _useCustomModel;

    /// <summary>
    /// Название модели, введённое вручную.
    ///
    /// Новые модели выходят чаще, чем обновляется Scott, и ждать выпуска ради
    /// свежей — глупо.
    /// </summary>
    [ObservableProperty] private string _customModel = "";

    /// <summary>Кто отвечает прямо сейчас — по словам backend, а не по выбору на странице.</summary>
    [ObservableProperty] private string? _activeProvider;
    [ObservableProperty] private string _activeModel = "";

    [ObservableProperty] private bool _applying;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private string? _status;

    /// <summary>Подключён ли вообще кто-нибудь. От этого зависит, отвечает ли Scott на вопросы.</summary>
    public bool Connected => !string.IsNullOrWhiteSpace(ActiveProvider);

    partial void OnActiveProviderChanged(string? value) => OnPropertyChanged(nameof(Connected));

    public AiModelViewModel(BackendClient client)
    {
        _client = client;

        _ = Load();

        // Первый запрос уходит, пока backend ещё поднимается: список
        // провайдеров остался бы пустым до перезапуска лаунчера.
        BackendReady.WhenReady(() => _ = Load());
    }

    [RelayCommand]
    private async Task Load()
    {
        Error = null;

        try
        {
            var (providers, activeProvider, activeModel) = await _client.ListAiProvidersAsync();

            Providers.Clear();
            foreach (var p in providers)
            {
                Providers.Add(p);
            }

            ActiveProvider = activeProvider;
            ActiveModel = activeModel;

            SelectedProvider = Providers.Count > 0
                ? (Providers.FirstOrDefault(p => p.Id == activeProvider) ?? Providers[0])
                : null;

            SelectedModel = !string.IsNullOrWhiteSpace(activeModel)
                ? activeModel
                : SelectedProvider?.Models.FirstOrDefault()?.Id;
        }
        catch (System.Exception ex)
        {
            Error = ex.Message;
        }
    }

    [RelayCommand]
    private void SetSelectedProvider(AiProvider provider) => SelectedProvider = provider;

    partial void OnSelectedProviderChanged(AiProvider? value)
    {
        // Ключ относится к провайдеру: оставленный при переключении, он ушёл бы
        // не туда.
        ApiKeyInput = "";

        SelectedModel = value?.Id == ActiveProvider
            ? ActiveModel
            : value?.Models.Count > 0 ? value.Models[0].Id : null;
    }

    [RelayCommand]
    private async Task Apply()
    {
        // Молчаливый выход отсюда — худшее, что можно сделать с человеком,
        // который только что ввёл ключ: кнопка нажата, и ничего не произошло.
        if (SelectedProvider is null)
        {
            Error = "Выберите провайдера ИИ — например, Groq";
            ToastService.Error(Error);
            return;
        }

        // Введённая руками модель важнее выбранной в списке: человек указал её
        // намеренно.
        var model = UseCustomModel && !string.IsNullOrWhiteSpace(CustomModel)
            ? CustomModel.Trim()
            : SelectedModel;

        if (string.IsNullOrWhiteSpace(model))
        {
            // Модель почти всегда можно взять сама собой: у провайдера есть
            // список, и первая в нём — разумный выбор по умолчанию.
            model = SelectedProvider.Models.FirstOrDefault()?.Id;
        }

        SelectedModel = model;

        if (string.IsNullOrWhiteSpace(SelectedModel))
        {
            Error = "У этого провайдера не нашлось моделей — выберите другого";
            ToastService.Error(Error);
            return;
        }

        Applying = true;
        Error = null;
        Status = null;

        try
        {
            var (success, message) = await _client.ConfigureAiAsync(
                SelectedProvider.Id, SelectedModel,
                string.IsNullOrWhiteSpace(ApiKeyInput) ? null : ApiKeyInput.Trim());

            if (!success)
            {
                Error = message;
                ToastService.Error(message);
                return;
            }

            // Ключ стираем сразу после успеха: он больше не нужен, а лежать на
            // экране ему незачем.
            ApiKeyInput = "";
            Status = message;
            ToastService.Success($"Модель ИИ переключена на {SelectedProvider.Id}");

            await Load();
        }
        catch (System.Exception ex)
        {
            // Недоступный backend — самый частый случай на новой машине: он ещё
            // поднимается, а человек уже ввёл ключ и нажал «Применить». Без
            // этой ветки исключение уходило в пустоту, и кнопка выглядела
            // сломанной — нажал, и ничего.
            Error = $"Не удалось применить: {ex.Message}";
            ToastService.Error(Error);
        }
        finally
        {
            Applying = false;
        }
    }
}
