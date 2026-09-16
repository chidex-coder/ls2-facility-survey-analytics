# LS 2.0 Facility Survey — Decision Brief

*Network: 184 facilities, 23 LGAs, baseline + 5 bi-weekly rounds (1,104 visits). Numbers are from `outputs/analysis_results.json`; every figure is interactive in the dashboard.*

## Headline picture

| Indicator | Value | Read |
|---|---|---|
| Composite readiness | 70.7 / 100 | 7.5% of visits Critical (<50), 28.6% Strong (>80) |
| Facility open on arrival | 80.1% | 46-minute average wait when closed; "staff not yet arrived" is the top reason |
| Permanent staff attendance | 72.0% | 28% absenteeism; JCHEWs lowest (68.6%), Pharmacy Technicians highest (75.8%) |
| Tracer commodity stock-outs | 31.4% of stocked items | maternal life-saving items worst: Ambu drape 55%, MgSO₄ 43%, TXA 43% |
| Vaccine availability | 69.2% | HPV (56%) and MEN A (59%) lowest; OPV (78%) highest |
| Planned sessions delivered | 78.0% | staff unavailability explains a third of missed sessions |
| Cold chain interruption | 20.7% of CCE facilities | power failure dominates; only 66% have a working vaccine fridge |
| Requisition submitted last cycle | 61.7% | 71% complete & on time; 49% fully filled |

## Six findings that should change what happens next fortnight

1. **Late salaries empty duty posts within the same round.** In the round where only 14% of facilities had salaries paid on time, attendance fell from ~74% to 64% and session completion from ~79% to 71%. Salary-linked reasons already explain 15% of all absences, and in rural facilities staff leave the post two or more times a month to reach a bank in 49% of visits.
2. **Stock-outs are mostly an upstream problem — but facility behaviour halves the risk.** 58% of stock-outs are attributed to central stock-outs, delivery delays or partial fulfilment. Yet facilities that both submit requisitions and can calculate minimum stock run a 24% stock-out rate against 44% where neither happens.
3. **Stock is being drawn down faster than it is replaced.** Stock-outs climbed from 18% at baseline to 39% by round 6; 85% of items with a known minimum stock level sit below it. The trend, not the level, is the alarm.
4. **The cold chain is the immunisation bottleneck.** Vaccine availability is 73% with a working fridge and no interruption, 58% after an interruption, and immunisation sessions are fully delivered in 82% of weeks where the fridge works versus 57% where it does not.
5. **Geography beats facility type.** Attendance spans 58% (Igabi) to 80% (Sanga); readiness spans 62 (Igabi) to 85 (Sanga); facilities in security-risk LGAs average 3.9 points lower readiness. Health Posts lag on cold chain and opening, General Hospitals on nothing in particular.
6. **Human resources gaps are structural.** 38% of PHCs have no permanent doctor and 9% of PHCs/BHCs have no permanent nurse or midwife; 35% of the workforce is ad hoc or volunteer.

## Recommended actions (owner → action → metric to watch)

| Owner | Action | Watch in the dashboard |
|---|---|---|
| State PHC Board / Finance | Lock salary payment to the 25th–month-end window; pilot agent-banking / POS access at rural facility catchments | *Salary on time*, *Access to Salary* absences, attendance by round |
| KADHSMA | Prioritise MgSO₄, TXA, Ambu drapes, misoprostol and chlorhexidine in the next distribution; publish fulfilment feedback to facilities | Stock-out rate by commodity, requisition funnel, *No feedback from KADHSMA* reason |
| LGA supervision teams | Visit the facilities flagged ≥50% at-risk (Predictions tab) before the next round; start with Kauru, Chikun, Kudan, Igabi, Giwa | At-risk table, readiness trend |
| LGA cold chain officers | Repair/replace non-functional fridges in stocking facilities; schedule generator fuel where power failure is the recorded cause | CCE functionality, interruption reasons, vaccine availability by cold chain status |
| Facility in-charges | Weekly roster updates and daily register sign-in — attendance is 80% with on-time salary + updated roster vs 55% with neither | Attendance by salary × roster |
| Training unit | LMIS / minimum-stock calculation refresher for the 22% of items where nobody can calculate the minimum | Below-minimum-stock share, stock-out by requisition behaviour |

## How to use the predictions

* **At-risk facilities** — slide the risk threshold; the table lists facilities above it with their latest readiness, expected attendance if salary is on time, and mean stock-out risk. Pair with the map on the Overview tab to plan routes.
* **Commodity stock-out risk** — set the minimum risk and read the ranked facility × commodity pairs; these are the emergency-resupply list.
* **Counterfactual attendance** — the gain chart shows, per facility, the attendance uplift the model expects from on-time salary alone (mean +3.6 points; +16 points at the most salary-sensitive sites).
* **Segments** — High performers (71 facilities), Stock-constrained (44) and Multi-constraint / priority (69) each warrant a different support package: light-touch monitoring, supply-side fixes, and full supportive supervision respectively.

## Caveats

The dataset is generated from the questionnaire structure, so the levels are illustrative; the pipeline, SQL, models and dashboard run unchanged on a real export with the same sheet layout. Model quality on real data should be re-checked on the held-out round before the risk lists are acted on.
