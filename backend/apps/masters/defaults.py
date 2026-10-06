"""Default equipment categories (indicative starting values; users edit them afterwards)."""

# (code, name)
DEFAULT_GROUPS = [
    ("CRITICAL_CARE", "Critical Care & Life Support"),
    ("MONITORING", "Patient Monitoring & Diagnostics"),
    ("IMAGING", "Diagnostic Imaging"),
    ("LABORATORY", "Laboratory"),
    ("OT_SURGICAL", "OT & Surgical"),
    ("THERAPEUTIC", "Therapeutic"),
    ("STERILIZATION", "Sterilization"),
]

# (code, name, group_code, pm_days, calibration_days, risk_class)
DEFAULT_CATEGORIES = [
    ("VENTILATOR", "Ventilator", "CRITICAL_CARE", 90, 365, "HIGH"),
    ("DEFIBRILLATOR", "Defibrillator", "CRITICAL_CARE", 90, 180, "HIGH"),
    ("INFUSION_PUMP", "Infusion Pump", "CRITICAL_CARE", 180, 365, "HIGH"),
    ("SYRINGE_PUMP", "Syringe Pump", "CRITICAL_CARE", 180, 365, "HIGH"),
    ("ANESTHESIA_WORKSTATION", "Anesthesia Workstation", "CRITICAL_CARE", 90, 365, "HIGH"),
    ("PATIENT_MONITOR", "Patient Monitor", "MONITORING", 180, 365, "MEDIUM"),
    ("PULSE_OXIMETER", "Pulse Oximeter", "MONITORING", 180, 365, "MEDIUM"),
    ("ECG_MACHINE", "ECG Machine", "MONITORING", 180, 365, "MEDIUM"),
    ("XRAY_SYSTEM", "X-Ray System", "IMAGING", 180, 365, "HIGH"),
    ("CT_SCANNER", "CT Scanner", "IMAGING", 90, 365, "HIGH"),
    ("MRI_SCANNER", "MRI Scanner", "IMAGING", 90, 365, "HIGH"),
    ("ULTRASOUND", "Ultrasound Machine", "IMAGING", 180, 365, "MEDIUM"),
    ("C_ARM", "C-Arm", "IMAGING", 180, 365, "HIGH"),
    ("HEMATOLOGY_ANALYZER", "Hematology Analyzer", "LABORATORY", 90, 365, "MEDIUM"),
    ("BIOCHEMISTRY_ANALYZER", "Biochemistry Analyzer", "LABORATORY", 90, 365, "MEDIUM"),
    ("CENTRIFUGE", "Centrifuge", "LABORATORY", 180, 365, "LOW"),
    ("MICROSCOPE", "Microscope", "LABORATORY", 365, None, "LOW"),
    ("OT_TABLE", "Operation Table", "OT_SURGICAL", 180, None, "MEDIUM"),
    ("OT_LIGHT", "Operation Theatre Light", "OT_SURGICAL", 180, None, "MEDIUM"),
    ("ELECTROSURGICAL_UNIT", "Electrosurgical Unit", "OT_SURGICAL", 180, 365, "HIGH"),
    ("SUCTION_APPARATUS", "Suction Apparatus", "OT_SURGICAL", 180, None, "MEDIUM"),
    ("DIALYSIS_MACHINE", "Dialysis Machine", "THERAPEUTIC", 90, 365, "HIGH"),
    ("INFANT_WARMER", "Infant Warmer", "THERAPEUTIC", 180, 365, "HIGH"),
    ("OXYGEN_CONCENTRATOR", "Oxygen Concentrator", "THERAPEUTIC", 180, None, "MEDIUM"),
    ("AUTOCLAVE", "Autoclave", "STERILIZATION", 90, 365, "HIGH"),
]