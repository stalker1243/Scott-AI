using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Animation;
using Avalonia.Controls;
using Avalonia.Media.Transformation;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Лёгкая помощь для "въезжающих" анимаций появления без стороннего behaviors-пакета:
/// выставляем начальное состояние (прозрачно + сдвинуто вниз), вешаем Transitions на
/// Opacity/RenderTransform, затем поочерёдно, с небольшой задержкой на элемент,
/// включаем финальное состояние — Transitions сами плавно доигрывают переход.
/// </summary>
public static class UiAnimations
{
    private static void PrimeFadeIn(Control control)
    {
        control.Opacity = 0;
        control.RenderTransform = TransformOperations.Parse("translateY(14px)");
        control.Transitions = new Transitions
        {
            new DoubleTransition { Property = Visual.OpacityProperty, Duration = TimeSpan.FromMilliseconds(340) },
            new TransformOperationsTransition { Property = Visual.RenderTransformProperty, Duration = TimeSpan.FromMilliseconds(380) },
        };
    }

    private static void Reveal(Control control)
    {
        control.Opacity = 1;
        control.RenderTransform = TransformOperations.Identity;
    }

    /// <summary>Прогревает и поочерёдно показывает элементы с шагом delayMs — для "въезда" карточек при открытии страницы.</summary>
    public static async Task StaggerIn(IReadOnlyList<Control> controls, int delayMs = 70, int startDelayMs = 30)
    {
        foreach (var c in controls) PrimeFadeIn(c);
        await Task.Delay(startDelayMs);
        foreach (var c in controls)
        {
            Reveal(c);
            await Task.Delay(delayMs);
        }
    }

    /// <summary>
    /// Показать один элемент сразу, без очереди.
    ///
    /// Для чата: там задержка по индексу недопустима — новая реплика
    /// оказалась бы последней в списке и «доезжала» бы полсекунды, хотя ждут
    /// её именно сейчас.
    /// </summary>
    public static async Task RevealNow(Control control)
    {
        PrimeFadeIn(control);
        // Один кадр на то, чтобы начальное состояние успело примениться: без
        // паузы Transitions не с чего начинать переход, и элемент возникает
        // рывком, как будто анимации нет вовсе.
        await Task.Delay(16);
        Reveal(control);
    }

    /// <summary>Для элементов ItemsControl, подготавливаемых по одному (ContainerPrepared) — задержка
    /// считается от индекса элемента, а не от порядка вызова, максимум 12 шагов, чтобы длинные списки
    /// не "доезжали" по полминуты.</summary>
    public static async Task RevealDelayed(Control control, int index, int stepMs = 45)
    {
        PrimeFadeIn(control);
        await Task.Delay(System.Math.Min(index, 12) * stepMs);
        Reveal(control);
    }
}
