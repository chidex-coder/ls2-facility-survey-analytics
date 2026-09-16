# LS 2.0 Facility Survey - Analysis Report

Every question below is answered with a SQL query against the SQLite warehouse (`outputs/ls2_survey.db`) and an interactive Plotly figure (`outputs/figures/<id>.html`).

## Facility access

### Q01. How often are facilities actually open when a data champion arrives, and where is access weakest?

Facilities were open on arrival in 80.1% of 1104 visits. Where closed, data champions waited 46 minutes on average. Kauru is the weakest LGA (68.8%) and Sanga the strongest (93.8%).

Figure: `outputs/figures/Q01.html`

<details><summary>SQL</summary>

```sql
SELECT lga, COUNT(*) AS visits, AVG(facility_open_on_arrival_flag) AS open_rate,
           AVG(CASE WHEN facility_open_on_arrival_flag=0 THEN wait_minutes END) AS avg_wait_when_closed
    FROM v_visits GROUP BY lga ORDER BY open_rate
```

</details>

### Q02. What are the main reasons facilities are closed when visited?

The leading cause of a closed facility is 'Staff not yet arrived' (30.0% of 220 cases). Insecurity accounts for 17.7%, concentrated in security-risk LGAs.

Figure: `outputs/figures/Q02.html`

<details><summary>SQL</summary>

```sql
SELECT reason_closed_on_arrival AS reason, COUNT(*) AS n
    FROM v_visits WHERE facility_open_on_arrival_flag=0 GROUP BY 1 ORDER BY n DESC
```

</details>

### Q03. What are facility operating hours, and can facilities refer emergencies with transport?

41.8% of facilities report 24-hour operation, driven by PHCs and General Hospitals; most Health Posts run 6-8 hour days. 78.2% of visits confirmed the facility can refer obstetric emergencies, but transport was available when needed in only 59.1% of those.

Figure: `outputs/figures/Q03.html`

<details><summary>SQL</summary>

```sql
SELECT facility_type, hours_of_operation, COUNT(DISTINCT facility_id) AS facilities
    FROM v_visits WHERE round_number=1 GROUP BY 1,2
```

</details>

## Cold chain

### Q04. How functional is the cold chain, and how often is it interrupted?

Where equipment exists, functionality ranges from 74.5% (Rush (3L)) to 82.2% (Refrigerators). Only 66.4% of facilities with cold chain equipment have at least one working vaccine refrigerator, and 20.7% of visits recorded a cold chain interruption since the previous visit, most often 'Power failure / no electricity'.

Figure: `outputs/figures/Q04.html`

<details><summary>SQL</summary>

```sql
SELECT cce_type, AVG(available_flag) AS availability,
           AVG(CASE WHEN available_flag=1 THEN functional_flag END) AS functionality
    FROM cold_chain_equipment GROUP BY cce_type ORDER BY functionality
```

</details>

## Service delivery

### Q05. Which services do facilities offer, and how reliably are planned sessions delivered?

Malaria and ANC are near-universal, while Nutrition (69.6%) and Labour & Delivery are the least available. Planned sessions were fully delivered in 78.0% of service-weeks; Immunization has the lowest completion (75.4%).

Figure: `outputs/figures/Q05.html`

<details><summary>SQL</summary>

```sql
SELECT service, AVG(offered_flag) AS offered_rate,
           AVG(all_conducted_flag) AS session_completion_rate
    FROM service_sessions GROUP BY service ORDER BY session_completion_rate
```

</details>

### Q06. What stops planned sessions from happening?

'Staff unavailable (leave, redeployment, strike)' explains 32.6% of missed sessions - a human-resource problem before a supply problem. Security concerns account for 10.2% and vaccine or cold-chain issues for 4.6%.

Figure: `outputs/figures/Q06.html`

<details><summary>SQL</summary>

```sql
SELECT reason_not_conducted AS reason, COUNT(*) AS n
    FROM service_sessions WHERE all_conducted_flag=0 GROUP BY 1 ORDER BY n DESC
```

</details>

### Q07. What is training coverage across the network?

77.2% of facilities had any staff trained in the past two years. Coverage is highest for Life Saving Skills (28.3%) and lowest for Nutrition / IYCF (18.5%); no single training reaches half of facilities.

