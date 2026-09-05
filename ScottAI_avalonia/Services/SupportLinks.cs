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
    /// Канал с новостями и новыми версиями. Читать — да, писать — нет:
    /// подписчики канала не могут отправлять сообщения, поэтому для отчётов он
    /// не годится и в интерфейсе назван честно.
    /// </summary>
    public const string TelegramChannel = "https://t.me/ScottAI_Channel";

    /// <summary>
    /// Чат, куда можно написать и приложить архив. Это должна быть ГРУППА или
    /// обсуждение канала — в самом канале написать нельзя. Пока адрес пуст,
    /// кнопки нет: вести человека туда, где он не сможет ответить, хуже, чем
    /// не показывать её вовсе.
    /// </summary>
    public const string TelegramChat = "";

    public static bool HasChannel => !string.IsNullOrWhiteSpace(TelegramChannel);

    public static bool HasChat => !string.IsNullOrWhiteSpace(TelegramChat);
}
