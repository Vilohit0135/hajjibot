# data/visa_data.py

VISA_EXPERT_DISCLAIMER = (
    "Please check with our visa expert by dialling +919008447887."
)

VISA_COUNTRIES = [
    "Dubai",
    "France",
    "Germany",
    "Finland",
    "Sri Lanka",
    "Canada",
    "United Kingdom",
    "Spain",
    "Switzerland",
    "Egypt",
    "South Africa",
    "Netherlands",
    "Czech Republic",
    "UAE",
    "Austria",
    "Ukraine",
    "USA",
    "Denmark",
    "Greece",
    "Hungary",
    "Sweden",
    "Singapore",
    "Turkey",
    "Australia",
    "Thailand",
    "New Zealand",
    "Italy",
    "Hong Kong",
    "Bangladesh",
    "Slovenia",
    "Saudi Arabia",
    "Belgium",
    "Poland",
    "Slovakia",
    "Iceland",
    "Portugal",
    "Norway",
    "Latvia",
    "Malta",
    "Malaysia",
    "Vietnam",
    "Tom",
    "Jerica",
    "Cambodia",
    "Liechtenstein",
    "Philippines",
]

CITY_TO_IATA = {
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "chennai": "MAA",
    "bangalore": "BLR",
    "hyderabad": "HYD",

    "jeddah": "JED",
    "jedha": "JED",
    "riyadh": "RUH",
    "mecca": "JED",
    "makkah": "JED",
    "madinah": "MED",

    "dubai": "DXB",
    "doha": "DOH",
    "singapore": "SIN",
}

VISA_COUNTRY_LOOKUP = {country.lower(): country for country in VISA_COUNTRIES}