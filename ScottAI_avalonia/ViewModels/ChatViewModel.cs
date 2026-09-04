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

    /// <summary>Тихий режим (по умолчанию включён, как autoSpeak=false в Tauri-версии) — Scott выполняет
    /// действие молча, без озвучивания ответа через локальные колонки backend.</summary>
    [ObservableProperty]
    private bool _quietMode = true;

    [ObservableProperty]
    private string? _attachedImageName;

    [ObservableProperty]
    private string? _attachedFileName;

    public bool HasAttachment => AttachedImageName is not null || AttachedFileName is not null;

    public ChatViewModel(BackendClient client)
    {
        _client = client;
    }

    partial void OnAttachedImageNameChanged(string? value) => OnPropertyChanged(nameof(HasAttachment));
    partial void OnAttachedFileNameChanged(string? value) => OnPropertyChanged(nameof(HasAttachment));

    public void SetAttachedImage(string name)
    {
        AttachedImageName = name;
        AttachedFileName = null;
    }

    public void SetAttachedFile(string name)
    {
        AttachedFileName = name;
        AttachedImageName = null;
    }

    [RelayCommand]
    private void RemoveAttachment()
    {
        AttachedImageName = null;
        AttachedFileName = null;
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

    [RelayCommand]
    private async Task Send()
    {
        var text = Draft.Trim();
        var attachment = AttachedImageName ?? AttachedFileName;
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

        // Backend пока не умеет анализировать вложения (см. аналогичное честное
        // ограничение в Tauri-версии) — если прикреплён файл/картинка без текста,
        // просто сообщаем об этом и не дёргаем /ask.
        if (string.IsNullOrEmpty(text) && attachment is not null)
        {
            Messages.Add(new ChatMessage
            {
                Text = "Вложение получено — Scott пока не умеет анализировать файлы и изображения (появится, когда backend получит поддержку зрения/файлового анализа).",
                FromUser = false,
            });
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
