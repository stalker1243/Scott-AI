using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class ChatViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<ChatMessage> Messages { get; } = new();

    /// <summary>История отправленных промтов за сессию (новые сверху) — клик по элементу подставляет его в поле ввода.</summary>
    public ObservableCollection<string> PromptHistory { get; } = new();

    [ObservableProperty]
    private string _draft = "";

    [ObservableProperty]
    private bool _sending;

    [ObservableProperty]
    private bool _showHistory;

    /// <summary>
    /// Зачитывать ли вслух ответы, полученные в переписке (по умолчанию — нет,
    /// как autoSpeak=false в Tauri-версии).
    ///
    /// Не путать с общим молчанием: то отключает голос Scott везде, включая
    /// ответы на голосовые команды, и живёт в настройках звука.
    /// </summary>
    [ObservableProperty]
    private bool _quietMode = true;

    /// <summary>
    /// Включено ли общее молчание.
    ///
    /// Пока оно включено, выбор в чате ничего не решает: голос отбрасывается
    /// в проигрывателе, что бы чат ни просил. Кнопка должна об этом сказать, а
    /// не обещать озвучку, которой не будет.
    /// </summary>
    [ObservableProperty]
    private bool _globallyMuted;

    [ObservableProperty]
    private string? _attachedImageName;

    [ObservableProperty]
    private string? _attachedFileName;

    /// <summary>
    /// Путь к прикреплённому файлу.
    ///
    /// Раньше запоминалось одно имя, и файл никуда не уходил: вопрос
    /// отправлялся обычным запросом, где вложения нет вовсе. Отсюда и брался
    /// ответ «Scott не умеет анализировать файлы» — проверить это было
    /// невозможно, файл до него не доходил.
    /// </summary>
    [ObservableProperty]
    private string? _attachedPath;

    public bool HasAttachment => AttachedImageName is not null || AttachedFileName is not null;

    public ChatViewModel(BackendClient client)
    {
        _client = client;
    }

    partial void OnAttachedImageNameChanged(string? value) => OnPropertyChanged(nameof(HasAttachment));
    partial void OnAttachedFileNameChanged(string? value) => OnPropertyChanged(nameof(HasAttachment));

    public void SetAttachedImage(string name, string path)
    {
        AttachedImageName = name;
        AttachedFileName = null;
        AttachedPath = path;
    }

    public void SetAttachedFile(string name, string path)
    {
        AttachedFileName = name;
        AttachedImageName = null;
        AttachedPath = path;
    }

    [RelayCommand]
    private void RemoveAttachment()
    {
        AttachedImageName = null;
        AttachedFileName = null;
        AttachedPath = null;
    }

    [RelayCommand]
    private void ToggleHistory() => ShowHistory = !ShowHistory;

    [RelayCommand]
    private void ToggleQuietMode() => QuietMode = !QuietMode;

    [RelayCommand]
    private void SelectHistoryPrompt(string prompt)
    {
        Draft = prompt;
        ShowHistory = false;
    }

    [RelayCommand]
    private void NewChat()
    {
        Messages.Clear();
        RemoveAttachment();
        Draft = "";
    }

    /// <summary>
    /// Забыть разговор целиком — и на экране, и в памяти Scott.
    ///
    /// «Новый чат» очищает только окно: ассистент продолжает помнить прежнюю
    /// беседу, потому что память живёт на стороне backend и переживает даже
    /// перезапуск. Здесь стирается и она.
    /// </summary>
    [RelayCommand]
    private async Task ClearHistory()
    {
        var confirmed = await DialogService.ConfirmAsync(
            "Удалить историю разговоров?",
            "Scott забудет всё, о чём вы говорили: и переписку в этом окне, и то, " +
            "что он держал в памяти. Отменить это будет нельзя.",
            "Удалить");

        if (!confirmed)
        {
            return;
        }

        Messages.Clear();
        PromptHistory.Clear();
        RemoveAttachment();
        Draft = "";

        var forgotten = await _client.ClearAiMemoryAsync();
        ToastService.Success(forgotten
            ? "История удалена — Scott забыл разговор"
            : "Окно очищено, но память Scott стереть не вышло: backend не ответил");
    }

    /// <summary>
    /// Отправить вопрос вместе с файлом.
    ///
    /// Ответ может прийти с примечанием — например, что снимок уменьшен или
    /// что из длинного документа взята только часть. Молчать об этом нельзя:
    /// человек решит, что ответ обо всём документе.
    /// </summary>
    private async Task SendWithAttachment(string path, string question)
    {
        Sending = true;
        try
        {
            var (success, answer, note) = await _client.AskAboutFileAsync(path, question);

            if (!string.IsNullOrEmpty(note))
            {
                answer = $"{answer}\n\n({note})";
            }

            Messages.Add(new ChatMessage
            {
                Text = string.IsNullOrEmpty(answer) ? "Scott не дал ответа." : answer,
                FromUser = false,
            });

            if (success && !QuietMode)
            {
                await _client.SpeakAsync(answer);
            }
        }
        finally
        {
            Sending = false;
        }
    }

    [RelayCommand]
    private async Task Send()
    {
        var text = Draft.Trim();
        var attachment = AttachedImageName ?? AttachedFileName;
        var path = AttachedPath;

        if (string.IsNullOrEmpty(text) && attachment is null) return;
        if (Sending) return;

        Messages.Add(new ChatMessage { Text = text, FromUser = true, AttachmentName = attachment });
        Draft = "";
        RemoveAttachment();

        if (!string.IsNullOrEmpty(text))
        {
            PromptHistory.Remove(text);
            PromptHistory.Insert(0, text);
        }

        // Файл идёт своей дорогой: он уходит на backend целиком, а вопрос —
        // вместе с ним. Без вопроса тоже можно: перетаскивая снимок молча,
        // человек обычно хочет услышать, что там вообще.
        if (path is not null)
        {
            await SendWithAttachment(path, text);
            return;
        }

        Sending = true;
        try
        {
            var answer = await _client.AskAsync(text, QuietMode);
            answer = string.IsNullOrEmpty(answer) ? "Scott не дал ответа." : answer;
            Messages.Add(new ChatMessage { Text = answer, FromUser = false });

            if (!QuietMode)
            {
                _ = _client.SpeakAsync(answer);
            }
        }
        catch (System.Exception ex)
        {
            Messages.Add(new ChatMessage { Text = $"Не удалось получить ответ от Scott: {ex.Message}", FromUser = false });
        }
        finally
        {
            Sending = false;
        }
    }
}
