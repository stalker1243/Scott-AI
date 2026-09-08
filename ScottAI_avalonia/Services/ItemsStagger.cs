using Avalonia.Controls;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Подключает "въезд" элементов списка (fade + сдвиг вверх) к любому ItemsControl —
/// подписывается на ContainerPrepared и анимирует каждый вновь подготовленный контейнер
/// с задержкой по его индексу, используя тот же приём, что и UiAnimations.StaggerIn.
/// </summary>
public static class ItemsStagger
{
    public static void Attach(ItemsControl itemsControl)
    {
        itemsControl.ContainerPrepared += (_, e) =>
        {
            if (e.Container is Control control)
            {
                _ = UiAnimations.RevealDelayed(control, e.Index);
            }
        };
    }

    /// <summary>
    /// То же, но без нарастающей задержки: каждый элемент появляется сразу.
    ///
    /// Для списков, куда элементы добавляются по ходу дела, — прежде всего для
    /// чата. Лесенка хороша при открытии страницы, но новую реплику она
    /// заставила бы ждать тем дольше, чем длиннее разговор.
    /// </summary>
    public static void AttachInstant(ItemsControl items)
    {
        items.ContainerPrepared += (_, e) =>
        {
            if (e.Container is Control control) _ = UiAnimations.RevealNow(control);
        };
    }
}
