# Gateway Decisions

Source: `gateway_rules_extracted.md`

1. Missing gateway object behavior

Decision: BLOCKED.

Reason: If no pre-built gateway object exists, Entry Engine has no permission map and must not infer GH/GL.

2. Session phase definitions

Decision:

- PREMARKET = before premarket lock.
- OPENING_WINDOW = 6:30 AM-7:00 AM PT.
- MIDSESSION = 7:00 AM-12:00 PM PT.
- CLOSED = after 12:00 PM PT.

Reason: Opening window is the primary early-session trade window; 12:00 PM is hard cutoff.

3. Allowed sides logic

Decision: BOTH by default when Gateway is ARMED. If Rejection Mode is active, allowed side equals watch_side. If Gateway is OFF/BLOCKED, allowed side = NONE.

Reason: Gateway controls permission; Rejection Engine controls directional premise.

4. Full premarket_context versus flat tv_context

Decision: Long term use full premarket_context. Short term allow flat tv_context until Pre-Market Engine is built.

Reason: Current TV feed is flat; future architecture requires full context object.

5. OFF / ARMED mapping to OPEN / BLOCKED

Decision: Gateway OFF = BLOCKED. Gateway ARMED = OPEN.

Reason: OFF means inside gateway/no engagement; ARMED means outside gateway and Step 2 may evaluate.

6. 12:00 PM cutoff effect on Gateway

Decision: Yes, after 12:00 PM PT Gateway must be BLOCKED/CLOSED.

Reason: No new trades allowed after cutoff.

7. near_liquidity boolean definition

Decision: near_liquidity = true only when price is at/touching active liquidity or inside an active stack/zone. Do not invent distance thresholds.

Reason: Distance thresholds belong to Step 4 proximity filter, not Gateway.

8. nearest_level meaning

Decision: nearest_level should mean nearest newly relevant liquidity from premarket context when available; short term use closest active level from current level map.

Reason: Blueprint requires nearest newly relevant liquidity; current feed does not yet provide full context.

9. PMH/PML/ONH/ONL lock status source

Decision: Source should be premarket_locked/session context plus level status in future. Short term, TradingView fires only after lock, so posted levels are treated locked.

Reason: TV alert timing enforces lock for now.

10. Missing level status behavior

Decision: Short term allow missing status and treat non-null posted levels as ACTIVE. Long term require status.

Reason: Current TV payload sends prices only; future premarket_context should send price + status.

11. Stack context requirement

Decision: Long term Gateway requires high_side/low_side stack context. Short term, if stack context missing, Gateway can operate as SINGLE-level only.

Reason: Current context feed does not yet provide stack object.

12. Price inside stack without outside GH/GL

Decision: BLOCKED.

Reason: Blueprint says if price is inside stack, GH/GL must be outside stack boundaries; without that, permission is unknown.

13. Rejection state influence on Gateway

Decision: Rejection state does not open Gateway. Gateway permission comes first. Once Gateway is open and Rejection Mode is ON, rejection watch_side controls allowed side.

Reason: Step 1 defines permission; Rejection Engine defines directional premise after activation.

14. OPENING_WINDOW state existence

Decision: Yes, include OPENING_WINDOW as operational session phase from 6:30-7:00 AM PT, but not as a blueprint system state.

Reason: Useful for diagnostics and future time filters; system states remain OFF/ARMED/REJECTION MODE ON/PROVISIONAL/NEUTRAL RESET.