Figure: `outputs/figures/Q07.html`

<details><summary>SQL</summary>

```sql
SELECT t.training, COUNT(DISTINCT t.facility_id)*1.0/(SELECT COUNT(*) FROM facilities) AS coverage
    FROM trainings t GROUP BY 1 ORDER BY coverage DESC
```

</details>

## Human resources

### Q08. What does the workforce look like by cadre and employment type?

The network has 4,652 health workers: 65.4% permanent, 20.7% ad hoc/seconded and 13.8% volunteers. CHEWs and JCHEWs form the backbone; 38.1% of PHCs have no permanent doctor and 9.1% of PHCs/BHCs have no permanent nurse or midwife. Women make up 55.1% of the workforce.

Figure: `outputs/figures/Q08.html`

<details><summary>SQL</summary>

```sql
SELECT cadre, SUM(permanent) AS permanent, SUM(adhoc_a) AS adhoc_a, SUM(adhoc_b) AS adhoc_b, SUM(volunteer) AS volunteer
    FROM v_staffing WHERE round_number=1 GROUP BY cadre ORDER BY permanent DESC
```

</details>

### Q09. How high is absenteeism, and which cadres are most affected?

Across all visits, 72.0% of permanent staff scheduled for duty were actually present - an absenteeism rate of 28.0%. JCHEWs are least reliably present (68.6%); Pharmacy Technicians most (75.8%).

Figure: `outputs/figures/Q09.html`

<details><summary>SQL</summary>

```sql
SELECT cadre, SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate, SUM(permanent_scheduled_today) AS scheduled
    FROM v_staffing WHERE permanent_scheduled_today>0 GROUP BY cadre ORDER BY attendance_rate
```

</details>

### Q10. Where is absenteeism geographically concentrated?

Attendance ranges from 57.6% in Igabi to 79.7% in Sanga - a 22-point spread that points to LGA-level management and security effects rather than individual behaviour.

Figure: `outputs/figures/Q10.html`

<details><summary>SQL</summary>

```sql
SELECT lga, SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate
    FROM v_staffing WHERE permanent_scheduled_today>0 GROUP BY lga ORDER BY attendance_rate
```

</details>

### Q11. Why are staff absent?

'Leave (Study, Annual, Maternity, etc.)' is the top recorded reason (11.2%), followed by 'Access to Salary' (9.0%). Salary-linked absence (going to access salary, or dissatisfaction with pay) accounts for 15.4% of all absences and is directly addressable by payment reform.

Figure: `outputs/figures/Q11.html`

<details><summary>SQL</summary>

```sql
SELECT reason, SUM(staff_count) AS staff FROM v_absence GROUP BY reason ORDER BY staff DESC
```

</details>

### Q12. How do salary delays affect attendance and service delivery over time?

In Bi-weekly 3 salary timeliness collapsed to 14.1% (vs 78.9% in other rounds); attendance fell to 63.7% (vs 73.7%) and session completion to 71.0% in the same round. Late salaries translate almost immediately into empty duty posts.

Figure: `outputs/figures/Q12.html`

<details><summary>SQL</summary>

```sql
SELECT round_number, round_name,
           AVG(salary_paid_on_time_last_3_months_flag) AS salary_on_time,
           SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate,
           AVG(session_completion_rate) AS session_completion
    FROM v_visits GROUP BY 1,2 ORDER BY 1
```

</details>

### Q13. Do roster practices and salary timeliness independently predict attendance?

When salary is on time and the roster was updated this week, attendance is 80.5%; with delayed salary and a stale roster it drops to 55.0%. Both levers matter, and roster discipline partly cushions the salary effect.

Figure: `outputs/figures/Q13.html`

<details><summary>SQL</summary>

```sql
SELECT CASE WHEN salary_paid_on_time_last_3_months_flag=1 THEN 'Salary on time' ELSE 'Salary delayed' END AS salary,
           CASE WHEN roster_updated_this_week_flag=1 THEN 'Roster updated' ELSE 'Roster not updated' END AS roster,
           SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate, COUNT(*) AS visits
    FROM v_visits GROUP BY 1,2
```

