using System;
using ScottAI.Avalonia.Models;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Всплывающие уведомления об успехе/ошибке — раньше единственной обратной связью на
/// действия вроде удаления команды или завершения процесса были тихие изменения списка
/// или (иногда) плашка с ошибкой где-то на странице, которую легко не заметить.
/// MainWindowViewModel подписывается на ToastRequested и показывает уведомление в углу
/// окна поверх любой страницы.
/// </summary>
public static class ToastService
{
    public static event Action<ToastMessage>? ToastRequested;

    public static void Success(string text) => Show(text, ToastKind.Success);
    public static void Error(string text) => Show(text, ToastKind.Error);
    public static void Info(string text) => Show(text, ToastKind.Info);

    private static void Show(string text, ToastKind kind)
        => ToastRequested?.Invoke(new ToastMessage { Id = Guid.NewGuid().ToString("N"), Text = text, Kind = kind });
}
