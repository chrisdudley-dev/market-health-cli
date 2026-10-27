# Compose design system

Tokens live in MarketTheme.kt and shared patterns in MarketComponents.kt.

Spacing uses 4/8/12/16/24/32 dp steps. Small controls use 8/12 dp corners, content surfaces 20 dp and sheets 28 dp. Cards use surface hierarchy rather than heavy shadows; elevation is reserved for overlays and transient controls.

Typography uses the platform sans-serif family with a 32 sp display, 26/22 sp headings, 20/16 sp titles and 16/14/12 sp body sizes. Numeric values have a clear hierarchy and wrap/reflow with font scale. Technical values use monospace without changing their precision.

Light/dark palettes define background, surface, text, outline and semantic action colors centrally. System mode follows Android's appearance. BUY/HOLD/WATCH/SELL/rescue/data-error treatments also have exact text and distinct icons; color never carries the meaning alone.

Four score cells use numeric labels and decorative bars on the existing score scale. They do not label the values as percentages. Large fonts and narrow constraints use two columns; detailed audit preserves the original numeric values. Charts use point shapes and text legends in addition to color.

Interactive rows/buttons/icons have at least 48 dp targets. Switch rows expose one toggleable semantic target with a decorative child switch. Headings, field labels, current selection, refresh state and chart tables remain accessible. See the [official Compose accessibility defaults](https://developer.android.com/develop/ui/compose/accessibility/api-defaults).

Native [pull-to-refresh](https://developer.android.com/develop/ui/compose/components/pull-to-refresh) invokes the existing refresh action. Busy-state guards and disabled controls prevent overlapping user requests. No shimmer, perpetual decorative animation or custom financial animation is needed; Material controls retain normal platform motion behavior.

Foreground work observation uses the existing [WorkManager state Flow](https://developer.android.com/reference/androidx/work/WorkManager) while the UI lifecycle is active. Observation does not enqueue work, change cadence or fetch prices.

Screenshots/golden tests use declared deterministic synthetic inputs and controlled emulator profiles. They do not establish physical-device or general release readiness.
