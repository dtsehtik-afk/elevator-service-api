"""Hebrew label maps used server-side (e.g. in the technician web app)."""

FAULT_TYPE_HE = {
    "STUCK":      "מעלית תקועה",
    "DOOR":       "תקלת דלת",
    "ELECTRICAL": "תקלה חשמלית",
    "MECHANICAL": "תקלה מכנית",
    "SOFTWARE":   "תקלת תוכנה",
    "OTHER":      "תקלה כללית",
}

PRIORITY_HE = {
    "CRITICAL": "קריטי",
    "HIGH":     "גבוה",
    "MEDIUM":   "בינוני",
    "LOW":      "נמוך",
}
