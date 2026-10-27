# Accessibility audit

All policy chips include explicit text and distinct icons. Score fields announce their original field name and displayed number; decorative score bars do not announce misleading percentages. History markers use distinct shapes as well as labelled colors. Canvas has a descriptive summary and an expandable exact-value text alternative. Section headings expose heading semantics. Refresh status uses a polite live region.

Native buttons, navigation items, dialog controls and switch rows retain Material touch/focus semantics. Icon-only toolbar controls have content descriptions. Switches use a single 48 dp minimum toggleable parent row with `Role.Switch`; the child switch has no duplicate action. Holding editors use labelled native text fields and numeric keyboards, scroll with the IME and keep failed drafts visible. Destructive removal requires confirmation.

Score displays switch to two columns above 1.3 font scale. Symbol identity/action stacks vertically with large text. Text wraps; screen content and drawers scroll. Large-font instrumentation opens detail, exact GlyphSpec audit and Settings Save. Actual display/font profile evidence is listed in RESPONSIVE_LAYOUT.md.

Measured design-token contrast is recorded in evidence/contrast.json, using WCAG relative luminance. All measured normal text pairs exceed 4.5:1, including policy chip foregrounds against their 12% tint over the theme surface. Main light onSurface/surface is 14.45:1; dark is 13.34:1. This calculation is a palette check, not an exhaustive screen-reader or rendered-pixel audit.

Compose tests exercise focus through text input, navigation, selected theme/filter states, disabled refresh during work, removal cancellation and readable score semantics. No custom continuous animation is added; Material motion uses platform animation settings. Static loading placeholders avoid continuous shimmer.

TalkBack is not installed in the available default API35 emulator image (package inventory returned none). Spoken reading order, switch-access and an independent assistive-technology user audit are NOT TESTED. Physical S9+ visual/font/accessibility validation of this new candidate is NOT TESTED: the failed idle-test artifact remains installed and preserved. These manual review limitations are explicit; no accessibility certification is claimed.
