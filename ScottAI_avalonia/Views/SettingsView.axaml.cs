using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class SettingsView : UserControl
{
    public SettingsView()
    {
        InitializeComponent();
        ItemsStagger.Attach(VersionedItemsList);

        // Раздел появляется с коротким подъёмом, а не подменяется мгновенно.
        // При быстром переключении вкладок иначе не понять, сменилось ли
        // что-нибудь: заголовки разделов похожи, а содержимое ниже сгиба.
        DataContextChanged += (_, _) => WatchTabs();
        WatchTabs();
    }

    private ViewModels.SettingsViewModel? _watched;

    private void WatchTabs()
    {
        if (DataContext is not ViewModels.SettingsViewModel vm || ReferenceEquals(vm, _watched)) return;

        _watched = vm;
        vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName != nameof(ViewModels.SettingsViewModel.SettingsTab)) return;

            var section = vm.SettingsTab switch
            {
                "look" => (Control)LookSection,
                "voice" => VoiceSection,
                "ai" => AiSection,
                _ => OtherSection,
            };

            _ = UiAnimations.RevealNow(section);
        };
    }
}