</details>

### Q14. How much service time is lost to accessing salary payments?

In rural facilities, staff leave the post to access salary two or more times a month in 49.1% of visits; the main reason is 'No bank or ATM nearby'. Bringing agent banking or POS access to facility catchments would recover many lost duty days.

Figure: `outputs/figures/Q14.html`

<details><summary>SQL</summary>

```sql
SELECT staff_leave_facility_for_salary_frequency AS frequency, urban_rural, COUNT(*) AS visits
    FROM v_visits GROUP BY 1,2
```

</details>

## Supply chain

### Q15. Which essential medicines and commodities are most often stocked out?

On average 31.4% of stocked tracer items had a stock-out since the previous visit. Maternal life-saving commodities fare worst (mean 33.9%): Calibrated Blood Collection Drape (55.4%), Magnesium Sulphate Injection (42.7%) and Tranexamic Acid Injection (42.6%). Paracetamol Tablet is the most reliably available (22.7%).

Figure: `outputs/figures/Q15.html`

<details><summary>SQL</summary>

```sql
SELECT commodity, category, AVG(stockout_flag) AS stockout_rate, AVG(zero_balance_flag) AS zero_balance_rate,
           AVG(below_min_stock_flag) AS below_min_rate, COUNT(*) AS observations
    FROM v_commodity WHERE stocked_flag=1 GROUP BY 1,2 ORDER BY stockout_rate DESC
```

</details>

### Q16. Are stock-outs caused upstream or at the facility?

58.3% of stock-outs are attributed to upstream causes (central stock-out, delivery delay, partial fulfilment, no feedback), versus 20.6% to facility-side causes (late requisition, poor forecasting, unreplaced expiries). The single largest is 'Stock-out at LGA/state/central supply level' at 31.0%.

Figure: `outputs/figures/Q16.html`

<details><summary>SQL</summary>

```sql
SELECT stockout_reason AS reason, COUNT(*) AS n FROM commodity_stock WHERE stockout_flag=1 GROUP BY 1 ORDER BY n DESC
```

</details>

### Q17. Which LGAs have the worst commodity availability?

Stock-out rates range from 18.1% in Sanga to 42.2% in Kauru. The top-five LGAs (Kauru, Chikun, Kudan, Igabi, Giwa) should be prioritised for supply-chain supervision.

Figure: `outputs/figures/Q17.html`

<details><summary>SQL</summary>

```sql
SELECT lga, AVG(stockout_flag) AS stockout_rate FROM v_commodity WHERE stocked_flag=1 GROUP BY lga ORDER BY stockout_rate DESC
```

</details>

### Q18. How well does the requisition-to-delivery process work?

Only 61.7% of facilities submitted a requisition in the last cycle; of those, 71.4% were complete and on time and 48.9% were fully filled. Delivery documentation accompanied 79.4% of receipts. Each leak in this funnel compounds into the stock-out rates above.

Figure: `outputs/figures/Q18.html`

<details><summary>SQL</summary>

```sql
SELECT requisition_frequency, AVG(requisition_submitted_last_cycle_flag) AS submitted,
           AVG(requisition_complete_on_time_flag) AS complete_on_time,
           AVG(CASE WHEN requisition_receipt_status='Yes, all items received' THEN 1.0 WHEN requisition_receipt_status IS NULL THEN NULL ELSE 0 END) AS fully_received,
           AVG(delivery_documentation_provided_flag) AS documented, COUNT(*) AS visits
    FROM v_visits GROUP BY 1 ORDER BY visits DESC
```

</details>

### Q19. Do requisition discipline and stock-management skills reduce stock-outs?

Facilities that submitted a requisition and know how to calculate minimum stock have a 23.6% stock-out rate, against 43.5% where no requisition was submitted and nobody can calculate minimum stock. Requisition discipline and LMIS skills are the cheapest stock-out reducers available.

Figure: `outputs/figures/Q19.html`

<details><summary>SQL</summary>

```sql
SELECT CASE WHEN requisition_submitted_last_cycle_flag=1 THEN 'Requisition submitted' ELSE 'No requisition' END AS requisition,
           knows_min_stock_calculation, AVG(stockout_flag) AS stockout_rate, COUNT(*) AS n
    FROM v_commodity WHERE stocked_flag=1 GROUP BY 1,2
```

