# Charts and persisted history

Dashboard action bars count the existing saved rows grouped by authoritative current action. Text labels and integer counts accompany each bar; these are not Health percentages or new recommendations.

History charts use one symbol at a time, `decision.timestamp` and that decision's persisted C/H1/H5/Blend. Only parseable UTC/offset timestamps are placed on the time axis. No timezone is invented for an ambiguous source time. The timeline retains unplottable records.

The score plot uses four labelled colors and four marker shapes (circle, square, triangle, diamond) on a 0–100 rendering scale. It draws individual points only, never connected/interpolated lines. Missing numeric values produce no marker. Time between observations remains a gap. The legend and exact accessible data table provide alternatives to color and Canvas.

All-loaded is the default window. Seven-, 30- and 90-day loaded windows appear only when loaded observations span that duration. A selected window ends at the newest loaded observation, rather than implying a complete live history. Older decisions remain available through normal pagination. The exact-data expansion shows the latest 50 plotted observations with its count limit explicitly stated; full decisions remain accessible in the paged timeline.

Charts are descriptive. No price forecast, return estimate, technical indicator, score reduction or trading-policy calculation is added. Synthetic visualization fixtures are separately labelled in the evidence manifest and are never represented as real historical observations.
