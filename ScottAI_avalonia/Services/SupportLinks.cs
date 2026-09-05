namespace ScottAI.Avalonia.Services;

/// <summary>
/// Куда человек может написать и где следить за новостями.
///
/// Здесь только адреса страниц — никаких токенов. Отправлять отчёт из
/// программы напрямую (через API бота) означало бы зашить в неё ключ доступа,
/// а его вытащит любой, кто откроет файл: чужой бот получил бы возможность
/// писать и читать от имени владельца. Поэтому программа лишь открывает чат,
/// а файл человек прикладывает сам — заодно видит, что именно отправляет.
/// </summary>
public static class SupportLinks
{
    /// <summary>Страница создания обращения с заполненным описанием.</summary>
    public const string GitHubIssues = "https://github.com/stalker1243/Scott-AI/issues/new";

    /// <summary>
    /// Канал Scott: новости, новые версии и — через прикреплённое обсуждение —
    /// место, куда можно написать и приложить архив.
    ///
    /// В самом канале подписчики писать не могут, но у него включены
    /// комментарии, а они ведут в связанную группу. Поэтому адрес один: с
    /// него человек попадает и к новостям, и к обсуждению.
    /// </summary>
    public const string TelegramChannel = "https://t.me/ScottAI_Channel";

    /// <summary>
    /// Куда писать о проблеме. Отдельный адрес понадобится, если однажды
    /// появится самостоятельная группа поддержки; пока это тот же канал с его
    /// обсуждением.
    /// </summary>
    public const string TelegramChat = TelegramChannel;

    public static bool HasChannel => !string.IsNullOrWhiteSpace(TelegramChannel);

    public static bool HasChat => !string.IsNullOrWhiteSpace(TelegramChat);
}