</details>

### Q20. Which supply sources are most reliable?

KDHSMA supplies 36.6% of stocked items. Items sourced from Open Market show the lowest stock-out rate (24.6%) and NGO-sourced items the highest (36.5%).

Figure: `outputs/figures/Q20.html`

<details><summary>SQL</summary>

```sql
SELECT supplier, AVG(stockout_flag) AS stockout_rate, COUNT(*) AS n FROM commodity_stock WHERE stocked_flag=1 AND supplier IS NOT NULL GROUP BY 1 HAVING n>200 ORDER BY stockout_rate
```

</details>

### Q21. How many facilities are below minimum stock (early-warning)?

A minimum stock level was known for 78.4% of stocked items. Where known, 85.2% of items sit below the minimum - the facility is one bad fortnight away from a stock-out. Calibrated Blood Collection Drape (95.8%) is most exposed.

Figure: `outputs/figures/Q21.html`

<details><summary>SQL</summary>

```sql
SELECT commodity, AVG(below_min_stock_flag) AS below_min_rate,
           AVG(CASE WHEN stock_adequacy_ratio IS NOT NULL THEN MIN(stock_adequacy_ratio, 5) END) AS median_adequacy
    FROM commodity_stock WHERE stocked_flag=1 AND minimum_stock_level IS NOT NULL GROUP BY 1 ORDER BY below_min_rate DESC
```

</details>

## Vaccines

### Q22. Which vaccines are available, and where are the gaps?

64.7% of facilities stock vaccines on site, 25.0% immunise without stocking and 10.3% offer no immunisation. Among stocking facilities, availability is lowest for HPV (55.6%) and MEN A (58.7%) - the newer antigens - and highest for OPV (78.0%).

Figure: `outputs/figures/Q22.html`

<details><summary>SQL</summary>

```sql
SELECT vaccine, AVG(in_stock_flag) AS in_stock_rate, SUM(doses_used) AS doses_used, AVG(physically_verified_flag) AS verified
    FROM vaccine_stock GROUP BY 1 ORDER BY in_stock_rate
```

</details>

### Q23. How much does cold chain status drive vaccine availability and immunisation delivery?

Vaccine availability is 72.7% with a working fridge and no interruption, but 58.2% with working fridge and interruption. Immunisation sessions were fully delivered in 81.5% of weeks where the fridge works versus 57.1% where it does not.

Figure: `outputs/figures/Q23.html`

<details><summary>SQL</summary>

```sql
SELECT CASE WHEN vaccine_fridge_functional_flag=1 THEN 'Working fridge' ELSE 'No working fridge' END AS fridge,
           CASE WHEN cold_chain_interruption_since_last_visit_flag=1 THEN 'Interruption' ELSE 'No interruption' END AS interruption,
           AVG(in_stock_flag) AS in_stock_rate, COUNT(*) AS n
    FROM v_vaccine GROUP BY 1,2
```

</details>

### Q24. Which vaccines are consumed most, and why?

OPV, PCV and PENTA account for 49.4% of doses used. The most common driver of a high-dispensing week is 'Scheduled routine immunization session' (53.4%), and HPV demand is mostly school-based sessions.

Figure: `outputs/figures/Q24.html`

<details><summary>SQL</summary>

```sql
SELECT vaccine, SUM(most_dispensed_flag) AS weeks_most_dispensed, SUM(doses_used) AS doses_used FROM vaccine_stock GROUP BY 1 ORDER BY doses_used DESC
```

</details>

## Readiness

### Q25. Which LGAs are most and least ready to deliver services?

Average readiness is 70.7/100, from 62.0 in Igabi to 84.9 in Sanga. 7.5% of visits score Critical (<50) and 28.6% Strong (>80).

Figure: `outputs/figures/Q25.html`

<details><summary>SQL</summary>

```sql
SELECT lga, AVG(readiness_score) AS readiness, AVG(facility_open_on_arrival_flag) AS open_rate, AVG(attendance_rate) AS attendance,
           1-AVG(stockout_rate) AS stock_availability, AVG(vaccine_availability_rate) AS vaccine_availability, AVG(session_completion_rate) AS sessions
    FROM v_visits GROUP BY lga ORDER BY readiness DESC
```

