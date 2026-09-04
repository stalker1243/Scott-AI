using System;
using System.Threading.Tasks;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Простой сервис модальных подтверждений — до этого kill-process и все "Удалить"
/// в списках выполнялись мгновенно, без единого предупреждения. MainWindowViewModel
/// подписывается на ConfirmRequested и показывает оверлей поверх всего окна; результат
/// возвращается через TaskCompletionSource, поэтому вызывающий код просто делает
/// `if (!await DialogService.ConfirmAsync(...)) return;`.
/// </summary>
public static class DialogService
{
    private static TaskCompletionSource<bool>? _pending;

    public static event Action<string, string, string, bool>? ConfirmRequested;

    public static Task<bool> ConfirmAsync(string title, string message, string confirmLabel = "Удалить", bool danger = true)
    {
        _pending?.TrySetResult(false);
        _pending = new TaskCompletionSource<bool>();
        ConfirmRequested?.Invoke(title, message, confirmLabel, danger);
        return _pending.Task;
    }

    public static void Resolve(bool result) => _pending?.TrySetResult(result);
}
