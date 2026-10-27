# Responsive layouts

The Compose scaffold uses bottom navigation on compact windows and a scrollable rail at 700 dp and above. The drawer retains all eight destinations. Above 1.3 font scale, bottom items use named icons with full accessibility descriptions, avoiding truncated labels. The current destination remains visible in the toolbar and full names remain in the drawer. Toolbar titles ellipsize on one line while retaining full semantic text.

Scores use two columns at larger font scale or narrow card constraints. Symbol identity/action and price levels stack at larger font scale so digits do not wrap into misleading fragments. Search/filter rows scroll and sort controls can wrap. The rail scrolls in short landscape windows, and an explicit test taps all four primary destinations. Forms, history, settings, technical details and drawers scroll.

| Profile | Pixels | Density | Approximate dp | Font scale | Status |
| --- | --- | --- | --- | --- | --- |
| S9+-class narrow | 1080 × 2220 | 480 dpi | 360 × 740 | 1.0 | PASS · evidence/validation/ui-4k-complete.json |
| S9+-class large text | 1080 × 2220 | 480 dpi | 360 × 740 | 2.0 | PASS · evidence/responsive/result.json |
| Modern phone | 1080 × 2400 | 420 dpi | 411 × 914 | 1.5 | PASS · evidence/responsive/result.json |
| Landscape | 2220 × 1080 | 480 dpi | 740 × 360 | 1.0 | PASS · evidence/responsive/result.json |
| Tablet | 1600 × 2560 | 240 dpi | 1067 × 1707 | 1.0 | PASS · evidence/responsive/result.json |
| CI small window | 320 × 640 | 160 dpi | 320 × 640 | 1.0 | See UI_TEST_RESULTS.md |

Pixel/dp figures describe emulator profiles, not execution on these physical devices. Captures show the actual Compose root; system bars outside that root are not included. Synthetic scores/reasons originate from frozen approved fixture values. No pixels are retouched.

Visual inspection caught bottom-label crowding at 200% font and a rail destination below the landscape viewport despite earlier rendering tests passing. Source 9918e11 corrected both; explicit primary-navigation reachability coverage was added. Earlier intermediate captures are retained outside the repository; the evidence directory presents the checked candidate.

The available S9+ remains on the preserved failed idle-test APK. New candidate physical layout, OEM font/display scaling, assistive technology and physical rendering performance are NOT TESTED. No new APK was installed on it during this phase.