</details>

### Q26. How does readiness differ by level of care?

General Hospitals score 75.9 and Health Posts 63.2. Health Posts lag most on cold chain (75.8%) and being open on arrival (77.0%), which argues for a differentiated support package by level of care.

Figure: `outputs/figures/Q26.html`

<details><summary>SQL</summary>

```sql
SELECT facility_type, AVG(readiness_score) AS readiness, AVG(attendance_rate) AS attendance, 1-AVG(stockout_rate) AS stock_availability,
           AVG(session_completion_rate) AS sessions, AVG(cce_functionality_rate) AS cold_chain, AVG(facility_open_on_arrival_flag) AS open_rate
    FROM v_visits GROUP BY 1
```

</details>

### Q27. Which individual facilities need urgent support?

The 15 lowest-scoring facilities average 52.8/100, with attendance of 54.0% and a 50.6% stock-out rate. Kudan contributes the most facilities to this list. These are the candidates for an intensive support visit this quarter.

Figure: `outputs/figures/Q27.html`

<details><summary>SQL</summary>

```sql
SELECT f.facility_id, f.facility_name, f.lga, f.facility_type, AVG(v.readiness_score) AS readiness, AVG(v.stockout_rate) AS stockout_rate,
           AVG(v.attendance_rate) AS attendance, AVG(v.facility_open_on_arrival_flag) AS open_rate, COUNT(*) AS visits
    FROM facility_visits v JOIN facilities f USING(facility_id) GROUP BY 1,2,3,4 ORDER BY readiness
```

</details>

### Q28. How are indicators trending across the bi-weekly rounds?

Commodity stock-outs rose from 17.5% at baseline to 38.7% by Bi-weekly 5 as opening balances were drawn down faster than deliveries replaced them, while vaccine availability held around 69.2%. The trend, not the level, is the alarm: resupply cadence is not keeping pace with consumption.

Figure: `outputs/figures/Q28.html`

<details><summary>SQL</summary>

```sql
SELECT round_name, round_number, AVG(readiness_score) AS readiness, AVG(stockout_rate) AS stockout_rate, AVG(vaccine_availability_rate) AS vaccine_availability,
           AVG(facility_open_on_arrival_flag) AS open_rate, AVG(cold_chain_interruption_since_last_visit_flag) AS cold_chain_interruption
    FROM v_visits GROUP BY 1,2 ORDER BY 2
```

</details>

### Q29. Which factors move together, and what are the strongest levers on readiness?

Readiness correlates most positively with Open on arrival (r=0.57) and Vaccine availability (r=0.54), and most negatively with Stock-out rate (r=-0.42). Salary timeliness (r=0.24) and requisition submission (r=0.18) are the strongest management levers.

Figure: `outputs/figures/Q29.html`

<details><summary>SQL</summary>

```sql
SELECT readiness_score, attendance_rate, stockout_rate, vaccine_availability_rate, session_completion_rate, cce_functionality_rate,
           salary_paid_on_time_last_3_months_flag, requisition_submitted_last_cycle_flag, roster_updated_this_week_flag,
           distance_to_lga_hq_km, total_health_workers, security_incident_reported_flag, facility_open_on_arrival_flag
    FROM v_visits
```

</details>

### Q30. Where are the weakest facilities located?

The lowest-readiness clusters are Igabi, Kudan, Kajuru (mean 63.5) while Ikara, Birnin Gwari, Sanga perform best (mean 80.2). Facilities in security-risk LGAs average 67.8 versus 71.7 elsewhere - geography and security explain a large share of the variation.

Figure: `outputs/figures/Q30.html`

<details><summary>SQL</summary>

```sql
SELECT f.facility_name, f.lga, f.facility_type, f.latitude, f.longitude, AVG(v.readiness_score) AS readiness, AVG(v.stockout_rate) AS stockout_rate, AVG(v.attendance_rate) AS attendance
    FROM facility_visits v JOIN facilities f USING(facility_id) GROUP BY 1,2,3,4,5
```

</details>
