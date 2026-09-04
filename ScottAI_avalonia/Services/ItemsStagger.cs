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
}
