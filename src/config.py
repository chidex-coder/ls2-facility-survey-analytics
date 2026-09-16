"""Shared vocabularies derived from the LS 2.0 questionnaire.

Every list here mirrors an option set or a repeated block in the instrument
(Modules 1-3), so the generator, ETL, analysis and dashboard all speak the
same language.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SURVEY_DIR = ROOT / "data" / "survey"
OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"
DOCS_DIR = ROOT / "docs"
DB_PATH = OUTPUT_DIR / "ls2_survey.db"
SURVEY_XLSX = SURVEY_DIR / "ls2_survey_responses.xlsx"

RANDOM_SEED = 2026

# Kaduna State LGAs with approximate centroids (lat, lon) and a security-risk
# flag used to shape closure / missed-session patterns in the synthetic data.
LGAS = {
    "Birnin Gwari": (10.66, 6.54, True),
    "Chikun": (10.35, 7.30, True),
    "Giwa": (11.05, 7.42, True),
    "Igabi": (10.75, 7.55, True),
    "Ikara": (11.15, 8.22, False),
    "Jaba": (9.55, 8.05, False),
    "Jema'a": (9.45, 8.30, False),
    "Kachia": (9.87, 7.95, True),
    "Kaduna North": (10.57, 7.44, False),
    "Kaduna South": (10.47, 7.42, False),
    "Kagarko": (9.48, 7.70, False),
    "Kajuru": (10.32, 7.68, True),
    "Kaura": (9.60, 8.45, False),
    "Kauru": (10.15, 8.15, False),
    "Kubau": (10.85, 8.20, False),
    "Kudan": (11.25, 7.75, False),
    "Lere": (10.38, 8.57, False),
    "Makarfi": (11.35, 7.88, False),
    "Sabon Gari": (11.17, 7.72, False),
    "Sanga": (9.35, 8.55, False),
    "Soba": (10.98, 8.05, False),
    "Zangon Kataf": (9.75, 8.30, False),
    "Zaria": (11.07, 7.70, False),
}

FACILITY_TYPES = ["Primary Health Centre", "Basic Health Centre", "Health Post", "General Hospital"]
FACILITY_TYPE_WEIGHTS = [0.45, 0.30, 0.17, 0.08]

CADRES = [
    "Medical Officer",
    "Nurse/Midwife",
    "CHO",
    "CHEW",
    "JCHEW",
    "Medical Lab Technician",
    "Medical Records Officer",
    "Pharmacy Technician",
    "Environmental Health Officer",
]

ABSENCE_REASONS = [
    "Personal Health Issues", "Family Responsibilities", "Funeral", "Weddings",
    "Transportation Problems", "Long Distance to Workplace",
    "Poor Health Facility Infrastructure", "Dissatisfaction with Job",
    "Workplace Conflict", "High Workload and Stress",
    "Dissatisfaction with Salary and Benefits",
    "Lack of Professional Development Opportunities",
    "Policy and Governance Issues", "Crime", "Unrest", "Shift",
    "Leave (Study, Annual, Maternity, etc.)", "Workshop and Training",
    "Meetings", "Access to Salary",
]

SERVICES = [
    "Immunization", "Nutrition", "Antenatal Care", "Postnatal Care",
    "IMCI", "Malaria", "Labour and Delivery", "Family Planning",
]

SESSION_MISS_REASONS = [
    "Vaccine stock-out", "Cold chain equipment failure",
    "Staff unavailable (leave, redeployment, strike)",
    "Facility closed (holiday, strike, renovation)",
    "Lack of transportation or logistics support",
    "Attending training, meeting, or other official assignment",
    "Security concerns (insecurity, movement restrictions)",
    "Low community turnout / community resistance",
    "Weather or environmental conditions", "Other",
]

CLOSED_REASONS = [
    "Staff not yet arrived", "Staff gone to collect vaccines/commodities",
    "Public holiday", "Staff at LGA meeting or training",
    "Facility closed due to insecurity", "No staff posted on this shift", "Other",
]

TRAININGS = [
    "Life Saving Skills", "Basic Emergency Obstetric and Newborn Care",
    "Modified Life Saving Skills", "Post Abortion Care",
    "Family Planning (LARC)", "Family Planning (Short term)",
    "Postpartum Family Planning", "RI Refresher Training Modules",
    "Vaccine Management", "New Vaccine Introduction (HPV, MR)",
    "IMCI", "Nutrition / IYCF", "Malaria Case Management",
    "Data Management (DHIS2)", "Infection Prevention and Control",
]

CCE_TYPES = [
    "Solar Refrigerators and Freezers", "Refrigerators",
    "Temperature Monitoring Devices", "Cold Boxes (6L)", "GioStyle (4L)",
    "Rush (3L)", "Ice Packs",
]

COLD_CHAIN_INTERRUPTION_REASONS = [
    "Power failure / no electricity", "Equipment breakdown or malfunction",
    "No fuel for generator", "Temperature excursion - cause unknown", "Other",
]

# (name, category, unit, typical monthly consumption for a mid-size PHC)
COMMODITIES = [
    ("Oxytocin", "Maternal", "ampoule", 40),
    ("Misoprostol", "Maternal", "tablet", 120),
    ("Tranexamic Acid Injection", "Maternal", "ampoule", 15),
    ("IV Fluids", "Maternal", "bag", 60),
    ("Giving Sets", "Maternal", "piece", 60),
    ("Calibrated Blood Collection Drape", "Maternal", "piece", 20),
    ("Magnesium Sulphate Injection", "Maternal", "ampoule", 20),
    ("Folic Acid", "Maternal", "tablet", 900),
    ("Sulphadoxine + Pyrimethamine", "Maternal", "tablet", 300),
    ("Ferrous Sulphate", "Maternal", "tablet", 900),
    ("Paracetamol Tablet", "General", "tablet", 1500),
    ("Amoxicillin Capsule", "General", "capsule", 800),
    ("Ibuprofen Tablet", "General", "tablet", 500),
    ("Artemether Injection", "General", "ampoule", 40),
    ("Amoxicillin Dispersible", "Child", "bottle", 60),
    ("Zinc", "Child", "tablet", 300),
    ("ORS", "Child", "sachet", 250),
    ("Paracetamol Syrup", "Child", "bottle", 80),
    ("Ibuprofen Suspension", "Child", "bottle", 40),
    ("Chlorhexidine Gel", "Child", "tube", 30),
    ("Artemether + Lumefantrine", "General", "pack", 200),
    ("Injectable Contraceptives", "Family Planning", "ampoule", 60),
    ("Implants", "Family Planning", "piece", 15),
]

STOCKOUT_DURATIONS = ["No stock-out", "Less than 1 week", "1 to 4 weeks", "More than 4 weeks"]

STOCKOUT_REASONS = [
    "Stock-out at LGA/state/central supply level",
    "Requisition not submitted or submitted late",
    "Incomplete fulfillment of requisition",
    "Delay in delivery or distribution",
    "Insufficient funds for procurement",
    "Poor quantification or forecasting",
    "High demand or unexpected increase in consumption",
    "Expired or damaged stock not replaced",
    "Storage or cold chain failure",
    "No feedback from KADHSMA",
    "Given a non-requisitioned essential medicine or commodity",
    "Other",
]

NOT_RECEIVED_REASONS = [
    "Stock-out at the source/KADHSMA", "Delivery delay",
    "Transportation challenges", "Other",
]

SUPPLIERS = [
    "Federal Government", "KDHSMA", "Free MNCH", "Zipline", "NGO",
    "Open Market", "LGA", "Donations",
]

VACCINES = ["BCG", "HPV", "IPV", "MR", "MEN A", "MCV", "OPV", "YF", "PENTA", "ROTA", "PCV"]

VACCINE_DISPENSE_REASONS = [
    "Scheduled routine immunization session", "Outreach session held this week",
    "Catch-up campaign", "High birth cohort this week", "School-based session (HPV)",
]

REQUISITION_FREQ = ["Monthly", "Bi-monthly", "Quarterly", "We do not submit requisitions"]
REQUISITION_SYSTEMS = [
    "Paper-based LMIS", "Electronic LMIS (eLMIS/NHLMIS)", "Electronic/Telegram",
    "Both paper and electronic", "Other",
]
REQUISITION_RECEIPT = ["Yes, all items received", "Yes, some items received", "No, none received yet"]
REQUISITION_NOT_SUBMITTED_REASONS = [
    "No commodities available at the source/KADHSMA", "No funds to submit requisition",
    "Staff responsible was absent/unavailable", "Facility had sufficient stock",
    "Requisition schedule was changed or delayed by higher level", "Other",
]

SALARY_DELAY = ["No delay", "1-2 weeks", "3-4 weeks", "More than 1 month"]
SALARY_ISSUES = [
    "Delayed payment", "Incomplete payment", "Deductions not explained",
    "Payment to wrong account", "Salary not paid at all",
]
SALARY_SERVICE_EFFECTS = [
    "Staff absent to chase payment", "Reduced staff motivation",
    "Staff left for other jobs", "Reduced opening hours", "No effect",
]
LEAVE_FOR_SALARY_REASONS = [
    "No bank or ATM nearby", "Bank verification / BVN issues",
    "Salary paid in cash at LGA headquarters", "POS agents charge high fees", "Other",
]
LEAVE_FOR_SALARY_FREQ = ["Never", "Once a month", "2-3 times a month", "Weekly"]

ATTENDANCE_REGISTER_TYPES = ["Paper-based", "Electronic", "Biometric", "Combination"]
NO_REGISTER_REASONS = [
    "Facility uses an electronic/biometric attendance system",
    "Staff register not supplied by LGA/authority",
    "Register previously used but lost or damaged",
    "Facility management does not enforce staff attendance tracking",
    "Lack of supervision or monitoring", "Staff shortages / workload constraints", "Other",
]
ROSTER_DEV_FREQ = ["Monthly", "Weekly", "Biweekly", "Quarterly", "Other"]
ROSTER_UPDATE_FREQ = ["Weekly", "On need basis"]
HOURS_OF_OPERATION = ["24 hours", "12 hours", "6-8 hours", "<5 hours"]
CADRE_OF_RESPONDENT = ["Nurse/Midwife", "CHO", "CHEW", "JCHEW", "Medical Officer", "Pharmacy Technician", "Other"]
RESPONDENT_POSITIONS = ["OIC", "2IC", "ANC In-charge", "RI Focal Person", "Pharmacy In-charge"]
VACCINE_STOCK_STATUS = [
    "Yes",
    "No, the facility does not stock vaccines but offers Immunization services",
    "No, the facility does not stock vaccines and does not offer Immunization services",
]
