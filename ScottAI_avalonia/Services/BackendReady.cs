using System;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Оповещение о том, что backend наконец ответил.
///
/// Страницы запрашивают данные при создании — то есть в первые секунды после
/// запуска, когда backend ещё поднимается (а при первом запуске он и вовсе
/// ждёт установки библиотек). Запросы уходили в пустоту, и человек видел
/// пустые списки, пока не нажимал «Обновить» руками.
///
/// Теперь каждая страница подписывается сюда и перезагружает себя сама, когда
/// отвечать стало кому.
/// </summary>
public static class BackendReady
{
    /// <summary>Отвечал ли backend хоть раз за эту сессию.</summary>
    public static bool IsReady { get; private set; }

    public static event Action? Ready;

    /// <summary>Сообщить, что backend поднялся. Повторные вызовы игнорируются:
    /// перезагружать страницы на каждую удачную проверку здоровья незачем.</summary>
    public static void Signal()
    {
        if (IsReady)
        {
            return;
        }

        IsReady = true;
        Ready?.Invoke();
    }

    /// <summary>
    /// Выполнить обновление сразу, если backend уже готов, и подписаться на
    /// будущее — если ещё нет.
    ///
    /// Порядок создания страниц и подъёма backend не гарантирован, поэтому
    /// каждая страница должна одинаково хорошо переживать оба случая.
    /// </summary>
    public static void WhenReady(Action refresh)
    {
        if (IsReady)
        {
            refresh();
            return;
        }

        Ready += refresh;
    }
}
