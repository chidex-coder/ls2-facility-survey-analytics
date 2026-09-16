"""Build a populated survey workbook from the LS 2.0 questionnaire structure.

The questionnaire we were given is the *instrument* (question text, options,
skip logic) rather than a response file, so this script produces a realistic
response dataset that follows the instrument exactly: one row per facility
visit for the single-answer questions, plus long tables for the repeated
blocks (per cadre, per absence reason, per commodity, per vaccine, per
service, per training).

Latent facility quality, LGA security context, facility type and a state-wide
salary shock in one round drive the outcomes, so the analytics layer has
genuine structure to uncover.

Run:  python src/generate_survey_data.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

rng = np.random.default_rng(C.RANDOM_SEED)

N_FACILITIES_PER_LGA = 8
ROUNDS = 6  # baseline + 5 bi-weekly visits
BASELINE_DATE = date(2026, 3, 2)
SALARY_SHOCK_ROUND = 4  # state-wide late salary in this round

FIRST_NAMES = ["Aisha", "Musa", "Hauwa", "Ibrahim", "Blessing", "Yusuf", "Zainab", "Danjuma",
               "Grace", "Abdullahi", "Fatima", "Emmanuel", "Halima", "Sani", "Ruth", "Umar",
               "Rahila", "Bala", "Maryam", "Joseph"]
LAST_NAMES = ["Abubakar", "Bako", "Danladi", "Garba", "Haruna", "Ishaya", "Kure", "Lawal",
              "Mohammed", "Nuhu", "Ochigbo", "Sule", "Tanko", "Usman", "Yakubu", "Zakari"]
WARD_STEMS = ["Unguwan", "Sabon", "Tudun", "Kofar", "Gidan", "Rafin", "Dutsen", "Maigana",
              "Kasuwan", "Angwan"]
WARD_SUFFIX = ["Rimi", "Gari", "Wada", "Dan Gama", "Fada", "Kaji", "Abba", "Kanawa", "Madaki", "Sarki"]
FACILITY_STEMS = ["Kwanar", "Sabon", "Ungwan", "Tudun", "Dutse", "Rafin", "Gidan", "Kasuwan",
                  "Maraban", "Zango", "Kofar", "Gwaraji", "Kudan", "Rigasa", "Badarawa", "Narayi"]


def pick(options, p=None, size=None):
    return rng.choice(options, p=p, size=size)


def yes(prob) -> str:
    return "Yes" if rng.random() < prob else "No"


def clip01(x):
    return float(np.clip(x, 0.02, 0.98))


def build_facilities() -> pd.DataFrame:
    rows = []
    fid = 0
    champions = [f"{pick(FIRST_NAMES)} {pick(LAST_NAMES)}" for _ in range(46)]
    for lga, (lat, lon, insecure) in C.LGAS.items():
        wards = [f"{pick(WARD_STEMS)} {pick(WARD_SUFFIX)}" for _ in range(4)]
        lga_effect = rng.normal(0, 0.08)
        for i in range(N_FACILITIES_PER_LGA):
            fid += 1
            ftype = pick(C.FACILITY_TYPES, p=C.FACILITY_TYPE_WEIGHTS)
            type_bonus = {"General Hospital": 0.18, "Primary Health Centre": 0.05,
                          "Basic Health Centre": -0.02, "Health Post": -0.12}[ftype]
            quality = clip01(rng.beta(4, 3) + type_bonus + lga_effect - (0.06 if insecure else 0))
            urban = lga in ("Kaduna North", "Kaduna South", "Zaria", "Sabon Gari", "Chikun") and rng.random() < 0.7
            distance_km = float(np.round(rng.gamma(2, 3) if not urban else rng.gamma(1.5, 1.5), 1))
            rows.append({
                "facility_id": f"KD-{fid:03d}",
                "facility_name": f"{pick(FACILITY_STEMS)} {pick(WARD_SUFFIX)} {'PHC' if ftype=='Primary Health Centre' else 'BHC' if ftype=='Basic Health Centre' else 'HP' if ftype=='Health Post' else 'GH'}",
                "facility_alternate_name": "None" if rng.random() < 0.7 else f"{pick(WARD_STEMS)} Clinic",
                "lga": lga,
                "ward": pick(wards),
                "facility_type": ftype,
                "urban_rural": "Urban" if urban else "Rural",
                "security_risk_lga": bool(insecure),
                "latitude": round(lat + rng.normal(0, 0.09), 5),
                "longitude": round(lon + rng.normal(0, 0.09), 5),
                "distance_to_lga_hq_km": distance_km,
                "facility_phone": f"0{rng.choice([70,80,81,90,91])}{rng.integers(10**7, 10**8-1)}",
                "data_champion": champions[(fid - 1) % len(champions)],
                "latent_quality": round(quality, 3),
            })
    return pd.DataFrame(rows)


CADRE_BASE = {  # mean permanent headcount by facility type
    "Medical Officer": {"General Hospital": 6, "Primary Health Centre": 0.6, "Basic Health Centre": 0.15, "Health Post": 0},
    "Nurse/Midwife": {"General Hospital": 22, "Primary Health Centre": 3.2, "Basic Health Centre": 1.4, "Health Post": 0.3},
    "CHO": {"General Hospital": 3, "Primary Health Centre": 1.5, "Basic Health Centre": 0.8, "Health Post": 0.3},
    "CHEW": {"General Hospital": 5, "Primary Health Centre": 4.5, "Basic Health Centre": 3.0, "Health Post": 1.6},
    "JCHEW": {"General Hospital": 3, "Primary Health Centre": 3.0, "Basic Health Centre": 2.2, "Health Post": 1.4},
    "Medical Lab Technician": {"General Hospital": 6, "Primary Health Centre": 0.9, "Basic Health Centre": 0.3, "Health Post": 0.05},
    "Medical Records Officer": {"General Hospital": 4, "Primary Health Centre": 1.0, "Basic Health Centre": 0.5, "Health Post": 0.1},
    "Pharmacy Technician": {"General Hospital": 5, "Primary Health Centre": 0.9, "Basic Health Centre": 0.4, "Health Post": 0.05},
    "Environmental Health Officer": {"General Hospital": 2, "Primary Health Centre": 0.5, "Basic Health Centre": 0.3, "Health Post": 0.1},
}

VACCINE_DEMAND = {"BCG": 40, "HPV": 25, "IPV": 45, "MR": 30, "MEN A": 25, "MCV": 30, "OPV": 90, "YF": 30, "PENTA": 90, "ROTA": 60, "PCV": 90}

# Items with chronic upstream shortages: multiplier on the chance of a delivery
HARD_TO_GET = {"Tranexamic Acid Injection": 0.5, "Calibrated Blood Collection Drape": 0.4,
               "Magnesium Sulphate Injection": 0.7, "Implants": 0.65, "Chlorhexidine Gel": 0.7,
               "Misoprostol": 0.8, "Artemether Injection": 0.8, "Ibuprofen Suspension": 0.75}

ABSENCE_WEIGHTS = np.array([
    6, 5, 3, 2, 4, 4, 1, 2, 1, 2, 3, 1, 1, 0.5, 1, 6, 8, 5, 4, 3,
], dtype=float)


def facility_establishment(fac) -> dict[str, dict]:
    """Fixed per-facility staffing structure (headcount doesn't change round to round)."""
    est = {}
    for cadre in C.CADRES:
        mu = CADRE_BASE[cadre][fac.facility_type] * (0.7 + 0.6 * fac.latent_quality)
        perm = int(rng.poisson(mu))
        adhoc_a = int(rng.poisson(mu * 0.25)) if cadre in ("Nurse/Midwife", "CHEW", "JCHEW", "CHO") else int(rng.random() < 0.08)
        adhoc_b = int(rng.poisson(0.5)) if cadre in ("Nurse/Midwife", "CHEW", "JCHEW", "Medical Lab Technician", "Pharmacy Technician") and fac.facility_type != "Health Post" else 0
        vol = int(rng.poisson(0.9)) if cadre in ("CHEW", "JCHEW", "Medical Records Officer") else int(rng.random() < 0.1)
        est[cadre] = {"permanent": perm, "adhoc_a": adhoc_a, "adhoc_b": adhoc_b, "volunteer": vol}
    return est


def generate():
    facilities = build_facilities()
    visits, staffing, absences, commodities, vaccines, sessions, trainings, cce_rows = [], [], [], [], [], [], [], []

    for fac in facilities.itertuples(index=False):
        est = facility_establishment(fac)
        q = fac.latent_quality
        # Facility-level fixed characteristics
        hours = pick(C.HOURS_OF_OPERATION, p=[0.62, 0.2, 0.15, 0.03]) if fac.facility_type in ("General Hospital", "Primary Health Centre") else pick(C.HOURS_OF_OPERATION, p=[0.2, 0.3, 0.42, 0.08])
        days_open = 7 if hours == "24 hours" else int(pick([5, 6, 7], p=[0.5, 0.3, 0.2]))
        has_register = rng.random() < 0.55 + 0.4 * q
        register_type = pick(C.ATTENDANCE_REGISTER_TYPES, p=[0.78, 0.08, 0.06, 0.08]) if has_register else None
        has_roster = rng.random() < 0.5 + 0.45 * q
        roster_dev = pick(C.ROSTER_DEV_FREQ, p=[0.6, 0.15, 0.12, 0.08, 0.05]) if has_roster else None
        roster_upd = pick(C.ROSTER_UPDATE_FREQ, p=[0.35, 0.65]) if has_roster else None
        stocks_vaccines = pick(C.VACCINE_STOCK_STATUS, p=[0.72, 0.2, 0.08]) if fac.facility_type != "Health Post" else pick(C.VACCINE_STOCK_STATUS, p=[0.35, 0.45, 0.2])
        has_cce = stocks_vaccines == "Yes" or rng.random() < 0.3
        cce_types = [t for t in C.CCE_TYPES if rng.random() < {"Solar Refrigerators and Freezers": 0.7, "Refrigerators": 0.35,
                     "Temperature Monitoring Devices": 0.8, "Cold Boxes (6L)": 0.75, "GioStyle (4L)": 0.6,
                     "Rush (3L)": 0.4, "Ice Packs": 0.9}[t]] if has_cce else []
        services = [s for s in C.SERVICES if rng.random() < {
            "Immunization": 0.95 if stocks_vaccines != C.VACCINE_STOCK_STATUS[2] else 0.0,
            "Nutrition": 0.75, "Antenatal Care": 0.92, "Postnatal Care": 0.85, "IMCI": 0.8,
            "Malaria": 0.97, "Labour and Delivery": 0.9 if fac.facility_type != "Health Post" else 0.35,
            "Family Planning": 0.88}[s]]
        trained = rng.random() < 0.45 + 0.5 * q
        fac_trainings = [t for t in C.TRAININGS if rng.random() < 0.12 + 0.35 * q] if trained else []
        req_freq = pick(C.REQUISITION_FREQ, p=[0.55, 0.2, 0.15, 0.1]) if q > 0.25 else pick(C.REQUISITION_FREQ, p=[0.3, 0.2, 0.2, 0.3])
        req_system = pick(C.REQUISITION_SYSTEMS, p=[0.35, 0.3, 0.15, 0.15, 0.05])
        knows_min_stock = pick(["Yes, I know how to calculate", "Yes, someone else is assigned to calculate", "No"],
                               p=[0.3 + 0.4 * q, 0.2, max(0.05, 0.5 - 0.4 * q)] / np.sum([0.3 + 0.4 * q, 0.2, max(0.05, 0.5 - 0.4 * q)]))
        main_supplier = pick(C.SUPPLIERS, p=[0.05, 0.5, 0.12, 0.08, 0.06, 0.12, 0.05, 0.02])
        respondent_name = f"{pick(FIRST_NAMES)} {pick(LAST_NAMES)}"
        respondent_cadre = pick(C.CADRE_OF_RESPONDENT, p=[0.3, 0.2, 0.3, 0.08, 0.05, 0.04, 0.03])
        respondent_pos = pick(C.RESPONDENT_POSITIONS, p=[0.6, 0.2, 0.08, 0.08, 0.04])

        # Rolling stock balances carried between rounds
        type_scale = {"General Hospital": 4.0, "Primary Health Centre": 1.0, "Basic Health Centre": 0.55, "Health Post": 0.3}[fac.facility_type]
        balances = {name: max(0, int(rng.normal(cons * type_scale * 0.9, cons * type_scale * 0.6))) for name, _, _, cons in C.COMMODITIES}
        vac_balances = {v: max(0, int(rng.normal(VACCINE_DEMAND[v] * type_scale * 0.8, VACCINE_DEMAND[v] * type_scale * 0.5))) for v in C.VACCINES}

        for r in range(1, ROUNDS + 1):
            visit_id = f"{fac.facility_id}-R{r}"
            visit_date = BASELINE_DATE + timedelta(days=14 * (r - 1) + int(rng.integers(0, 4)))
            round_name = "Baseline" if r == 1 else f"Bi-weekly {r - 1}"
            salary_shock = r == SALARY_SHOCK_ROUND
            security_event = fac.security_risk_lga and rng.random() < 0.18

            # ---------- Module 1: facility status on arrival ----------
            p_open = clip01(0.72 + 0.25 * q - (0.35 if security_event else 0) - (0.06 if salary_shock else 0))
            open_on_arrival = yes(p_open)
            arrive_hour = int(pick([8, 9, 10], p=[0.5, 0.35, 0.15]))
            arrival_time = f"{arrive_hour:02d}:{int(rng.integers(0, 60)):02d}"
            if open_on_arrival == "Yes":
                opened_time, closed_reason, wait_min = None, None, 0
            else:
                wait_min = int(rng.gamma(2, 25))
                opened_time = f"{(arrive_hour * 60 + int(rng.integers(0,60)) + wait_min) // 60 % 24:02d}:{(wait_min % 60):02d}" if wait_min < 240 else None
                closed_reason = pick(C.CLOSED_REASONS, p=[0.35, 0.15, 0.05, 0.15, 0.12 if fac.security_risk_lga else 0.02, 0.1, 0.08 if fac.security_risk_lga else 0.18])
                if security_event:
                    closed_reason = "Facility closed due to insecurity"
            can_refer = yes(0.6 + 0.35 * q)
            transport_available = yes(0.35 + 0.45 * q) if can_refer == "Yes" else None

            # ---------- Cold chain ----------
            cce_functional = {}
            for t in C.CCE_TYPES:
                if t in cce_types:
                    cce_functional[t] = yes(0.6 + 0.35 * q)
            fridge_ok = any(cce_functional.get(t) == "Yes" for t in ("Solar Refrigerators and Freezers", "Refrigerators"))
            interruption = yes(0.1 + (0.35 if not fridge_ok and has_cce else 0.08) - 0.1 * q) if has_cce else None
            interruption_reason = pick(C.COLD_CHAIN_INTERRUPTION_REASONS, p=[0.45, 0.25, 0.15, 0.1, 0.05]) if interruption == "Yes" else None
            for t in C.CCE_TYPES:
                cce_rows.append({"visit_id": visit_id, "cce_type": t, "available": "Yes" if t in cce_types else "No",
                                 "functional": cce_functional.get(t)})

            # ---------- Module 2: staffing ----------
            salary_on_time = yes(0.15 if salary_shock else 0.7 + 0.15 * q)
            salary_delay = "No delay" if salary_on_time == "Yes" else pick(C.SALARY_DELAY[1:], p=[0.45, 0.35, 0.2])
            salary_issues_any = yes(0.75 if salary_shock else 0.35 - 0.15 * q)
            salary_issue_types = ";".join(sorted(set(pick(C.SALARY_ISSUES, p=[0.45, 0.25, 0.15, 0.1, 0.05], size=int(rng.integers(1, 3)))))) if salary_issues_any == "Yes" else None
            salary_issue_freq = pick(["Once", "2-3 times", "Every month"], p=[0.4, 0.4, 0.2]) if salary_issues_any == "Yes" else None
            salary_effect = pick(C.SALARY_SERVICE_EFFECTS, p=[0.4, 0.3, 0.08, 0.07, 0.15]) if salary_issues_any == "Yes" else None
            leave_for_salary_freq = pick(C.LEAVE_FOR_SALARY_FREQ, p=[0.35 if fac.urban_rural == "Urban" else 0.1, 0.4, 0.3, 0.2 if fac.urban_rural == "Rural" else 0.0] / np.sum([0.35 if fac.urban_rural == "Urban" else 0.1, 0.4, 0.3, 0.2 if fac.urban_rural == "Rural" else 0.0]))
            leave_for_salary_reason = pick(C.LEAVE_FOR_SALARY_REASONS, p=[0.45, 0.2, 0.15, 0.15, 0.05]) if leave_for_salary_freq != "Never" else None
            register_updated = yes(0.5 + 0.45 * q) if has_register else None
            roster_updated_week = yes(0.35 + 0.5 * q) if has_roster else None

            # Attendance probability for permanent staff
            p_att = clip01(0.62 + 0.28 * q
                           - (0.14 if salary_on_time == "No" else 0)
                           - (0.05 if leave_for_salary_freq in ("2-3 times a month", "Weekly") else 0)
                           - min(0.12, 0.006 * fac.distance_to_lga_hq_km)
                           - (0.3 if security_event else 0)
                           + (0.05 if roster_updated_week == "Yes" else 0))
            total_hw = perm_hw = male_hw = 0
            for cadre in C.CADRES:
                e = est[cadre]
                total = e["permanent"] + e["adhoc_a"] + e["adhoc_b"] + e["volunteer"]
                perm = e["permanent"]
                sched_leave = int(rng.binomial(perm, 0.05))
                sched_off = int(rng.binomial(perm - sched_leave, 0.12 if hours == "24 hours" else 0.04))
                working = perm - sched_leave - sched_off
                if hours == "24 hours" and working >= 3:
                    morning = int(np.ceil(working * 0.5)); afternoon = int(np.floor(working * 0.3)); evening = working - morning - afternoon
                else:
                    morning, afternoon, evening = working, 0, 0
                perm_present = int(rng.binomial(working, p_att))
                nonperm_present = int(rng.binomial(total - perm, clip01(p_att - 0.08)))
                present = perm_present + nonperm_present
                perm_absent = working - perm_present
                male = int(rng.binomial(total, 0.62 if cadre in ("Medical Officer", "CHEW", "JCHEW", "Medical Lab Technician", "Environmental Health Officer") else 0.25))
                staffing.append({
                    "visit_id": visit_id, "cadre": cadre, "total_staff": total, "permanent": perm,
                    "adhoc_a": e["adhoc_a"], "adhoc_b": e["adhoc_b"], "volunteer": e["volunteer"],
                    "scheduled_morning": morning, "scheduled_afternoon": afternoon, "scheduled_evening": evening,
                    "scheduled_off": sched_off, "scheduled_leave": sched_leave,
                    "present_today": present, "permanent_present_today": perm_present,
                    "permanent_absent_unscheduled": perm_absent,
                })
                total_hw += total; perm_hw += perm; male_hw += male
                if perm_absent > 0:
                    w = ABSENCE_WEIGHTS.copy()
                    if salary_on_time == "No":
                        w[C.ABSENCE_REASONS.index("Access to Salary")] *= 4
                        w[C.ABSENCE_REASONS.index("Dissatisfaction with Salary and Benefits")] *= 2.5
                    if security_event:
                        w[C.ABSENCE_REASONS.index("Unrest")] *= 12; w[C.ABSENCE_REASONS.index("Crime")] *= 4
                    if fac.distance_to_lga_hq_km > 8:
                        w[C.ABSENCE_REASONS.index("Long Distance to Workplace")] *= 2.2
                        w[C.ABSENCE_REASONS.index("Transportation Problems")] *= 2
                    reasons = rng.choice(C.ABSENCE_REASONS, size=perm_absent, p=w / w.sum())
                    for reason, cnt in pd.Series(reasons).value_counts().items():
                        absences.append({"visit_id": visit_id, "cadre": cadre, "reason": reason, "staff_count": int(cnt)})
            # non-health-worker staff (cleaners, security, admin)
            support_staff = int(rng.poisson({"General Hospital": 12, "Primary Health Centre": 2.2, "Basic Health Centre": 1.2, "Health Post": 0.5}[fac.facility_type]))
            total_staff = total_hw + support_staff
            adhoc_a_total = sum(est[c]["adhoc_a"] for c in C.CADRES)
            adhoc_b_total = sum(est[c]["adhoc_b"] for c in C.CADRES)
            vol_total = sum(est[c]["volunteer"] for c in C.CADRES)

            # ---------- Services & sessions ----------
            imm_sessions_all = None
            for s in C.SERVICES:
                offered = s in services
                if offered:
                    days = pick(["MTWTF", "MTWTFSS", "Specific days", "On needs basis"], p=[0.35, 0.2 if hours == "24 hours" else 0.05, 0.4, 0.05 + (0.15 if hours != "24 hours" else 0)] / np.sum([0.35, 0.2 if hours == "24 hours" else 0.05, 0.4, 0.05 + (0.15 if hours != "24 hours" else 0)]))
                    p_all = clip01(0.7 + 0.25 * q - (0.4 if security_event else 0) - (0.1 if salary_on_time == "No" else 0) - (0.2 if s == "Immunization" and not fridge_ok and stocks_vaccines == "Yes" else 0))
                    all_conducted = yes(p_all)
                    reason = None
                    if all_conducted == "No":
                        w = np.array([0.12 if s == "Immunization" else 0.01, 0.1 if s == "Immunization" else 0.01, 0.3, 0.1, 0.06, 0.12, 0.12 if fac.security_risk_lga else 0.02, 0.1, 0.05, 0.03])
                        if security_event:
                            w[6] *= 8
                        reason = pick(C.SESSION_MISS_REASONS, p=w / w.sum())
                    if s == "Immunization":
                        imm_sessions_all = all_conducted
                else:
                    days, all_conducted, reason = None, None, None
                sessions.append({"visit_id": visit_id, "service": s, "offered": "Yes" if offered else "No",
                                 "dedicated_days": days, "all_planned_sessions_conducted": all_conducted,
                                 "reason_not_conducted": reason})
            if r == 1:
                for t in fac_trainings:
                    trainings.append({"visit_id": visit_id, "facility_id": fac.facility_id, "training": t})

            # ---------- Module 3: requisition ----------
            stocks_meds = yes(0.97)
            if req_freq == "We do not submit requisitions":
                submitted = "No"
            else:
                submitted = yes(0.45 + 0.5 * q)
            not_submitted_reason = pick(C.REQUISITION_NOT_SUBMITTED_REASONS, p=[0.25, 0.15, 0.25, 0.1, 0.15, 0.1]) if submitted == "No" else None
            complete_on_time = yes(0.4 + 0.55 * q) if submitted == "Yes" else None
            receipt = pick(C.REQUISITION_RECEIPT, p=[0.35 + 0.3 * q, 0.45 - 0.15 * q, 0.2 - 0.15 * q] / np.sum([0.35 + 0.3 * q, 0.45 - 0.15 * q, 0.2 - 0.15 * q])) if submitted == "Yes" else None
            partial_reason = pick(C.NOT_RECEIVED_REASONS, p=[0.5, 0.3, 0.15, 0.05]) if receipt in ("Yes, some items received", "No, none received yet") else None
            documentation = yes(0.55 + 0.4 * q) if receipt and receipt != "No, none received yet" else None
            req_types = ";".join([t for t in ["Essential medicines", "Family planning commodities", "Vaccines", "Laboratory commodities"] if rng.random() < {"Essential medicines": 0.95, "Family planning commodities": 0.6, "Vaccines": 0.3, "Laboratory commodities": 0.35}[t]]) if submitted == "Yes" else None
            sources = ";".join(sorted(set([main_supplier] + [s for s in C.SUPPLIERS if rng.random() < 0.12]))) if receipt and receipt != "No, none received yet" else None

            # ---------- Per-commodity stock ----------
            fulfil = {"Yes, all items received": 1.0, "Yes, some items received": 0.55, "No, none received yet": 0.0, None: 0.15}[receipt]
            for name, category, unit, cons in C.COMMODITIES:
                stocked = not (category == "Family Planning" and "Family Planning" not in services) and not (name in ("Oxytocin", "Misoprostol", "Tranexamic Acid Injection", "Magnesium Sulphate Injection", "Calibrated Blood Collection Drape") and "Labour and Delivery" not in services)
                if not stocked:
                    commodities.append({"visit_id": visit_id, "commodity": name, "category": category, "unit": unit,
                                        "facility_stocks_item": "No", "stockout_duration": "The facility does not stock this item",
                                        "stockout_reason": None, "quantity_received": None, "not_received_reason": None,
                                        "minimum_stock_level": None, "stock_balance": None, "supplier": None, "physically_verified": None})
                    continue
                scale = {"General Hospital": 4.0, "Primary Health Centre": 1.0, "Basic Health Centre": 0.55, "Health Post": 0.3}[fac.facility_type]
                monthly = cons * scale * (0.8 + 0.4 * rng.random())
                consumed_two_weeks = int(rng.poisson(monthly / 2))
                p_receive = (0.55 * fulfil + 0.12 + (0.12 if main_supplier == "Open Market" else 0) + (0.1 if main_supplier == "Zipline" else 0)) * HARD_TO_GET.get(name, 1.0)
                received = int(rng.poisson(monthly * (0.55 + 0.6 * q))) if rng.random() < p_receive else 0
                not_received_reason = pick(C.NOT_RECEIVED_REASONS, p=[0.5, 0.3, 0.15, 0.05]) if received == 0 else None
                prev = balances[name]
                bal = max(0, prev + received - consumed_two_weeks)
                stockout_days = 0
                if prev + received < consumed_two_weeks:
                    stockout_days = int(np.clip(14 * (1 - (prev + received) / max(1, consumed_two_weeks)), 1, 14))
                    if prev == 0 and received == 0:
                        stockout_days = 14 + int(rng.integers(0, 20))
                balances[name] = bal
                if stockout_days == 0:
                    dur = "No stock-out"
                elif stockout_days < 7:
                    dur = "Less than 1 week"
                elif stockout_days <= 28:
                    dur = "1 to 4 weeks"
                else:
                    dur = "More than 4 weeks"
                so_reason = None
                if dur != "No stock-out":
                    w = np.array([0.28, 0.14 if submitted == "No" else 0.04, 0.12 if receipt == "Yes, some items received" else 0.04, 0.15, 0.06, 0.12 if knows_min_stock == "No" else 0.04, 0.08, 0.03, 0.03 if name == "Oxytocin" else 0.005, 0.05, 0.02, 0.02])
                    so_reason = pick(C.STOCKOUT_REASONS, p=w / w.sum())
                min_stock = int(round(monthly * 1.5)) if knows_min_stock != "No" or rng.random() < 0.3 else None
                supplier = main_supplier if rng.random() < 0.75 else pick(C.SUPPLIERS)
                if name in ("Injectable Contraceptives", "Implants") and rng.random() < 0.5:
                    supplier = "Federal Government"
                if name in ("Oxytocin", "Misoprostol", "Magnesium Sulphate Injection") and rng.random() < 0.3:
                    supplier = "Free MNCH"
                shown = yes(0.9 if bal > 0 else 0.0) if bal > 0 else "No"
                commodities.append({"visit_id": visit_id, "commodity": name, "category": category, "unit": unit,
                                    "facility_stocks_item": "Yes", "stockout_duration": dur, "stockout_reason": so_reason,
                                    "quantity_received": received, "not_received_reason": not_received_reason,
                                    "minimum_stock_level": min_stock, "stock_balance": bal, "supplier": supplier,
                                    "physically_verified": shown})

            # ---------- Vaccines ----------
            vac_available_sessions = None
            vac_sources = None
            most_dispensed = []
            if stocks_vaccines == "Yes":
                vac_available_sessions = yes(0.55 + 0.4 * q - (0.25 if not fridge_ok else 0))
                vac_sources = ";".join(sorted(set(["LGA"] + (["KDHSMA"] if rng.random() < 0.3 else []) + (["Zipline"] if rng.random() < 0.25 else []))))
                for v in C.VACCINES:
                    opening = vac_balances[v]
                    demand = VACCINE_DEMAND[v] * {"General Hospital": 2.5, "Primary Health Centre": 1.0, "Basic Health Centre": 0.6, "Health Post": 0.35}[fac.facility_type]
                    used = int(rng.poisson(demand / 2))
                    resupply = int(rng.poisson(demand * 0.8)) if rng.random() < 0.3 + 0.4 * q - (0.25 if interruption == "Yes" else 0) - (0.15 if v in ("HPV", "MR", "MEN A") else 0) else 0
                    current = max(0, opening + resupply - used)
                    vac_balances[v] = current
                    dispensed_flag = used > demand * 0.45
                    if dispensed_flag:
                        most_dispensed.append(v)
                    vaccines.append({"visit_id": visit_id, "vaccine": v, "in_stock": "Yes" if current > 0 else "No",
                                     "opening_balance_doses": opening, "doses_received": resupply, "current_balance_doses": current,
                                     "doses_used": min(used, opening + resupply),
                                     "supplier": pick(["LGA", "KDHSMA", "Zipline"], p=[0.65, 0.2, 0.15]),
                                     "physically_verified": yes(0.92) if current > 0 else "No",
                                     "most_dispensed_this_week": "Yes" if dispensed_flag else "No",
                                     "reason_most_dispensed": pick(C.VACCINE_DISPENSE_REASONS, p=[0.55, 0.2, 0.08, 0.1, 0.07] if v != "HPV" else [0.2, 0.15, 0.1, 0.05, 0.5]) if dispensed_flag else None})
            elif stocks_vaccines == C.VACCINE_STOCK_STATUS[1]:
                vac_available_sessions = yes(0.5 + 0.3 * q)
                vac_sources = pick(["LGA cold store", "Nearby PHC", "Ward focal facility"], p=[0.5, 0.35, 0.15])

            visits.append({
                "visit_id": visit_id, "facility_id": fac.facility_id, "round_number": r, "round_name": round_name,
                "visit_date": visit_date.isoformat(), "data_champion": fac.data_champion,
                "respondent_name": respondent_name, "respondent_cadre": respondent_cadre, "respondent_position": respondent_pos,
                "hours_of_operation": hours, "days_open_per_week": days_open,
                "facility_open_on_arrival": open_on_arrival, "arrival_time": arrival_time, "facility_opened_time": opened_time,
                "wait_minutes": wait_min, "reason_closed_on_arrival": closed_reason,
                "can_refer_emergencies": can_refer, "emergency_transport_available_2wks": transport_available,
                "total_staff": total_staff, "permanent_staff": perm_hw + int(support_staff * 0.7), "adhoc_a_staff": adhoc_a_total,
                "adhoc_b_staff": adhoc_b_total, "volunteer_staff": vol_total + int(support_staff * 0.3),
                "total_health_workers": total_hw, "male_health_workers": male_hw, "female_health_workers": total_hw - male_hw,
                "permanent_health_workers": perm_hw,
                "has_cold_chain_equipment": "Yes" if has_cce else "No", "cce_types_available": ";".join(cce_types) if cce_types else None,
                "vaccine_fridge_functional": "Yes" if fridge_ok else ("No" if has_cce else None),
                "cold_chain_interruption_since_last_visit": interruption, "cold_chain_interruption_reason": interruption_reason,
                "services_provided": ";".join(services), "staff_trained_past_2_years": "Yes" if trained else "No",
                "has_dedicated_service_days": yes(0.8), "immunization_sessions_all_conducted": imm_sessions_all,
                "maintains_attendance_register": "Yes" if has_register else "No", "attendance_register_type": register_type,
                "attendance_register_updated_daily": register_updated,
                "no_register_reason": pick(C.NO_REGISTER_REASONS, p=[0.05, 0.3, 0.15, 0.2, 0.15, 0.1, 0.05]) if not has_register else None,
                "has_duty_roster": "Yes" if has_roster else "No", "roster_development_frequency": roster_dev,
                "roster_update_frequency": roster_upd, "roster_updated_this_week": roster_updated_week,
                "salary_paid_on_time_last_3_months": salary_on_time, "salary_delay_length": salary_delay,
                "salary_issues_past_6_months": salary_issues_any, "salary_issue_types": salary_issue_types,
                "salary_issue_frequency": salary_issue_freq, "salary_issue_service_effect": salary_effect,
                "staff_leave_facility_for_salary_frequency": leave_for_salary_freq, "leave_for_salary_reason": leave_for_salary_reason,
                "stocks_essential_medicines": stocks_meds, "requisition_frequency": req_freq,
                "requisition_submitted_last_cycle": submitted, "requisition_system": req_system if submitted == "Yes" else None,
                "requisition_commodity_types": req_types, "requisition_complete_on_time": complete_on_time,
                "requisition_not_submitted_reason": not_submitted_reason, "requisition_receipt_status": receipt,
                "requisition_partial_reason": partial_reason, "commodity_sources": sources,
                "delivery_documentation_provided": documentation, "knows_min_stock_calculation": knows_min_stock,
                "vaccine_stock_status": stocks_vaccines, "vaccines_available_during_sessions": vac_available_sessions,
                "vaccine_sources": vac_sources, "vaccines_most_dispensed_this_week": ";".join(most_dispensed) if most_dispensed else None,
                "security_incident_reported": "Yes" if security_event else "No",
            })

    return {
        "facilities": facilities.drop(columns=["latent_quality"]),
        "facility_visits": pd.DataFrame(visits),
        "staffing_by_cadre": pd.DataFrame(staffing),
        "absence_reasons": pd.DataFrame(absences),
        "cold_chain_equipment": pd.DataFrame(cce_rows),
        "service_sessions": pd.DataFrame(sessions),
        "trainings": pd.DataFrame(trainings),
        "commodity_stock": pd.DataFrame(commodities),
        "vaccine_stock": pd.DataFrame(vaccines),
    }


def data_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    module = {"facilities": "Module 1", "facility_visits": "Modules 1-3", "staffing_by_cadre": "Module 2",
              "absence_reasons": "Module 2", "cold_chain_equipment": "Module 1", "service_sessions": "Module 1",
              "trainings": "Module 1", "commodity_stock": "Module 3", "vaccine_stock": "Module 3"}
    rows = []
    for name, df in tables.items():
        for col in df.columns:
            s = df[col]
            example = s.dropna().iloc[0] if s.notna().any() else ""
            rows.append({"sheet": name, "column": col, "questionnaire_module": module[name],
                         "dtype": str(s.dtype), "non_null": int(s.notna().sum()),
                         "distinct_values": int(s.nunique()), "example": str(example)[:60]})
    return pd.DataFrame(rows)


def main():
    tables = generate()
    tables["data_dictionary"] = data_dictionary(tables)
    C.SURVEY_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(C.SURVEY_XLSX, engine="openpyxl") as xw:
        for name, df in tables.items():
            df.to_excel(xw, sheet_name=name, index=False)
    for name, df in tables.items():
        df.to_csv(C.SURVEY_DIR / f"{name}.csv", index=False)
        print(f"{name:22s} {len(df):7,d} rows x {df.shape[1]:3d} cols")
    print(f"\nWorkbook written to {C.SURVEY_XLSX}")


if __name__ == "__main__":
    main()
